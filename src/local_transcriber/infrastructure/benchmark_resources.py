"""Sample owned process-tree RSS and whole-device VRAM without logging private data."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

import psutil

from local_transcriber.infrastructure.privacy import child_environment


class ResourceSampler:
    def __init__(self, output: Path, smi: str, gpu_index: int, *, interval: float = 0.5) -> None:
        if interval <= 0:
            raise ValueError("Sample interval must be positive")
        self.output, self.smi, self.gpu_index = output, smi, gpu_index
        self.interval = interval
        self.parent = psutil.Process()
        self.peak_rss = 0
        self.peak_vram: int | None = None
        self.baseline_vram: int | None = None
        self.samples = 0
        self.rss_errors = self.vram_errors = 0
        self.failure: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="benchmark-resources", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise RuntimeError("Resource sampler did not stop")
        if self.failure:
            raise RuntimeError("Resource sampler failed: " + self.failure)

    def _run(self) -> None:
        try:
            self._sample()
        except Exception as error:
            self.failure = type(error).__name__

    def _sample(self) -> None:
        started = time.perf_counter()
        with self.output.open("x", encoding="utf-8") as output:
            while not self._stop.is_set():
                rss = 0
                try:
                    processes = [self.parent, *self.parent.children(recursive=True)]
                    for process in processes:
                        try:
                            rss += process.memory_info().rss
                        except psutil.NoSuchProcess:
                            pass
                        except psutil.AccessDenied:
                            self.rss_errors += 1
                except psutil.Error:
                    self.rss_errors += 1
                self.peak_rss = max(self.peak_rss, rss)
                vram = None
                try:
                    result = subprocess.run(
                        [
                            self.smi,
                            f"--id={self.gpu_index}",
                            "--query-gpu=memory.used",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        timeout=3,
                        env=child_environment(),
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                    if result.returncode:
                        raise ValueError
                    vram = int(result.stdout.strip()) * 1024 * 1024
                    if self.baseline_vram is None:
                        self.baseline_vram = vram
                    self.peak_vram = max(self.peak_vram or 0, vram)
                except OSError, ValueError, subprocess.TimeoutExpired:
                    self.vram_errors += 1
                self.samples += 1
                output.write(
                    json.dumps(
                        {
                            "seconds": time.perf_counter() - started,
                            "rss_bytes": rss,
                            "device_vram_bytes": vram,
                        }
                    )
                    + "\n"
                )
                output.flush()
                self._stop.wait(self.interval)

    def summary(self) -> dict[str, int | float | None | str]:
        return {
            "peak_rss_bytes": self.peak_rss or None,
            "peak_vram_bytes": self.peak_vram,
            "baseline_vram_bytes": self.baseline_vram,
            "rss_scope": "sampler process plus recursive children; excludes PostgreSQL",
            "vram_scope": "whole selected GPU incl. other applications; NOT per-process",
            "sample_interval_seconds": self.interval,
            "samples": self.samples,
            "rss_errors": self.rss_errors,
            "vram_errors": self.vram_errors,
        }
