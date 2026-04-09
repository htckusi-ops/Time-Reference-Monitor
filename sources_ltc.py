from __future__ import annotations
import collections
import dataclasses
import shlex
import subprocess
import threading
import time
import re
import select
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from models import LTCStatus
from rolling import RollingCounter


_TC_RE = re.compile(r"(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2}):(?P<ff>\d{2})")

# ltcdump -F output: "YYYY-MM-DD ±HHMM HH:MM:SS:FF | pos pos"
# This is the preferred format — includes date AND timezone directly.
_LTCDUMP_F_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+([+-]\d{4})\s+(\d{2}:\d{2}:\d{2}:\d{2})")

# ltcdump 0.7.0 output with -d only: "HH:MM:SS:FF YYYY-MM-DD"
# alsaltc output with date:          "HH:MM:SS:FF YYYY-MM-DD"
_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# ltcdump output without -d: "HH:MM:SS:FF | n1 n2 n3 n4 n5 n6 n7 n8"  (8 nibbles 0-15)
_UB_RE = re.compile(r"\|\s*(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})")


def _nibbles_to_ub(n: list) -> str:
    """Format 8 nibbles as 4 hex bytes: 'AB CD EF GH'."""
    return " ".join(f"{(n[i] << 4 | n[i + 1]):02X}" for i in range(0, 8, 2))


