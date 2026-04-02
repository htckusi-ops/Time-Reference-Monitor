# spectrum.py
from __future__ import annotations

import os
import threading
import time
import tempfile
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from config import LTC_ALSA_DEVICE as device



def _utc_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class SpectrumStatus:
    state: str = "idle"  # idle | generating | error | disabled
    message: str = ""
    device: str = ""
    duration_s: int = 0
    has_image: bool = False
    has_audio: bool = False
    last_generated_utc: Optional[str] = None


class SpectrumManager:
    """
    On-demand LTC spectrum generator.
    Captures audio via arecord, renders spectrogram via sox, keeps PNG bytes in memory.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 48000,
        channels: int = 1,
        fmt: str = "S32_LE",
        max_duration_s: int = 120,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.fmt = str(fmt)
        self.max_duration_s = int(max_duration_s)

        self._lock = threading.Lock()
        self._status = SpectrumStatus()
        self._img: Optional[bytes] = None
        self._wav: Optional[bytes] = None
        self._worker: Optional[threading.Thread] = None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return asdict(self._status)

    def image_bytes(self) -> Optional[bytes]:
        with self._lock:
            return self._img

    def wav_bytes(self) -> Optional[bytes]:
        with self._lock:
            return self._wav

    def generate(self, *, duration_s: int, device: str) -> Dict[str, Any]:
        device = str(device or "").strip()
        duration_s = int(duration_s)

        if not device:
            raise ValueError("device is required")
        if duration_s <= 0 or duration_s > self.max_duration_s:
            raise ValueError(f"duration_s must be 1..{self.max_duration_s}")

        with self._lock:
            if self._worker and self._worker.is_alive():
                # already running
                self._status.message = "Already generating."
                return asdict(self._status)

            self._status.state = "generating"
            self._status.message = "Starting…"
            self._status.device = device
            self._status.duration_s = duration_s
            self._status.has_image = False
            self._status.has_audio = False
            self._status.last_generated_utc = None
            self._img = None
            self._wav = None

            t = threading.Thread(
                target=self._run_job,
                args=(device, duration_s),
                name="spectrum-gen",
                daemon=True,
            )
            self._worker = t
            t.start()
            return asdict(self._status)

    def _run_job(self, device: str, duration_s: int) -> None:
        wav_path = None
        png_path = None
        try:
            with tempfile.TemporaryDirectory(prefix="ptpmon_spectrum_") as td:
                wav_path = os.path.join(td, "ltc.wav")
                png_path = os.path.join(td, "spectrum.png")

                # 1) capture wav
                arec = [
                    "arecord",
                    "-D", device,
                    "-f", self.fmt,
                    "-r", str(self.sample_rate),
                    "-c", str(self.channels),
                    "-d", str(duration_s),
                    wav_path,
                ]
                self._set_msg(f"Capturing {duration_s}s from {device} …")
                subprocess.run(
                    arec,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=duration_s + 10,
                    check=True,
                    text=True,
                )

                # store WAV bytes for browser playback / download
                with open(wav_path, "rb") as f:
                    wav_data = f.read()
                with self._lock:
                    self._wav = wav_data
                    self._status.has_audio = True

                # 2) render spectrogram (PNG)
                sox_cmd = [
                    "sox", wav_path,
                    "-n",
                    "spectrogram",
                    "-o", png_path,
                    "-t", "LTC Spectrum",
                ]
                self._set_msg("Rendering spectrogram…")
                subprocess.run(
                    sox_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    check=True,
                    text=True,
                )

                # 3) read into memory
                with open(png_path, "rb") as f:
                    img = f.read()

            with self._lock:
                self._img = img
                self._status.state = "idle"
                self._status.message = "OK"
                self._status.has_image = True
                self._status.last_generated_utc = _utc_iso_ms()

        except subprocess.TimeoutExpired as e:
            self._set_error(f"Timeout: {e}")
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip()
            self._set_error(f"Command failed: {err[:400]}")
        except Exception as e:
            self._set_error(str(e))

    def _set_msg(self, msg: str) -> None:
        with self._lock:
            self._status.message = msg

    def _set_error(self, msg: str) -> None:
        with self._lock:
            self._status.state = "error"
            self._status.message = msg
            self._status.has_image = False
            self._status.last_generated_utc = _utc_iso_ms()
            self._img = None
