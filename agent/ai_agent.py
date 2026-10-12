from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from config import DATA_DIR

try:
    import keyring
except Exception:  # pragma: no cover
    keyring = None


class AgenticAI:
    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.config_path = DATA_DIR / "ai_settings.json"
        saved = self._load_settings()
        self.online_url = (
            os.getenv("RAHU_AI_BASE_URL")
            or saved.get("online_url")
            or "https://generativelanguage.googleapis.com/v1beta/openai"
        ).rstrip("/")
        self.online_model = os.getenv("RAHU_AI_MODEL") or saved.get("online_model") or "gemini-3.8-flash"
        self.online_key = os.getenv("RAHU_AI_API_KEY") or os.getenv("OPENAI_API_KEY") or self._stored_api_key()
        self.local_url = (os.getenv("RAHU_LOCAL_AI_BASE_URL") or saved.get("local_url") or "http://127.0.0.1:11434/v1").rstrip("/")
        self.local_model = os.getenv("RAHU_LOCAL_AI_MODEL") or saved.get("local_model") or "qwen2.5:7b"
        self.max_tool_rounds = 3
        self.conversation_history: list[dict[str, str]] = []

    def _load_settings(self) -> dict[str, str]:
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _stored_api_key() -> str:
        if keyring is None:
            return ""
        try:
            return keyring.get_password("RAHU Assistant", "online-provider") or ""
        except Exception:
            return ""

    def configure(self, settings: dict[str, Any]) -> None:
        online_url = self._config_text(settings, "online_url", self.online_url, 500).rstrip("/")
        online_model = self._config_text(settings, "online_model", self.online_model, 120)
        local_url = self._config_text(settings, "local_url", self.local_url, 500).rstrip("/")
        local_model = self._config_text(settings, "local_model", self.local_model, 120)
        api_key = self._config_text(settings, "api_key", "", 2000)

        for label, url in (("online", online_url), ("local", local_url)):
            if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
                raise ValueError(f"The {label} provider URL must use HTTPS or point to localhost.")
        if not online_model or not local_model:
            raise ValueError("Enter a model name for both online and local providers.")

        if api_key:
            if keyring is None:
                raise RuntimeError("Windows Credential Manager is unavailable; set RAHU_AI_API_KEY in your environment instead.")
            keyring.set_password("RAHU Assistant", "online-provider", api_key)
            self.online_key = api_key
        elif settings.get("clear_api_key"):
            if keyring is None:
                raise RuntimeError("Windows Credential Manager is unavailable.")
            try:
                keyring.delete_password("RAHU Assistant", "online-provider")
            except keyring.errors.PasswordDeleteError:
                pass
            self.online_key = ""

        payload = {
            "online_url": online_url,
            "online_model": online_model,
            "local_url": local_url,
            "local_model": local_model,
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.config_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary_path.replace(self.config_path)
        self.online_url = online_url
        self.online_model = online_model
        self.local_url = local_url
        self.local_model = local_model

    @staticmethod
    def _config_text(settings: dict[str, Any], key: str, default: str, limit: int) -> str:
        value = settings.get(key, default)
        return value.strip()[:limit] if isinstance(value, str) else default

    def status(self) -> dict[str, str | bool]:
        local_available = False
        try:
            response = requests.get(f"{self.local_url}/models", timeout=(0.25, 0.5))
            response.raise_for_status()
            models = response.json().get("data", [])
            local_available = any(
                model.get("id", "").casefold() == self.local_model.casefold()
                for model in models
                if isinstance(model, dict)
            )
        except (requests.RequestException, ValueError):
            pass
        return {
            "online_configured": bool(self.online_key),
            "online_url": self.online_url,
            "online_model": self.online_model,
            "local_available": local_available,
            "local_url": self.local_url,
            "local_model": self.local_model,
            "mode": "hybrid",
        }

    def respond(self, request_text: str) -> str | None:
        providers = []
        if self.online_key:
            providers.append((self.online_url, self.online_model, self.online_key))
        providers.append((self.local_url, self.local_model, ""))

        last_error = ""
        for base_url, model, api_key in providers:
            try:
                result = self._run_provider(
                    request_text,
                    base_url,
                    model,
                    api_key,
                    self.conversation_history[-10:],
                )
                if result:
                    self.conversation_history.extend([
                        {"role": "user", "content": request_text[:6000]},
                        {"role": "assistant", "content": result[:6000]},
                    ])
                    self.conversation_history = self.conversation_history[-20:]
                    return result
            except Exception as exc:
                last_error = str(exc)

        if last_error:
            print(f"AI providers are unavailable: {last_error}")
        return None

    def _run_provider(
        self,
        request_text: str,
        base_url: str,
        model: str,
        api_key: str,
        history: list[dict[str, str]],
    ) -> str | None:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        tools = self._tool_definitions()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are RAHU, a careful productivity assistant on the user's Windows computer. "
                    "Understand ordinary language, correct likely speech-recognition typos, and prefer completing a task with the listed tools. "
                    "For general knowledge and conversational questions, answer directly in clear, useful language. Give a brief rationale or important caveat when helpful, but do not provide hidden chain-of-thought. "
                    "Distinguish general knowledge from current facts; do not claim to have browsed unless you used a tool that actually browses. "
                    "Never invent completed actions. Use only the available tools for computer changes; do not request or run shell commands. "
                    "For presentations, create a useful, detailed deck on the user's topic and honor a requested slide count. "
                    "For broad productivity requests, give a concise prioritized plan and a concrete first step. "
                    "Cleaning is preview-only until the user explicitly confirms it in a later message."
                ),
            },
            *history,
            {"role": "user", "content": request_text[:6000]},
        ]
        completed = []

        for _round in range(self.max_tool_rounds):
            payload = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.2,
            }
            try:
                response = requests.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=(5, 30) if api_key else (1, 30),
                )
                response.raise_for_status()
                choices = response.json().get("choices", [])
            except Exception:
                if completed:
                    return "I completed the requested action:\n" + "\n".join(completed)
                raise
            if not choices:
                raise ValueError("The AI provider returned no response choices.")

            message = choices[0].get("message", {})
            calls = message.get("tool_calls") or []
            if not calls:
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
                return "; ".join(completed) if completed else None

            messages.append(message)
            for call in calls:
                function = call.get("function", {})
                name = function.get("name", "")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except (TypeError, json.JSONDecodeError):
                    arguments = {}
                result = self._execute_tool(name, arguments)
                completed.append(result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": result[:4000],
                })

        if completed:
            return "\n".join(completed)
        return None

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            self._tool("open_app", "Open a named installed app.", {"name": {"type": "string"}}, ["name"]),
            self._tool("open_file", "Find and open a local file by name, with or without its extension.", {"name": {"type": "string"}}, ["name"]),
            self._tool("search_web", "Open web search results for a topic.", {"query": {"type": "string"}}, ["query"]),
            self._tool("search_maps", "Open Google Maps, optionally searching a location.", {"location": {"type": "string"}}),
            self._tool("create_presentation", "Create a PowerPoint deck for a topic, optionally with a requested number of slides.", {"topic": {"type": "string"}, "slide_count": {"type": "integer"}}, ["topic"]),
            self._tool("create_word_document", "Create a Word document with a title and useful content.", {"title": {"type": "string"}, "content": {"type": "string"}}, ["title", "content"]),
            self._tool("check_system", "Check local CPU, memory, and disk use.", {}),
            self._tool("clean_temporary_files", "Preview old temporary-file cleanup; actual deletion requires a separate user confirmation.", {}),
        ]

    @staticmethod
    def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
        parameters: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
        if required:
            parameters["required"] = required
        return {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        }

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if not isinstance(arguments, dict):
            return "I couldn't use that action because its arguments were invalid."

        if name == "open_app":
            app_name = self._text_argument(arguments, "name", 120)
            if not app_name:
                return "Tell me which app to open."
            return self.agent.handle_command(f"open {app_name}")

        if name == "open_file":
            filename = self._text_argument(arguments, "name", 260)
            if not filename:
                return "Tell me the file name to find."
            return self.agent.handle_command(f"open file {filename}")

        if name == "search_web":
            query = self._text_argument(arguments, "query", 300)
            if not query:
                return "Tell me what to search for."
            return self.agent.browser.open_url(f"https://www.google.com/search?q={quote(query)}")

        if name == "search_maps":
            location = self._text_argument(arguments, "location", 200)
            if not location:
                return self.agent.browser.open_url("https://www.google.com/maps")
            return self.agent.browser.open_url(
                f"https://www.google.com/maps/search/?api=1&query={quote(location)}"
            )

        if name == "create_presentation":
            topic = self._text_argument(arguments, "topic", 300)
            if not topic:
                return "A presentation needs a topic."
            count = arguments.get("slide_count")
            if isinstance(count, bool) or not isinstance(count, int):
                count = None
            else:
                count = max(3, min(count, 30))
            options: dict[str, Any] = {"folder": str(self.agent.output_directory)}
            if count is not None:
                options["slide_count"] = count
            path = self.agent.automation.create_presentation_from_topic(topic, **options)
            return f"Created the presentation at {path}."

        if name == "create_word_document":
            title = self._text_argument(arguments, "title", 160)
            content = self._text_argument(arguments, "content", 12000)
            if not title or not content:
                return "A document needs a title and content."
            path = self.agent.automation.create_word_document(
                title,
                content,
                folder=str(self.agent.output_directory),
            )
            return f"Created the Word document at {path}."

        if name == "check_system":
            return json.dumps(self.agent.system_manager.assess())

        if name == "clean_temporary_files":
            return self.agent._handle_cleanup("clean junk") or "No cleanup action was started."

        return "That action is not available."

    @staticmethod
    def _text_argument(arguments: dict[str, Any], key: str, limit: int) -> str:
        value = arguments.get(key, "")
        if not isinstance(value, str):
            return ""
        return value.strip()[:limit]