from __future__ import annotations
import dataclasses
import shlex
import subprocess
import threading
import time
import re
import select
from datetime import datetime, timezone
from typing import Optional

from models import LTCStatus
from rolling import RollingCounter


_TC_RE = re.compile(r"(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2}):(?P<ff>\d{2})")


def utc_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _probe_alsa_delay_ms(device: str, rate: int = 48000) -> Optional[float]:
    """
    Probe ALSA capture period size for *device* and return capture latency in ms.
    Uses arecord --verbose; parses period_size from the setup block (= one interrupt
    period = actual capture-to-read latency). Falls back to buffer_size/4.
    Returns None on failure.
    """
    # Do NOT wrap in plug: — "plug:default" breaks the common "default" device.
    # Pass device as-is; users who need format conversion should specify plughw:X,Y.
    cmd = ["arecord", "-D", device, "-f", "S16_LE", "-c", "1", "-r", str(rate),
           "-d", "1", "--verbose", "/dev/null"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        lines: list = []
        try:
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                # Non-blocking line read via select so we can bail on deadline
                ready, _, _ = select.select([proc.stdout], [], [], 0.3)
                if not ready:
                    continue
                line = proc.stdout.readline()
                if not line:          # EOF – process exited
                    break
                lines.append(line)
                if "period_size" in line:  # setup block complete
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
            return int(m.group(1)) / rate * 1000.0
        # fallback: buffer_size / 4 (ring buffer is typically 4× one period)
        m = re.search(r"buffer_size\s*[=:]\s*(\d+)", text)
        if m:
            return int(m.group(1)) / 4.0 / rate * 1000.0
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
        self.cmd = cmd or f"ltcdump -d {shlex.quote(self.device)} -f {shlex.quote(self.fps)}"
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
        with self._lock:
            self._status.present = True
            self._status.timecode = tc
            self._status.last_update_utc = utc_iso_ms()
            self._status.no_ltc_since_utc = None
            self._status.raw = raw if self.trace else None

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
