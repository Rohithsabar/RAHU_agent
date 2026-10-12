from __future__ import annotations

from config import AgentSettings


class RemoteConnectionManager:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.connection_requested = False
        self.session_active = False

    def request_permission(self) -> str:
        self.connection_requested = True
        return (
            "A remote device is requesting permission to connect. "
            "Please approve the connection to continue."
        )

    def approve_connection(self) -> str:
        self.connection_requested = False
        self.session_active = True
        self.settings.remote_connected = True
        self.settings.save()
        return "Remote connection approved and enabled."

    def disconnect(self) -> str:
        self.connection_requested = False
        self.session_active = False
        self.settings.remote_connected = False
        self.settings.save()
        return "Remote session disconnected."

    def status(self) -> dict:
        return {
            "connected": self.session_active,
            "permission_pending": self.connection_requested,
            "remote_connected": self.settings.remote_connected,
        }
