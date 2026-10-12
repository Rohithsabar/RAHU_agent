from __future__ import annotations

import os
import tempfile
import time
from typing import Dict, List
from pathlib import Path

import psutil


class LaptopSystemManager:
    def __init__(self) -> None:
        self.last_assessment: Dict[str, float] = {}
        self.temp_directory = Path(tempfile.gettempdir()).resolve()

    def assess(self) -> Dict[str, float | bool]:
        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent if hasattr(psutil, "disk_usage") else 0

        assessment = {
            "cpu_percent": round(float(cpu), 1),
            "memory_percent": round(float(memory), 1),
            "disk_percent": round(float(disk), 1),
            "slow": bool(cpu > 80 or memory > 80 or disk > 85),
        }
        self.last_assessment = assessment
        return assessment

    def suggestions(self) -> str:
        status = self.assess()
        if not status["slow"]:
            return "Your laptop looks stable right now. No heavy optimization is needed. Anything else I can do for you?"

        items: List[str] = []
        if float(status["cpu_percent"]) > 80:
            items.append("close heavy background apps and browser tabs")
        if float(status["memory_percent"]) > 80:
            items.append("free memory by closing unnecessary programs")
        if float(status["disk_percent"]) > 85:
            items.append("clear temporary files and old downloads")

        suggestions = ", ".join(items)
        return (
            f"I noticed your laptop may be slowing down because of {suggestions}. "
            "If you approve, I can help you clean up the system safely, close unnecessary apps, and suggest the best performance steps."
        )

    def optimize(self) -> str:
        status = self.assess()
        if not status["slow"]:
            return "Your system is already running normally. No optimization is required right now."
        return (
            "I can help with safe performance steps such as closing heavy apps, checking startup programs, and cleaning temporary files. "
            "Please approve the optimization before I take any action."
        )

    def _old_temp_files(self, older_than_days: int = 1) -> list[tuple[Path, int]]:
        root = self.temp_directory
        if not root.exists() or not root.is_dir():
            return []

        cutoff = time.time() - older_than_days * 24 * 60 * 60
        results = []
        for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            directories[:] = [
                name for name in directories
                if not (current_path / name).is_symlink()
                and not getattr(current_path / name, "is_junction", lambda: False)()
            ]
            for filename in filenames:
                path = current_path / filename
                try:
                    if path.is_symlink() or path.stat().st_mtime > cutoff:
                        continue
                    results.append((path, path.stat().st_size))
                except OSError:
                    continue
        return results

    def preview_junk_cleanup(self) -> dict[str, int]:
        files = self._old_temp_files()
        return {"files": len(files), "bytes": sum(size for _, size in files)}

    def clean_junk(self) -> dict[str, int]:
        files = self._old_temp_files()
        deleted = 0
        freed_bytes = 0
        for path, size in files:
            try:
                path.unlink()
                deleted += 1
                freed_bytes += size
            except OSError:
                continue

        for current, directories, _filenames in os.walk(self.temp_directory, topdown=False, followlinks=False):
            current_path = Path(current)
            for name in directories:
                directory = current_path / name
                if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)():
                    continue
                try:
                    directory.rmdir()
                except OSError:
                    pass

        return {"files": deleted, "bytes": freed_bytes}
