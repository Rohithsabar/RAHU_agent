from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config import DATA_DIR


class LearningMemory:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path) if path else DATA_DIR / "learning_memory.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"history": [], "preferences": {}}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            if not isinstance(payload, dict):
                return {"history": [], "preferences": {}}
            payload.setdefault("history", [])
            payload.setdefault("preferences", {})
            return payload
        except Exception:
            return {"history": [], "preferences": {}}

    def _save(self) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, indent=2)

    def record(self, command: str, response: str | None = None) -> None:
        text = (command or "").strip()
        if not text:
            return

        entry = {
            "text": text,
            "response": response or "",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self.data.setdefault("history", []).append(entry)

        keywords = [
            "notepad", "ppt", "presentation", "word", "report", "job", "search",
            "browser", "website", "remote", "payment", "laptop", "open", "connect"
        ]
        lower = text.lower()
        for keyword in keywords:
            if keyword in lower:
                bucket = self.data.setdefault("preferences", {}).setdefault(keyword, [])
                bucket.append(text)
                if len(bucket) > 12:
                    del bucket[:-12]

        self._save()

    def get_recent_context(self, limit: int = 5) -> list[str]:
        history = self.data.get("history", [])
        recent = [entry.get("text", "") for entry in history[-limit:]]
        return [item for item in recent if item]

    def get_preference(self, category: str) -> list[str]:
        prefs = self.data.get("preferences", {})
        values = prefs.get(category, [])
        if values:
            return values

        category_lower = (category or "").lower()
        category_map = {
            "routine": ["notepad", "open", "daily", "morning"],
            "project": ["ppt", "presentation", "document", "report", "project"],
            "job": ["job", "search"],
            "remote": ["remote", "connect", "device"],
        }

        matched = []
        for key, items in prefs.items():
            key_lower = key.lower()
            if category_lower in key_lower or key_lower in category_lower:
                matched.extend(items)
            elif category_lower in category_map and any(token in key_lower for token in category_map.get(category_lower, [])):
                matched.extend(items)

        if matched:
            return matched

        for key, items in prefs.items():
            if key_lower := key.lower():
                if any(token in key_lower for token in ["notepad", "ppt", "presentation", "remote", "job", "search", "document"]):
                    matched.extend(items)
        return matched

    def build_context(self, command: str) -> str:
        history = self.get_recent_context(5)
        if not history:
            return ""

        if command.lower().startswith("make") or "presentation" in command.lower():
            relevant = [item for item in history if "presentation" in item.lower() or "ppt" in item.lower() or "document" in item.lower()]
            if relevant:
                return "You often create presentations and documents around: " + ", ".join(relevant[-2:])

        if "job" in command.lower() or "search" in command.lower():
            relevant = [item for item in history if "job" in item.lower() or "search" in item.lower()]
            if relevant:
                return "You have been searching for: " + ", ".join(relevant[-2:])

        return "Recent tasks: " + ", ".join(history[-2:])
