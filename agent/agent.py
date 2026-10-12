from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from config import settings
from .ai_agent import AgenticAI
from .browser_controller import BrowserController
from .desktop_automation import DesktopAutomation
from .desktop_controller import DesktopController
from .desktop_status import ListeningStatusWindow
from .learning_memory import LearningMemory
from .payment_manager import PaymentManager
from .project_planner import ProjectPlanner
from .remote_manager import RemoteConnectionManager
from .system_manager import LaptopSystemManager
from .voice import VoiceController


class LocalAgent:
    def __init__(self, voice_enabled: bool = False) -> None:
        self.settings = settings
        self.voice = VoiceController(enabled=voice_enabled)
        self.voice.set_agent_identity(self.settings.agent_name, self.settings.agent_pronunciation)
        self.desktop = DesktopController()
        self.browser = BrowserController()
        self.automation = DesktopAutomation()
        self.remote = RemoteConnectionManager(self.settings)
        self.payment = PaymentManager(self.settings)
        self.project_planner = ProjectPlanner()
        self.system_manager = LaptopSystemManager()
        self.memory = LearningMemory()
        self.status_window = ListeningStatusWindow()
        self.output_directory = Path.home() / "Documents" / "RAHU Assistant"
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.ai = AgenticAI(self)
        self.voice.on_voice_unavailable = self.hide_listening
        self.running = True
        self.cleanup_confirmation_pending = False

    def set_voice_enabled(self, enabled: bool) -> None:
        self.voice.set_enabled(enabled)
        self.settings.voice_enabled = enabled
        self.settings.save()

    def request_voice_permission(self) -> bool:
        granted = self.voice.request_permission()
        self.settings.voice_enabled = granted
        self.settings.save()
        return granted

    def listen_for_wake_word(self) -> str:
        transcript = self.voice.listen_for_wake_word(self.settings.wake_word)
        if not transcript:
            return ""
        if not self.voice.enabled:
            return transcript
        if self.settings.wake_word.lower() in transcript.lower() or self.settings.agent_name.lower() in transcript.lower():
            return transcript
        return ""

    def show_listening(self, text: str = "RAHU is listening...") -> None:
        self.status_window.show(text)

    def hide_listening(self) -> None:
        self.status_window.close()

    def _handle_payment_request(self, text: str) -> str:
        lower = text.lower()
        if any(word in lower for word in ["daily", "weekly", "monthly"]):
            return self.payment.parse_payment_request(text)
        return self.payment.guidance()

    def _is_cleanup_request(self, lower: str) -> bool:
        action = r"(?:clean|clear|remove|delete)"
        target = r"(?:junk|temporary files?|temp files?|temporary folder|temp folder)"
        return bool(re.search(rf"\b{action}\b.*\b{target}\b|\bfree up (?:some )?(?:disk )?space\b", lower))

    def _handle_cleanup(self, command: str) -> str | None:
        lower = command.casefold().strip()
        if self.cleanup_confirmation_pending:
            if re.fullmatch(r"(?:yes|yeah|yep|confirm|confirm cleanup|do it|go ahead|clean it|yes,? clean it)", lower):
                self.cleanup_confirmation_pending = False
                result = self.system_manager.clean_junk()
                size_mb = result["bytes"] / (1024 * 1024)
                return f"Cleaned {result['files']} old temporary files and freed {size_mb:.1f} MB. Files still in use were skipped."
            if re.fullmatch(r"(?:no|cancel|never mind|nevermind|stop)", lower):
                self.cleanup_confirmation_pending = False
                return "Cleanup cancelled. I left the temporary files untouched."
            self.cleanup_confirmation_pending = False

        if not self._is_cleanup_request(lower):
            return None

        preview = self.system_manager.preview_junk_cleanup()
        size_mb = preview["bytes"] / (1024 * 1024)
        if preview["files"] == 0:
            return "I couldn't find old files to clean in your temporary folder. I didn't touch your documents or downloads."

        self.cleanup_confirmation_pending = True
        return (
            f"I found {preview['files']} temporary files older than one day ({size_mb:.1f} MB) in your user temp folder. "
            "I won't touch documents, downloads, or system folders. Say 'confirm cleanup' to remove them, or 'cancel'."
        )

    def _extract_requested_slide_count(self, text: str) -> int | None:
        numbers = {
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
        }
        match = re.search(r"\b(\d{1,2}|" + "|".join(numbers) + r")(?:\s*-\s*|\s+)slides?\b", text, flags=re.IGNORECASE)
        if not match:
            return None
        value = match.group(1).casefold()
        count = int(value) if value.isdigit() else numbers[value]
        return max(3, min(count, 30))

    def _presentation_output_directory(self, command: str) -> tuple[Path | None, str | None]:
        match = re.search(
            r"\b(?:save|store)\s+(?:it\s+)?(?:in|to|on)\s+(?:the\s+)?([a-z])(?:\s+drive|:)(?:\b|\\)",
            command,
            flags=re.IGNORECASE,
        )
        if not match:
            return self.output_directory, None

        drive_root = Path(f"{match.group(1).upper()}:\\")
        if not drive_root.exists():
            return None, f"I couldn't access drive {match.group(1).upper()}:, so I didn't create the presentation."

        destination = drive_root / "RAHU Assistant"
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return None, f"I couldn't create the output folder on drive {match.group(1).upper()}: ({exc})."
        return destination, None

    def _strip_name_prefix(self, text: str) -> str:
        command = (text or "").strip()
        if not command:
            return ""

        lower = command.lower()
        wake_word = self.settings.wake_word.lower()
        agent_name = self.settings.agent_name.lower()

        if lower.startswith(wake_word):
            return command[len(wake_word):].strip(" ,.-:;!?")
        if lower.startswith(agent_name):
            return command[len(agent_name):].strip(" ,.-:;!?")
        return command

    def _normalize_command(self, command: str) -> str:
        corrections = {
            "presenation": "presentation",
            "presentaion": "presentation",
            "presention": "presentation",
            "managment": "management",
            "mangement": "management",
        }
        return re.sub(
            r"\b(" + "|".join(corrections) + r")\b",
            lambda match: corrections[match.group(0).casefold()],
            command,
            flags=re.IGNORECASE,
        )

    def _extract_topic(self, text: str, keywords: list[str]) -> str:
        clean = text.strip()
        clean = re.sub(r"^(?:please\s+)?(?:(?:can|could) you\s+)?(?:kindly\s+)?(?:help me\s+)?", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"^(?:make|create|build|generate|draft)\s+(?:me\s+)?(?:(?:the|a)\s+)?", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"^(?:(?:the|a)\s+)?(?:power\s*point\s+)?(?:presentation|ppt|slide deck)\s+", "", clean, flags=re.IGNORECASE)
        match = re.search(r"\b(?:about|for|on|regarding|of)\s+(.+)$", clean, flags=re.IGNORECASE)
        if match:
            topic = re.split(
                r"\b(?:which|that)\s+(?:will|would|can)\b|\busing\s+(?:power\s*point|powerpoint)\b|\b(?:save|store)\s+(?:it\s+)?(?:in|to|on)\b",
                match.group(1),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
            topic = re.sub(r"[^a-z0-9\s-]", " ", topic)
            topic = " ".join(topic.split())
            if topic:
                return topic.title()

        for keyword in keywords:
            clean = re.sub(rf"\b{re.escape(keyword)}\b", " ", clean, flags=re.IGNORECASE)
        clean = re.sub(r"[^a-z0-9\s-]", " ", clean, flags=re.IGNORECASE)
        clean = " ".join(clean.split())
        return clean.title() if clean else "Project Update"

    def _open_named_path(self, target: str) -> str | None:
        matches = self.desktop.find_paths_by_name(target)
        if not matches:
            return None
        if len(matches) > 1:
            locations = "\n".join(f"- {path}" for path in matches)
            return f"I found multiple matches for '{target}'. Choose one by its folder or file name:\n{locations}"
        try:
            return self.desktop.open_file(str(matches[0]))
        except FileNotFoundError:
            return None

    def _handle_file_search(self, command: str) -> str | None:
        match = re.match(
            r"^(?:find|locate|search for)\s+(?:the\s+)?(?:file|folder)\s+(?:named\s+|called\s+)?(.+)$",
            command,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        target = match.group(1).strip().strip('"')
        matches = self.desktop.find_paths_by_name(target)
        if not matches:
            return f"I couldn't find '{target}' in your user folders or the current project."
        return "Matching files and folders:\n" + "\n".join(f"- {path}" for path in matches)

    def _handle_direct_open(self, command: str, lower: str) -> str | None:
        match = re.match(r"^(?:.*?\b)?(?:open|launch|start)\s+(?:the\s+)?(.+)$", lower)
        if not match:
            return None

        target = match.group(1).strip()
        if not target:
            return None

        kind_match = re.match(r"^(?:(?:the|a)\s+)?(file|folder)\s+", target)
        explicit_path_search = kind_match is not None
        if kind_match is not None:
            target = target[kind_match.end():].strip()
        else:
            target = re.sub(r"^app\s+", "", target).strip()
        target = re.sub(r"^(?:named|called)\s+", "", target).strip()
        if not target or target in {"file", "folder"}:
            return "Tell me the name of the file or folder to open."

        map_match = re.match(r"^maps?(?:\s+of)?(?:\s+(.*))?$", target)
        if map_match:
            location = (map_match.group(1) or "").strip()
            url = (
                f"https://www.google.com/maps/search/?api=1&query={quote(location)}"
                if location
                else "https://www.google.com/maps"
            )
            return self.browser.open_url(url)

        if any(word in target for word in ["browser", "website", "site", "google", "youtube", "facebook", "linkedin"]):
            site = target.replace("browser", "").replace("website", "").replace("site", "").strip()
            if not site:
                site = "google.com"
            return self.browser.open_url(site)

        if any(word in target for word in ["job", "jobs", "career", "careers"]):
            keyword = target.replace("job", "").replace("jobs", "").replace("career", "").replace("careers", "").strip()
            return self.automation.open_job_search(keyword or "remote jobs")

        filename_like = bool(re.search(r"\.[a-z0-9]{1,8}$", target))
        if explicit_path_search or filename_like:
            result = self._open_named_path(target)
            if result is not None:
                return result
            return f"I couldn't find '{target}' in your user folders or the current project."

        result = self.desktop.open_app(target)
        if result.startswith("Could not open app from name:"):
            path_result = self._open_named_path(target)
            if path_result is not None:
                return path_result
            return f"I couldn't find '{target}' as an app, file, or folder in your user folders or the current project."
        self.voice.speak(result)
        return result

    def _handle_direct_search(self, command: str, lower: str) -> str | None:
        if not re.match(r"^(?:.*?\b)?(?:search|find|look for|research)\s+", lower):
            return None

        phrase = re.sub(r"^(?:.*?\b)?(?:search|find|look for|research)\s+", "", lower).strip()
        if not phrase:
            return None

        if any(word in phrase for word in ["job", "jobs", "career", "careers"]):
            keyword = re.sub(r"\b(job|jobs|career|careers)\b", "", phrase).strip()
            return self.automation.open_job_search(keyword or "remote jobs")

        if any(word in phrase for word in ["website", "site", "web", "google", "youtube"]):
            search_term = re.sub(r"\b(website|site|web|google|youtube)\b", "", phrase).strip() or "latest updates"
            return self.browser.open_url(search_term)

        search_term = re.sub(r"^(?:about|for|the web for)\s+", "", phrase).strip()
        search_term = re.sub(r"^(?:the\s+)?", "", search_term).strip()
        if not search_term:
            return "What would you like me to search for?"

        map_match = re.match(r"^maps?(?:\s+of)?(?:\s+(.*))?$", search_term)
        if map_match:
            location = (map_match.group(1) or "").strip()
            if location:
                url = f"https://www.google.com/maps/search/?api=1&query={quote(location)}"
            else:
                url = "https://www.google.com/maps"
            return self.browser.open_url(url)

        return self.browser.open_url(f"https://www.google.com/search?q={quote(search_term)}")

    def handle_command(self, text: str) -> str:
        command = (text or "").strip()
        if not command:
            return "I am ready to help. Tell me what you want me to do on this laptop."

        command = self._normalize_command(self._strip_name_prefix(command))
        lower = command.lower()

        if not command:
            return f"Yes, I am {self.settings.agent_name}. How can I help you?"

        context_hint = self.memory.build_context(command)
        self.memory.record(command)

        cleanup_response = self._handle_cleanup(command)
        if cleanup_response is not None:
            return cleanup_response

        file_search = self._handle_file_search(command)
        if file_search is not None:
            return file_search

        direct_open = self._handle_direct_open(command, lower)
        if direct_open is not None:
            self.memory.record(command, direct_open)
            return direct_open

        direct_search = self._handle_direct_search(command, lower)
        if direct_search is not None:
            self.memory.record(command, direct_search)
            return direct_search

        if "open browser" in lower or "open website" in lower or "visit" in lower:
            match = re.search(r"(?:open|visit|browse)\s+(?:website\s+)?(.+)", lower)
            target = match.group(1).strip() if match else ""
            if not target:
                return "Please tell me which website you want to open."
            return self.browser.open_url(target)

        if "run command" in lower or "execute" in lower:
            match = re.search(r"(?:run|execute)\s+(.*)", lower)
            script = match.group(1).strip() if match else ""
            if not script:
                return "Please tell me the command you want me to run."
            result = self.desktop.run_command(script)
            self.voice.speak(result)
            return result

        if "open app" in lower or "launch app" in lower:
            match = re.search(r"(?:open|launch)\s+(?:app\s+)?(.+)", lower)
            app_name = match.group(1).strip() if match else ""
            if not app_name:
                return "Please tell me which application you want to open."
            result = self.desktop.open_app(app_name)
            self.voice.speak(result)
            return result

        if ("list" in lower and "folder" in lower) or "list files" in lower or "show files" in lower:
            folder = re.search(r"(?:in|from|at)\s+(.+)$", lower)
            folder_name = folder.group(1).strip() if folder else "."
            try:
                return self.desktop.list_directory(folder_name)
            except FileNotFoundError:
                return f"I could not find the folder: {folder_name}"

        if "connect" in lower and ("phone" in lower or "remote" in lower or "device" in lower):
            return self.remote.request_permission()

        if "approve" in lower and ("connection" in lower or "device" in lower):
            return self.remote.approve_connection()

        if "disconnect" in lower and ("device" in lower or "phone" in lower or "remote" in lower):
            return self.remote.disconnect()

        if ("terminate" in lower or "stop" in lower) and ("agent" in lower or "session" in lower):
            self.running = False
            return "The local agent session is being terminated."

        presentation_request = (
            re.search(r"\b(?:ppt|powerpoint|presentation|slide deck|slides?)\b", lower)
            and re.search(r"\b(?:make|create|build|generate|draft|prepare|need|want)\b", lower)
        ) or "presentation about" in lower or "presentation on" in lower or "ppt about" in lower
        if presentation_request:
            slide_count = self._extract_requested_slide_count(command)
            topic_command = re.sub(
                r"\b(?:with\s+)?(?:\d{1,2}|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)(?:\s*-\s*|\s+)slides?\b",
                " ",
                command,
                flags=re.IGNORECASE,
            )
            title = self._extract_topic(topic_command, ["powerpoint", "presentation", "ppt", "make", "create", "about", "for", "on"])
            output_directory, output_error = self._presentation_output_directory(command)
            if output_error:
                return output_error
            options = {"folder": str(output_directory)}
            if slide_count is not None:
                options["slide_count"] = slide_count
            result = self.automation.create_presentation_from_topic(title, **options)
            return f"I created the presentation file here: {result}"

        if (
            "make word" in lower
            or "create word" in lower
            or "create document" in lower
            or "make document" in lower
            or "word document" in lower
            or "document about" in lower
        ):
            title = self._extract_topic(command, ["document", "word", "make", "create", "about", "for", "on"])
            body = (
                f"This document was created by RAHU for {title}.\n\n"
                "Summary:\n- Review the task\n- Complete the objective\n- Save the progress\n- Share updates"
            )
            result = self.automation.create_word_document(title, body, folder=str(self.output_directory))
            return f"I created the Word document here: {result}"

        if "search for job" in lower or "find job" in lower or "job search" in lower or "look for jobs" in lower:
            keyword = "remote jobs"
            if "for" in lower:
                keyword = lower.split("for", 1)[1].strip()
            if not keyword or keyword in {"job", "jobs"}:
                keyword = "remote jobs"
            result = self.automation.open_job_search(keyword)
            return result

        if "slow" in lower or "lag" in lower or "performance" in lower or "laptop is slow" in lower or "computer is slow" in lower:
            return self.system_manager.suggestions()

        if "optimize" in lower and "laptop" in lower or "optimize" in lower and "computer" in lower:
            return self.system_manager.optimize()

        if "recommend" in lower or "project" in lower or "income" in lower or "earn money" in lower:
            projects = self.project_planner.get_recommendations()
            summary = "Here are some practical ways to earn money: "
            summary += "; ".join(f"{item['title']} ({item['income_potential']})" for item in projects[:3])
            return summary

        if "payment" in lower or "pay" in lower or "salary" in lower or "receive" in lower:
            return self._handle_payment_request(command)

        if "hello" in lower or "hi" in lower:
            greeting = (
                f"Hello, I am {self.settings.agent_name}. I am your local personal assistant and I can manage files, "
                "open apps, run commands, organize your work, and help you grow your income."
            )
            self.voice.speak(greeting)
            return greeting

        if "help" in lower:
            return (
                f"I am {self.settings.agent_name}, and I can open files, launch apps, run commands, check folders, "
                "find files by name, create detailed Word and PowerPoint documents, clean old temporary files with your approval, "
                "search for jobs, open websites, check your system, manage remote access permissions, and keep your payment schedule organized. "
                "For example: 'open Microsoft Store', 'clean junk', or 'prepare a 12-slide presentation on solar energy'."
            )

        ai_response = self.ai.respond(command)
        if ai_response:
            self.memory.record(command, ai_response)
            return ai_response

        ai_status = self.ai.status()
        if not ai_status["online_configured"] and not ai_status["local_available"]:
            return (
                "I can chat and answer general questions when an AI model is connected, but none is configured right now. "
                "Open the AI connection panel and save an online API key, or install Ollama and its local model. "
                "My built-in app, file, and desktop tools are still available."
            )

        friendly = (
            f"I couldn't confidently match that request to an available action. I can open Windows apps, find files by name, "
            "create detailed Word or PowerPoint files, search the web, check system performance, clean old temporary files with your approval, "
            "and manage your payment plan or remote connection. Try: 'open Microsoft Store', 'clean junk', or 'prepare a 12-slide presentation on solar energy'."
        )
        if context_hint:
            friendly += " " + context_hint
        self.memory.record(command, friendly)
        self.voice.speak(friendly)
        return friendly

    def status(self) -> dict:
        return {
            "running": self.running,
            "voice_enabled": self.voice.enabled,
            "remote": self.remote.status(),
            "payment": {
                "schedule": self.settings.payment_schedule,
                "method": self.settings.default_payment_method,
            },
            "ai": self.ai.status(),
        }

    def run_console(self) -> None:
        print(f"{self.settings.agent_name} is ready. Type 'exit' to quit.")
        while self.running:
            try:
                self.show_listening("RAHU is listening...")
                if self.voice.enabled:
                    detected = self.listen_for_wake_word()
                    if not detected:
                        continue
                    if self.settings.wake_word.lower() in detected.lower() or self.settings.agent_name.lower() in detected.lower():
                        command = detected.replace(self.settings.wake_word, "", 1)
                        command = command.replace(self.settings.agent_name, "", 1)
                        user_input = command.strip()
                        if not user_input:
                            user_input = self.voice.listen_for_command_after_wake(self.settings.wake_word)
                    else:
                        user_input = detected
                else:
                    user_input = input("You: ").strip()
            except EOFError:
                print("\nSession closed.")
                self.running = False
                break
            except KeyboardInterrupt:
                print("\nSession interrupted.")
                self.running = False
                break

            self.hide_listening()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "bye"}:
                self.running = False
                print("Goodbye.")
                break
            response = self.handle_command(user_input)
            print(f"{self.settings.agent_name}: {response}")
            self.voice.speak(response)
            print(f"{self.settings.agent_name}: Anything else I can do for you?")
            self.voice.speak("Anything else I can do for you?")

    def run_voice_loop(self) -> None:
        if not self.voice.enabled:
            print("Voice mode is disabled. Use --voice to enable microphone assistance.")
            return

        self.show_listening(f"{self.settings.agent_name} is ready")
        self.voice.speak(f"Hello, I am {self.settings.agent_name}. I am ready to help you.")
        print(f"{self.settings.agent_name} voice loop is active. Say '{self.settings.wake_word}' to begin.")

        while self.running and self.voice.enabled:
            self.show_listening(f"Listening for: {self.settings.wake_word}")
            transcript = self.listen_for_wake_word()
            if not transcript:
                continue
            if self.voice.enabled:
                if self.settings.wake_word.lower() not in transcript.lower() and self.settings.agent_name.lower() not in transcript.lower():
                    continue
                after_wake = transcript.replace(self.settings.wake_word, "", 1)
                after_wake = after_wake.replace(self.settings.agent_name, "", 1)
                command = after_wake.strip()
                if not command:
                    command = self.voice.listen_for_command_after_wake(self.settings.wake_word)
            else:
                command = transcript.strip()

            self.hide_listening()

            if command.lower() in {"exit", "quit", "bye"}:
                self.running = False
                self.voice.speak("Goodbye.")
                print("Goodbye.")
                break

            response = self.handle_command(command)
            print(f"{self.settings.agent_name}: {response}")
            self.voice.speak(response)
            print(f"{self.settings.agent_name}: Anything else I can do for you?")
            self.voice.speak("Anything else I can do for you?")

    def build_prompt(self) -> str:
        return (
            f"You are {self.settings.agent_name}, a local personal AI assistant for this computer. Speak in clear English, "
            "be polite, and focus on helping the user with daily work, project planning, and money-making tasks."
        )
