from __future__ import annotations

import threading
import re
from collections.abc import Callable

try:
    import pyttsx3
except Exception:  # pragma: no cover
    pyttsx3 = None

try:
    import speech_recognition as sr
except Exception:  # pragma: no cover
    sr = None


def _confirm_microphone_permission() -> bool:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        try:
            return messagebox.askyesno(
                "Microphone permission",
                "RAHU would like to use your microphone. Allow microphone access?",
                parent=root,
            )
        finally:
            root.destroy()
    except Exception:
        try:
            answer = input("RAHU needs microphone access to listen to your voice. Allow microphone permission? [y/N]: ").strip().lower()
            return answer in {"y", "yes"}
        except EOFError:
            return False


class VoiceController:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.permission_requested = False
        self.engine = None
        self.agent_name = "RAHU"
        self.agent_pronunciation = "Rahu"
        self.on_voice_unavailable: Callable[[], None] | None = None
        if self.enabled and pyttsx3 is not None:
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", 170)

    @property
    def microphone_available(self) -> bool:
        return sr is not None

    def set_agent_identity(self, name: str, pronunciation: str) -> None:
        self.agent_name = name.strip() or "RAHU"
        self.agent_pronunciation = pronunciation.strip() or self.agent_name

    def _spoken_text(self, text: str) -> str:
        if not self.agent_name or not self.agent_pronunciation:
            return text
        return re.sub(
            rf"\b{re.escape(self.agent_name)}\b",
            self.agent_pronunciation,
            text,
            flags=re.IGNORECASE,
        )

    def _disable_voice(self) -> None:
        self.set_enabled(False)
        if self.on_voice_unavailable is not None:
            self.on_voice_unavailable()

    @staticmethod
    def _is_listen_timeout(error: Exception) -> bool:
        timeout_error = getattr(sr, "WaitTimeoutError", None) if sr is not None else None
        return isinstance(timeout_error, type) and isinstance(error, timeout_error)

    def request_permission(self) -> bool:
        if self.enabled:
            return True

        granted = _confirm_microphone_permission()
        self.permission_requested = True
        if not granted:
            self.enabled = False
            print("Microphone permission denied. Voice mode is disabled; text input remains available.")
            return False

        if sr is None:
            print("SpeechRecognition is unavailable. Voice mode is disabled; text input remains available.")
            self.enabled = False
            return False

        self.enabled = True
        if pyttsx3 is not None and self.engine is None:
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", 170)
        print("Microphone permission granted. Voice mode is now enabled.")
        return True

    def speak(self, text: str) -> None:
        if not self.enabled:
            return
        if not text or not text.strip():
            return
        if self.engine is None:
            print(f"[Voice]: {text}")
            return

        def _speak() -> None:
            try:
                self.engine.say(self._spoken_text(text))
                self.engine.runAndWait()
            except Exception:
                print(f"[Voice]: {text}")

        threading.Thread(target=_speak, daemon=True).start()

    def listen(self) -> str:
        if not self.enabled or sr is None:
            return input("You: ").strip()

        try:
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                print("Listening...")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
            return recognizer.recognize_google(audio)
        except Exception as exc:
            if self._is_listen_timeout(exc):
                if self.on_voice_unavailable is not None:
                    self.on_voice_unavailable()
                return ""
            self._disable_voice()
            print("Voice input is unavailable. Please type your command.")
            return input("You: ").strip()

    def listen_for_wake_word(self, wake_word: str = "hey rahu") -> str:
        if not self.enabled or sr is None:
            return input("You: ").strip()

        try:
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                print(f"Waiting for wake word: {wake_word}")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
            transcript = recognizer.recognize_google(audio)
            print(f"Heard: {transcript}")
            return transcript
        except Exception as exc:
            if self._is_listen_timeout(exc):
                if self.on_voice_unavailable is not None:
                    self.on_voice_unavailable()
                return ""
            self._disable_voice()
            print("Voice input is unavailable. Please type your command.")
            return input("You: ").strip()

    def listen_for_command_after_wake(self, wake_word: str) -> str:
        if not self.enabled or sr is None:
            return input("Command: ").strip()

        try:
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                print(f"Listening for command after {wake_word}...")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
            command = recognizer.recognize_google(audio)
            print(f"Command: {command}")
            return command
        except Exception as exc:
            if self._is_listen_timeout(exc):
                if self.on_voice_unavailable is not None:
                    self.on_voice_unavailable()
                return ""
            self._disable_voice()
            print("Voice input is unavailable. Please type your command.")
            return input("Command: ").strip()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled and pyttsx3 is not None and self.engine is None:
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", 170)
