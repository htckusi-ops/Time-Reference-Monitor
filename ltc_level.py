# ltc_level.py
import subprocess, math, struct, select, os, time
from typing import Dict


def read_ltc_level(
    device: str,
    duration_ms: int = 100,
    rate: int = 48000,
    channels: int = 1,
) -> Dict[str, float]:

    frames = int(rate * duration_ms / 1000)
    bytes_per_sample = 4  # S32_LE
    bytes_needed = frames * channels * bytes_per_sample

    # Optional: über "plug:" konvertieren lassen (hilft wenn dsnoop/hw picky ist)
    arec_dev = device
    if not device.startswith(("plug:", "hw:", "plughw:")):
        arec_dev = "plug:" + device

    cmd = [
        "arecord",
        "-q",
        "-t", "raw",  # kein WAV-Header
        "-D", arec_dev,
        "-f", "S32_LE",
        "-c", str(channels),
        "-r", str(rate),
    ]
    p = None
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw = _read_with_deadline(p.stdout.fileno(), bytes_needed,
                                  deadline=time.monotonic() + duration_ms / 1000.0 + 2.0)
    except Exception:
        return _zero_levels()
    finally:
        if p is not None:
            try:
                p.terminate()
                p.wait(timeout=0.5)
            except Exception:
                try:
                    p.kill()
                    p.wait(timeout=0.5)
                except Exception:
                    pass

    if len(raw) < bytes_per_sample:
        return _zero_levels()

    n = len(raw) // 4
    samples = struct.unpack("<%di" % n, raw)

    MAX_I32 = (2 ** 31) - 1
    MIN_I32 = -(2 ** 31)
    denom = float(MAX_I32)
    peak = 0.0
    acc = 0.0

    for s in samples:
        if s == MIN_I32:
            s = -MAX_I32
        v = min(abs(s) / denom, 1.0)
        if v > peak:
            peak = v
        acc += v * v

    rms = math.sqrt(acc / len(samples)) if samples else 0.0
    return {
        "peak": peak,
        "rms": rms,
        "dbfs_peak": _to_dbfs(peak),
        "dbfs_rms": _to_dbfs(rms),
    }


def _read_with_deadline(fd: int, nbytes: int, deadline: float) -> bytes:
    """Read up to nbytes from fd, returning early if deadline is reached.

    Uses select() so the call never blocks longer than the deadline,
    even if the subprocess hangs and never produces data.
    """
    buf = bytearray()
    while len(buf) < nbytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            r, _, _ = select.select([fd], [], [], min(remaining, 0.05))
        except (ValueError, OSError):
            break
        if not r:
            continue
        try:
            chunk = os.read(fd, nbytes - len(buf))
        except OSError:
            break
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def _to_dbfs(v: float) -> float:
    if v <= 0.0:
        return -120.0
    return 20.0 * math.log10(v)


def _zero_levels() -> Dict[str, float]:
    return {"peak": 0.0, "rms": 0.0, "dbfs_peak": -120.0, "dbfs_rms": -120.0}
