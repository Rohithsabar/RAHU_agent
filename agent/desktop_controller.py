from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


class DesktopController:
    def find_paths_by_name(
        self,
        name: str,
        roots: list[Path] | None = None,
        limit: int = 5,
        time_limit: float = 6.0,
    ) -> list[Path]:
        requested = Path(name.strip().strip('"')).expanduser()
        if requested.exists():
            return [requested]

        query = requested.name.casefold()
        if not query:
            return []

        search_roots = roots or [Path.home(), Path.cwd()]
        if roots is None and os.name == "nt":
            search_roots.extend(
                Path(f"{letter}:\\")
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if Path(f"{letter}:\\").exists()
            )
        primary_roots = {root.expanduser().resolve() for root in search_roots[:2]}
        normalized_roots = []
        for root in search_roots:
            try:
                resolved = root.expanduser().resolve()
            except OSError:
                continue
            if resolved.exists() and resolved not in normalized_roots:
                normalized_roots.append(resolved)

        ignored_directories = {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            "appdata",
            "windows",
            "program files",
            "program files (x86)",
            "programdata",
            "$recycle.bin",
            "system volume information",
        }
        exact_matches = []
        partial_matches = []
        deadline = time.monotonic() + time_limit

        for root in normalized_roots:
            if roots is None and root not in primary_roots and exact_matches:
                break
            if root.is_file():
                candidates = [root]
                directories = []
            else:
                candidates = []
                directories = []
                for current, child_directories, filenames in os.walk(root, onerror=lambda _error: None):
                    if time.monotonic() >= deadline:
                        break
                    child_directories[:] = [
                        directory for directory in child_directories
                        if directory.casefold() not in ignored_directories
                    ]
                    current_path = Path(current)
                    directories.extend(current_path / directory for directory in child_directories)
                    candidates.extend(current_path / filename for filename in filenames)

            for candidate in candidates + directories:
                candidate_name = candidate.name.casefold()
                if candidate_name == query or candidate.stem.casefold() == query:
                    exact_matches.append(candidate)
                elif query in candidate_name:
                    partial_matches.append(candidate)
                if len(exact_matches) >= limit or time.monotonic() >= deadline:
                    break
            if len(exact_matches) >= limit or time.monotonic() >= deadline:
                break

        return exact_matches[:limit] if exact_matches else partial_matches[:limit]

    def run_command(self, command: str) -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            output = result.stdout.strip() or result.stderr.strip() or "Command executed successfully."
            return output
        except Exception as exc:  # pragma: no cover
            return f"Command failed: {exc}"

    def open_file(self, file_path: str) -> str:
        target = Path(file_path).expanduser()
        if not target.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if os.name == "nt":
            os.startfile(str(target))
        else:
            subprocess.Popen(["xdg-open", str(target)])

        return f"Opened file: {target}"

    def open_app(self, app_name: str) -> str:
        if os.name == "nt":
            normalized_name = " ".join(app_name.casefold().split())
            windows_aliases = {
                "microsoft store": "ms-windows-store:",
                "windows store": "ms-windows-store:",
                "store": "ms-windows-store:",
                "settings": "ms-settings:",
                "windows settings": "ms-settings:",
                "calculator": "calc.exe",
                "file explorer": "explorer.exe",
                "explorer": "explorer.exe",
                "notepad": "notepad.exe",
                "paint": "mspaint.exe",
            }
            launch_target = windows_aliases.get(normalized_name, app_name)
            try:
                os.startfile(launch_target)
                return f"Opened app: {app_name}"
            except OSError:
                pass

            start_menu_app = self._find_start_menu_app(normalized_name)
            if start_menu_app:
                try:
                    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{start_menu_app}"])
                    return f"Opened app: {app_name}"
                except OSError:
                    pass
            return f"Could not open app from name: {app_name}."

        result = self.run_command(app_name)
        return result or f"Started via command: {app_name}"

    def _find_start_menu_app(self, normalized_name: str) -> str | None:
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None

            import json

            apps = json.loads(result.stdout)
            if isinstance(apps, dict):
                apps = [apps]
            exact = [app for app in apps if " ".join(app.get("Name", "").casefold().split()) == normalized_name]
            matches = exact or [
                app for app in apps
                if normalized_name in " ".join(app.get("Name", "").casefold().split())
            ]
            if len(matches) == 1:
                return matches[0].get("AppID")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None
        return None

    def list_directory(self, directory: str) -> str:
        target = Path(directory).expanduser() if directory else Path.cwd()
        if not target.exists():
            raise FileNotFoundError(f"Folder not found: {directory}")

        items = sorted(entry.name for entry in target.iterdir())
        return "\n".join(items) if items else "Folder is empty."