def _decode_ltc_date(nibbles: list) -> Optional[str]:
    """
    Decode SMPTE 309M date from 8 user-bit nibbles as output by ltcdump -F
    (without -d).  Empirically verified against known data: '64260408' → 2026-04-08.

    Nibble layout (0-indexed, each nibble = 4 bits):
      [0]: BGF flags + timezone sign/info   (not used for date)
      [1]: BGF flags + century bit (bit 2)  (nibble[1] >> 2) & 1 → 1=2000+
      [2]: year tens
      [3]: year units
      [4]: month tens
      [5]: month units
      [6]: day tens
      [7]: day units
    """
    if len(nibbles) != 8:
        return None
    century = 2000 if (nibbles[1] >> 2) & 1 else 1900
    year_t  = nibbles[2] & 0xF
    year_u  = nibbles[3] & 0xF
    mon_t   = nibbles[4] & 0xF
    mon_u   = nibbles[5] & 0xF
    day_t   = nibbles[6] & 0xF
    day_u   = nibbles[7] & 0xF
    year  = century + year_t * 10 + year_u
    month = mon_t * 10 + mon_u
    day   = day_t * 10 + day_u
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        from datetime import date as _date
        _date(year, month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def utc_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _probe_alsa_delay_ms(device: str, rate: int = 48000) -> Optional[float]:
    """
    Probe ALSA capture period size for *device* and return capture latency in ms.

    Three strategies, tried in order:
      1. arecord without format flags  — lets dsnoop/ALSA negotiate native format.
      2. arecord with -f S16_LE        — fallback for plain hw: devices.
      3. /proc/asound/ procfs          — most reliable when ltcdump already has the
                                         device open; reads actual configured params.
    Returns latency in ms, or None if all three fail.
    """
    attempts = [
        # No format flags: ALSA/dsnoop uses native format (required for named devices).
        ["arecord", "-D", device, "-d", "1", "--verbose", "/dev/null"],
        # Explicit S16_LE: fallback for plain hw: devices.
        ["arecord", "-D", device, "-f", "S16_LE", "-c", "1", "-r", str(rate),
         "-d", "1", "--verbose", "/dev/null"],
    ]
    for cmd in attempts:
        result = _run_arecord_probe(cmd)
        if result is not None:
            return result
    # Strategy 3: read from procfs — works when ltcdump already has the device open.
    return _probe_alsa_delay_from_proc()


def _probe_alsa_delay_from_proc() -> Optional[float]:
    """
    Read period_size from /proc/asound/card*/pcm*c/sub*/hw_params.
    When ltcdump is running the configured hw params are visible here.
    Returns latency in ms for the first open capture stream found, or None.
    """
    import glob as _glob
    for path in sorted(_glob.glob("/proc/asound/card*/pcm*c/sub*/hw_params")):
        try:
            with open(path) as f:
                content = f.read()
            if not content.strip() or content.strip() == "closed":
                continue
            rate_m = re.search(r"rate:\s*(\d+)", content)
            period_m = re.search(r"period_size:\s*(\d+)", content)
            if rate_m and period_m:
                return int(period_m.group(1)) / int(rate_m.group(1)) * 1000.0
        except Exception:
            continue
    return None


def _run_arecord_probe(cmd: list) -> Optional[float]:
    """Run one arecord probe attempt; parse period_size/buffer_size from verbose output."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        lines: list = []
        rate_from_output: Optional[int] = None
        try:
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                ready, _, _ = select.select([proc.stdout], [], [], 0.3)
                if not ready:
                    continue
                line = proc.stdout.readline()
                if not line:
                    break
                lines.append(line)
                # Capture actual rate from verbose output (may differ from requested)
                if rate_from_output is None:
                    rm = re.search(r"rate\s*[=:]\s*(\d+)", line)
                    if rm:
                        rate_from_output = int(rm.group(1))
                if "period_size" in line:
                    break
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
        text = "".join(lines)
        # ALSA verbose uses "key : value" or "key = value" depending on version
        m = re.search(r"period_size\s*[=:]\s*(\d+)", text)
        if m:
            r = rate_from_output or 48000
            return int(m.group(1)) / r * 1000.0
        m = re.search(r"buffer_size\s*[=:]\s*(\d+)", text)
        if m:
            r = rate_from_output or 48000
            return int(m.group(1)) / 4.0 / r * 1000.0
    except Exception:
        pass
    return None


def _tc_to_frames(tc: str, fps: int) -> Optional[int]:
    """Convert 'HH:MM:SS:FF' to absolute frame count within 24h."""
    m = _TC_RE.fullmatch(tc)
    if not m:
        return None
    hh = int(m.group("hh")); mm = int(m.group("mm")); ss = int(m.group("ss")); ff = int(m.group("ff"))
    fps = max(1, int(fps))
    return ((hh * 3600 + mm * 60 + ss) * fps) + ff


class LTCMonitor:
    def __init__(
        self,
        enabled: bool,
        device: str,
        fps: str,
        cmd: Optional[str],
        trace: bool,
        rolling_window_s: int,
        *,
        dropout_timeout_ms: int = 0,
        jump_tolerance_frames: int = 0,
    ):
        self.enabled = bool(enabled)
        self.device = device or "default"
        self.fps = fps or "25"
        # ltcdump: -a for ALSA device, -d to decode date/tz from user bits, -F for full format
        # Full format output: "YYYY-MM-DD ±HHMM HH:MM:SS:FF | pos pos"
        self.cmd = cmd or f"ltcdump -a {shlex.quote(self.device)} -f {shlex.quote(self.fps)} -d -F"
        self.trace = bool(trace)

        self.dropout_timeout_ms = max(0, int(dropout_timeout_ms or 0))
        self.jump_tolerance_frames = max(0, int(jump_tolerance_frames or 0))
        try:
            self._fps_i = int(float(self.fps))
        except Exception:
            self._fps_i = 25

        self._last_tc_frames: Optional[int] = None
        self._last_tc_mono: Optional[float] = None
        self._jump_roll = RollingCounter(rolling_window_s)
        self._alsa_probed = False   # retry flag: probe again on first LTC frame if initial probe fails

        # Probe ALSA capture delay once at construction time.
        # May return None if the device is not yet ready; will retry on first LTC frame.
        alsa_delay: Optional[float] = None
        if self.enabled:
            alsa_delay = _probe_alsa_delay_ms(self.device)
            self._alsa_probed = alsa_delay is not None

        self._lock = threading.Lock()
        self._status = LTCStatus(
            enabled=self.enabled, device=self.device, fps=self.fps,
            present=False, alsa_delay_ms=alsa_delay,
        )
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._err_roll = RollingCounter(rolling_window_s)

        # Raw line ring buffer for live diagnostic view
        self._raw_lines: collections.deque = collections.deque(maxlen=500)
        self._raw_seq: int = 0
        self._raw_lock = threading.Lock()

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thr and self._thr.is_alive():
            return
        self._thr = threading.Thread(target=self._run, daemon=True, name="ltc-monitor")
        self._thr.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> LTCStatus:
        with self._lock:
            st = dataclasses.replace(self._status)
        if st.last_update_utc:
            try:
                last = datetime.fromisoformat(st.last_update_utc)
                st.last_update_age_s = max(0.0, (datetime.now(timezone.utc) - last).total_seconds())
            except Exception:
                st.last_update_age_s = None
        st.decode_errors_rolling = self._err_roll.count()
        st.jumps_rolling = self._jump_roll.count()
        return st

    def _mark_absent(self) -> None:
        with self._lock:
            self._status.present = False
            if self._status.no_ltc_since_utc is None:
                self._status.no_ltc_since_utc = utc_iso_ms()

    def _mark_present(self, tc: str, raw: str) -> None:
        # Retry ALSA delay probe if the initial probe failed (device not ready at startup)
        if not self._alsa_probed:
            delay = _probe_alsa_delay_ms(self.device)
            if delay is not None:
                self._alsa_probed = True
                with self._lock:
                    self._status.alsa_delay_ms = delay
        # Parse date + timezone:
        # 1. ltcdump -F: "YYYY-MM-DD ±HHMM HH:MM:SS:FF | pos pos"  → date + tz directly
        # 2. ltcdump -d only / alsaltc: "HH:MM:SS:FF YYYY-MM-DD"   → date only
        # 3. ltcdump without -d: nibble user-bits decode            → date via SMPTE 309M
        user_bits: Optional[str] = None
        ltc_date: Optional[str] = None
        ltc_tz: Optional[str] = None
        f_m = _LTCDUMP_F_RE.match(raw)
        if f_m:
            ltc_date = f_m.group(1)   # "YYYY-MM-DD"
            ltc_tz   = f_m.group(2)   # "±HHMM"
        else:
            d_m = _DATE_RE.search(raw)
            if d_m:
                ltc_date = d_m.group(0)
            else:
                ub_m = _UB_RE.search(raw)
                if ub_m:
                    nibbles = [int(ub_m.group(i)) for i in range(1, 9)]
                    user_bits = _nibbles_to_ub(nibbles)
                    ltc_date = _decode_ltc_date(nibbles)
        with self._lock:
            self._status.present = True
            self._status.timecode = tc
            self._status.last_update_utc = utc_iso_ms()
            self._status.no_ltc_since_utc = None
            self._status.user_bits = user_bits
            self._status.ltc_date = ltc_date
            self._status.ltc_tz   = ltc_tz
            self._status.raw = raw if self.trace else None

    def get_raw_lines(self, since: int = 0) -> Tuple[List[str], int]:
        """Return (lines_since, current_seq).  Thread-safe."""
        with self._raw_lock:
            lines = list(self._raw_lines)
            seq = self._raw_seq
        drop = max(0, seq - len(lines))
        start = max(0, since - drop)
        return lines[start:], seq

    def _append_raw(self, line: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        with self._raw_lock:
            self._raw_lines.append(f"{ts}  {line}")
            self._raw_seq += 1

    def _run(self) -> None:

        while not self._stop.is_set():
            try:
                proc = subprocess.Popen(
                    self.cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None

                # Reset per-process state
                self._last_tc_frames = None
                self._last_tc_mono = None
                dropout_marked = False

                while not self._stop.is_set():
                    # Periodic timeout so we can detect dropouts even if no output arrives
                    r, _, _ = select.select([proc.stdout], [], [], 0.2)
                    now = time.monotonic()

                    # Dropout watchdog (Python-side)
                    if self.dropout_timeout_ms > 0 and self._last_tc_mono is not None:
                        if (now - self._last_tc_mono) * 1000.0 >= float(self.dropout_timeout_ms):
                            if not dropout_marked:
                                self._mark_absent()
                                dropout_marked = True

                    if r:
                        line = proc.stdout.readline()
                        if not line:
                            break
                        line = line.strip()
                        if not line:
                            continue

                        self._append_raw(line)

                        if line == "NO_LTC":
                            self._mark_absent()
                            dropout_marked = True
                            continue

                        m = _TC_RE.search(line)
                        if not m:
                            continue

                        tc = f"{m.group('hh')}:{m.group('mm')}:{m.group('ss')}:{m.group('ff')}"

                        # Jump detection
                        if self.jump_tolerance_frames > 0:
                            cur = _tc_to_frames(tc, self._fps_i)
                            if cur is not None and self._last_tc_frames is not None:
                                day_frames = 24 * 3600 * max(1, self._fps_i)
                                diff = cur - self._last_tc_frames

                                # handle wrap-around near midnight: choose minimal diff
                                if diff > day_frames // 2:
                                    diff -= day_frames
                                elif diff < -day_frames // 2:
                                    diff += day_frames

                                if abs(diff) > int(self.jump_tolerance_frames):
                                    with self._lock:
                                        self._status.jumps_total += 1
                                        self._jump_roll.add()
                                    # Mark as present anyway, but keep raw line for diagnostics
                        self._last_tc_frames = _tc_to_frames(tc, self._fps_i) or self._last_tc_frames
                        self._last_tc_mono = now
                        dropout_marked = False

                        self._mark_present(tc, line)

                # Process ended or stream closed -> absent
                try:
                    proc.terminate()
                except Exception:
                    pass
                self._mark_absent()
                time.sleep(0.5)

            except Exception:
                with self._lock:
                    self._status.decode_errors_total += 1
                    self._err_roll.add()
                self._mark_absent()
                time.sleep(1.0)
