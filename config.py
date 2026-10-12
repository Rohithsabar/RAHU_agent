from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

if getattr(sys, "frozen", False):
    USER_DATA_ROOT = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "RAHU Assistant"
    DATA_DIR = USER_DATA_ROOT / "data"
else:
    DATA_DIR = Path(__file__).resolve().parent / "data"

DATA_PATH = DATA_DIR / "settings.json"


@dataclass
class AgentSettings:
    user_name: str = "User"
    agent_name: str = "RAHU"
    agent_pronunciation: str = "Rahu"
    wake_word: str = "hey rahu"
    preferred_language: str = "en-US"
    voice_enabled: bool = False
    default_payment_method: str = "Bank transfer"
    payment_schedule: str = "Daily"
    remote_permission_required: bool = True
    remote_connected: bool = False

    @classmethod
    def load(cls) -> "AgentSettings":
        if not DATA_PATH.exists():
            settings = cls()
            settings.save()
            return settings

        with DATA_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return cls(**payload)

    def save(self) -> None:
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DATA_PATH.open("w", encoding="utf-8") as file:
            json.dump(asdict(self), file, indent=2)


settings = AgentSettings.load()
