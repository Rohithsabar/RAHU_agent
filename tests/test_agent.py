import unittest
import threading
import tempfile
import os
import time
from pathlib import Path
import requests
from zipfile import ZipFile
from lxml import etree
from unittest.mock import MagicMock, patch

from agent.agent import LocalAgent
from agent.desktop_automation import DesktopAutomation, Presentation as PowerPoint
from agent.desktop_status import ListeningStatusWindow
from agent.desktop_controller import DesktopController
from agent.ai_agent import AgenticAI
from agent.voice import VoiceController


class LocalAgentCommandTests(unittest.TestCase):
    def test_direct_app_launch_is_supported(self):
        agent = LocalAgent(voice_enabled=False)
        response = agent.handle_command("open notepad")
        self.assertIn("Opened app", response)

    def test_microsoft_store_uses_windows_app_protocol(self):
        desktop = DesktopController()
        with patch("agent.desktop_controller.os.name", "nt"), patch(
            "agent.desktop_controller.os.startfile",
            create=True,
        ) as startfile:
            response = desktop.open_app("Microsoft Store")

        self.assertEqual(response, "Opened app: Microsoft Store")
        startfile.assert_called_once_with("ms-windows-store:")

    def test_ai_uses_local_fallback_and_returns_productivity_response(self):
        agent = LocalAgent(voice_enabled=False)
        agent.ai.online_key = ""
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": "Prioritize the top three tasks, then schedule focused work."}}]
        }
        with patch("agent.ai_agent.requests.post", return_value=response) as post:
            result = agent.ai.respond("Help me plan my workday")

        self.assertIn("Prioritize", result)
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:11434/v1/chat/completions")

    def test_ai_configuration_saves_secret_to_credential_store_only(self):
        agent = LocalAgent(voice_enabled=False)
        with tempfile.TemporaryDirectory() as folder, patch("agent.ai_agent.keyring.set_password") as set_password:
            agent.ai.config_path = Path(folder) / "ai_settings.json"
            agent.ai.configure({
                "online_url": "https://api.example.com/v1",
                "online_model": "assistant-model",
                "api_key": "test-secret-value",
                "local_url": "http://127.0.0.1:11434/v1",
                "local_model": "qwen2.5:7b",
            })
            saved_settings = agent.ai.config_path.read_text(encoding="utf-8")

        set_password.assert_called_once_with("RAHU Assistant", "online-provider", "test-secret-value")
        self.assertNotIn("test-secret-value", saved_settings)
        self.assertEqual(agent.ai.online_model, "assistant-model")

    def test_clean_ai_setup_defaults_to_gemini_free_tier(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(AgenticAI, "_load_settings", return_value={}), patch.object(
            AgenticAI,
            "_stored_api_key",
            return_value="",
        ), patch.dict(os.environ, {
            "RAHU_AI_BASE_URL": "",
            "RAHU_AI_MODEL": "",
            "RAHU_AI_API_KEY": "",
            "OPENAI_API_KEY": "",
        }):
            online = AgenticAI(agent)

        self.assertEqual(online.online_url, "https://generativelanguage.googleapis.com/v1beta/openai")
        self.assertEqual(online.online_model, "gemini-3.8-flash")
        self.assertFalse(online.online_key)

    def test_ai_configuration_rejects_remote_plain_http(self):
        agent = LocalAgent(voice_enabled=False)
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            agent.ai.configure({"online_url": "http://example.com/v1"})

    def test_ai_configuration_can_remove_saved_online_credential(self):
        agent = LocalAgent(voice_enabled=False)
        agent.ai.online_key = "configured-test-key"
        with patch("agent.ai_agent.keyring.delete_password") as delete_password:
            agent.ai.configure({"clear_api_key": True})

        delete_password.assert_called_once_with("RAHU Assistant", "online-provider")
        self.assertEqual(agent.ai.online_key, "")

    def test_ai_settings_without_key_do_not_claim_credential_was_saved(self):
        import app as web_app

        previous_key = web_app.agent.ai.online_key
        web_app.agent.ai.online_key = ""
        try:
            response = web_app.app.test_client().post("/api/ai/config", json={
                "online_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "online_model": "gemini-3.8-flash",
                "local_url": "http://127.0.0.1:11434/v1",
                "local_model": "qwen2.5:7b",
            })
        finally:
            web_app.agent.ai.online_key = previous_key

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add an API key", response.get_json()["message"])

    def test_mobile_dashboard_requires_pairing_before_api_access(self):
        import app as web_app

        previous_enabled = web_app.mobile_access_enabled
        previous_code = web_app.mobile_pairing_code
        web_app.mobile_access_enabled = True
        web_app.mobile_pairing_code = "12345678"
        web_app.pairing_failures.clear()
        try:
            client = web_app.app.test_client()
            remote = {"REMOTE_ADDR": "192.168.1.20"}
            landing = client.get("/", environ_base=remote)
            self.assertIn(b"Connect this phone", landing.data)
            self.assertNotIn(b"12345678", landing.data)
            self.assertEqual(client.get("/api/status", environ_base=remote).status_code, 401)

            paired = client.post("/api/pair", json={"code": "12345678"}, environ_base=remote)
            self.assertEqual(paired.status_code, 200)
            self.assertEqual(client.get("/api/status", environ_base=remote).status_code, 200)
        finally:
            web_app.mobile_access_enabled = previous_enabled
            web_app.mobile_pairing_code = previous_code
            web_app.pairing_failures.clear()

    def test_unknown_chat_request_explains_ai_setup_when_no_model_is_available(self):
        agent = LocalAgent(voice_enabled=False)
        agent.ai.online_key = ""
        with patch.object(agent.ai, "status", return_value={"online_configured": False, "local_available": False}):
            response = agent.handle_command("Explain how photosynthesis works")

        self.assertIn("none is configured right now", response)
        self.assertIn("AI connection panel", response)

    def test_general_chat_request_uses_model_answer(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(agent.ai, "respond", return_value="Photosynthesis converts light into stored chemical energy."):
            response = agent.handle_command("Explain photosynthesis simply")

        self.assertEqual(response, "Photosynthesis converts light into stored chemical energy.")

    def test_ai_keeps_context_for_follow_up_requests(self):
        agent = LocalAgent(voice_enabled=False)
        agent.ai.online_key = ""
        first = MagicMock()
        first.json.return_value = {"choices": [{"message": {"content": "I planned three work blocks."}}]}
        second = MagicMock()
        second.json.return_value = {"choices": [{"message": {"content": "The first block was email."}}]}
        with patch("agent.ai_agent.requests.post", side_effect=[first, second]) as post:
            agent.ai.respond("Plan my workday")
            agent.ai.respond("What was my first block?")

        second_messages = post.call_args.kwargs["json"]["messages"]
        self.assertTrue(any(message.get("content") == "Plan my workday" for message in second_messages))
        self.assertTrue(any(message.get("content") == "I planned three work blocks." for message in second_messages))

    def test_ai_tool_loop_creates_requested_presentation(self):
        agent = LocalAgent(voice_enabled=False)
        agent.ai.online_key = ""
        action_response = MagicMock()
        action_response.json.return_value = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call-1",
                        "function": {
                            "name": "create_presentation",
                            "arguments": '{"topic":"Hospital Management System","slide_count":12}',
                        },
                    }],
                }
            }]
        }
        final_response = MagicMock()
        final_response.json.return_value = {"choices": [{"message": {"content": "The 12-slide deck is ready."}}]}
        with patch("agent.ai_agent.requests.post", side_effect=[action_response, final_response]) as post, patch.object(
            agent.automation,
            "create_presentation_from_topic",
            return_value=str(agent.output_directory / "hospital.pptx"),
        ) as create:
            result = agent.ai.respond("Please create a presentation for a hospital management system")

        self.assertEqual(result, "The 12-slide deck is ready.")
        create.assert_called_once_with(
            "Hospital Management System",
            folder=str(agent.output_directory),
            slide_count=12,
        )
        self.assertEqual(post.call_count, 2)
        self.assertNotIn("run_command", {item["function"]["name"] for item in agent.ai._tool_definitions()})

    def test_ai_provider_failure_after_tool_does_not_repeat_side_effect(self):
        agent = LocalAgent(voice_enabled=False)
        agent.ai.online_key = "configured-test-key"
        action_response = MagicMock()
        action_response.json.return_value = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call-1",
                        "function": {
                            "name": "create_presentation",
                            "arguments": '{"topic":"Solar Energy","slide_count":10}',
                        },
                    }],
                }
            }]
        }
        with patch(
            "agent.ai_agent.requests.post",
            side_effect=[action_response, requests.ConnectionError("provider stopped responding")],
        ) as post, patch.object(
            agent.automation,
            "create_presentation_from_topic",
            return_value=str(agent.output_directory / "solar.pptx"),
        ) as create:
            result = agent.ai.respond("Create a solar presentation")

        create.assert_called_once()
        self.assertIn("solar.pptx", result)
        self.assertEqual(post.call_count, 2)

    def test_direct_job_search_is_supported(self):
        agent = LocalAgent(voice_enabled=False)
        response = agent.handle_command("search for python jobs")
        self.assertIn("Opened job search", response)

    def test_misspelled_presentation_request_is_understood(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(agent.automation, "create_presentation_from_topic", return_value="hospital.pptx") as create:
            response = agent.handle_command("make presenation for hospital managment system")

        self.assertIn("hospital.pptx", response)
        create.assert_called_once_with("Hospital Management System", folder=str(agent.output_directory))

    def test_search_about_topic_opens_web_results(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(agent.browser, "open_url", return_value="opened search") as open_url:
            response = agent.handle_command("search about gods eye")

        self.assertEqual(response, "opened search")
        open_url.assert_called_once_with("https://www.google.com/search?q=gods%20eye")

    def test_search_map_opens_maps(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(agent.browser, "open_url", return_value="opened maps") as open_url:
            response = agent.handle_command("search map")

        self.assertEqual(response, "opened maps")
        open_url.assert_called_once_with("https://www.google.com/maps")

    def test_open_map_opens_google_maps(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(agent.browser, "open_url", return_value="opened maps") as open_url:
            response = agent.handle_command("open map")

        self.assertEqual(response, "opened maps")
        open_url.assert_called_once_with("https://www.google.com/maps")

    def test_sentence_command_with_wake_word(self):
        agent = LocalAgent(voice_enabled=False)
        response = agent.handle_command("hey RAHU open notepad")
        self.assertIn("Opened app", response)

    def test_sentence_command_for_ppt_generation(self):
        agent = LocalAgent(voice_enabled=False)
        response = agent.handle_command("please make a PowerPoint presentation about remote work productivity")
        self.assertIn("presentation", response.lower())
        self.assertIn("here", response.lower())

    def test_learning_memory_remembers_user_preferences(self):
        from agent.learning_memory import LearningMemory

        memory = LearningMemory()
        memory.record("open notepad every morning")
        memory.record("make a ppt about remote work productivity")
        learned = memory.get_preference("routine")
        self.assertTrue(len(learned) >= 1)
        self.assertIn("notepad", " ".join(learned).lower())

    def test_agent_uses_memory_for_context(self):
        agent = LocalAgent(voice_enabled=False)
        agent.memory.record("make a presentation about remote work productivity")
        suggestion = agent.memory.get_preference("project")
        self.assertTrue(any("remote" in item.lower() for item in suggestion))

    def test_voice_permission_prompt_allows_microphone(self):
        controller = VoiceController(enabled=False)
        with patch("agent.voice._confirm_microphone_permission", return_value=True), patch("agent.voice.sr", object()):
            self.assertTrue(controller.request_permission())
            self.assertTrue(controller.enabled)

    def test_voice_permission_dialog_can_be_denied(self):
        controller = VoiceController(enabled=False)
        with patch("agent.voice._confirm_microphone_permission", return_value=False):
            self.assertFalse(controller.request_permission())
            self.assertFalse(controller.enabled)

    def test_spoken_agent_name_uses_saved_pronunciation(self):
        controller = VoiceController(enabled=False)
        controller.set_agent_identity("RAHU", "Rahu")

        self.assertEqual(controller._spoken_text("Hello, I am RAHU."), "Hello, I am Rahu.")

    def test_voice_loop_processes_typed_command_after_microphone_failure(self):
        agent = LocalAgent(voice_enabled=False)
        agent.voice.enabled = True

        def microphone_failure() -> str:
            agent.voice.enabled = False
            return "open budget"

        def handle_typed_command(command: str) -> str:
            agent.running = False
            return f"handled {command}"

        with patch.object(agent, "listen_for_wake_word", side_effect=microphone_failure), patch.object(
            agent,
            "handle_command",
            side_effect=handle_typed_command,
        ) as handle_command, patch.object(agent.voice, "speak"), patch.object(agent, "show_listening"), patch.object(
            agent,
            "hide_listening",
        ):
            agent.run_voice_loop()

        handle_command.assert_called_once_with("open budget")

    def test_listening_waveform_animates_only_while_listening(self):
        window = ListeningStatusWindow()
        window.root = MagicMock()
        window.wave_canvas = MagicMock()
        window._wave_bars = [1, 2]
        window._listening = True

        window._animate_wave()

        self.assertEqual(window.wave_canvas.coords.call_count, 2)
        self.assertEqual(window.wave_canvas.itemconfigure.call_args_list[0].kwargs["fill"], "#38bdf8")
        window._listening = False
        window._animate_wave()
        self.assertEqual(window.wave_canvas.itemconfigure.call_args_list[-1].kwargs["fill"], "#475569")

    def test_wake_word_voice_failure_falls_back_to_typed_command(self):
        controller = VoiceController(enabled=True)
        voice_unavailable = MagicMock()
        controller.on_voice_unavailable = voice_unavailable
        recognition = type("Recognition", (), {"Recognizer": lambda: None, "Microphone": lambda: None})
        with patch("agent.voice.sr", recognition), patch("builtins.input", return_value="open notepad"):
            self.assertEqual(controller.listen_for_wake_word(), "open notepad")
        self.assertFalse(controller.enabled)
        voice_unavailable.assert_called_once_with()

    def test_typed_command_does_not_require_wake_word_when_voice_is_disabled(self):
        agent = LocalAgent(voice_enabled=False)
        with patch("builtins.input", return_value="open notepad"):
            self.assertEqual(agent.listen_for_wake_word(), "open notepad")

    def test_status_window_updates_from_worker_are_queued(self):
        status_window = ListeningStatusWindow()
        with patch("agent.desktop_status.tk") as tkinter:
            worker = threading.Thread(target=status_window.show, args=("Listening",))
            worker.start()
            worker.join()
            tkinter.Tk.assert_not_called()

        self.assertEqual(status_window._actions.get_nowait(), ("show", "Listening"))

    def test_file_search_matches_a_name_without_a_path(self):
        with tempfile.TemporaryDirectory() as folder:
            expected = Path(folder) / "Meeting Notes.docx"
            expected.write_text("test", encoding="utf-8")

            matches = DesktopController().find_paths_by_name(
                "meeting notes",
                roots=[Path(folder)],
            )

        self.assertEqual(matches, [expected])

    def test_open_file_command_resolves_name_before_opening(self):
        agent = LocalAgent(voice_enabled=False)
        expected = Path("D:/Documents/budget.xlsx")
        with (
            patch.object(agent.desktop, "find_paths_by_name", return_value=[expected]),
            patch.object(agent.desktop, "open_file", return_value=f"Opened file: {expected}") as open_file,
        ):
            response = agent.handle_command("open file budget")

        self.assertIn("Opened file", response)
        open_file.assert_called_once_with(str(expected))

    def test_bare_open_name_searches_after_app_launch_fails(self):
        agent = LocalAgent(voice_enabled=False)
        expected = Path("D:/Documents/meeting-notes")
        with patch.object(
            agent.desktop,
            "open_app",
            return_value="Could not open app from name: meeting-notes.",
        ), patch.object(
            agent.desktop,
            "find_paths_by_name",
            return_value=[expected],
        ), patch.object(
            agent.desktop,
            "open_file",
            return_value=f"Opened file: {expected}",
        ) as open_file:
            response = agent.handle_command("open meeting-notes")

        self.assertIn("Opened file", response)
        open_file.assert_called_once_with(str(expected))

    def test_presentation_request_understands_on_topic_wording(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(agent.automation, "create_presentation_from_topic", return_value="solar.pptx") as create:
            response = agent.handle_command("make me a presentation on solar energy")

        self.assertIn("solar.pptx", response)
        create.assert_called_once_with("Solar Energy", folder=str(agent.output_directory))

    def test_presentation_request_passes_requested_slide_count(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(agent.automation, "create_presentation_from_topic", return_value="solar.pptx") as create:
            response = agent.handle_command("prepare a 12-slide presentation on solar energy")

        self.assertIn("solar.pptx", response)
        create.assert_called_once_with("Solar Energy", folder=str(agent.output_directory), slide_count=12)

    def test_presentation_slide_count_at_end_keeps_topic_clean(self):
        agent = LocalAgent(voice_enabled=False)
        with patch.object(agent.automation, "create_presentation_from_topic", return_value="solar.pptx") as create:
            agent.handle_command("make a presentation on solar energy with 12 slides")

        create.assert_called_once_with("Solar Energy", folder=str(agent.output_directory), slide_count=12)

    def test_full_hospital_presentation_request_extracts_topic_count_and_d_drive(self):
        agent = LocalAgent(voice_enabled=False)
        request = (
            "make the presentation of hospital management system which will have the pipeline of how to design "
            "and what facilities will be available for the system design using power point of seven slides "
            "and make good color using background and animations to the slides make it store in D drive"
        )
        with patch.object(agent, "_presentation_output_directory", return_value=(Path("D:/RAHU Assistant"), None)), patch.object(
            agent.automation,
            "create_presentation_from_topic",
            return_value="D:/RAHU Assistant/Hospital_Management_System.pptx",
        ) as create:
            response = agent.handle_command(request)

        self.assertIn("D:/RAHU Assistant", response)
        create.assert_called_once_with(
            "Hospital Management System",
            folder="D:\\RAHU Assistant",
            slide_count=7,
        )

    @unittest.skipIf(PowerPoint is None, "python-pptx is unavailable")
    def test_hospital_deck_has_seven_styled_slides_and_fade_transitions(self):
        automation = DesktopAutomation()
        with tempfile.TemporaryDirectory() as folder:
            path = automation.create_presentation_from_topic(
                "Hospital Management System",
                folder=folder,
                slide_count=7,
            )
            presentation = PowerPoint(path)

            self.assertEqual(len(presentation.slides), 7)
            self.assertEqual(presentation.slide_width, 12191695)
            self.assertEqual(presentation.slides[1].shapes.title.text, "01  |  Vision and Users")
            self.assertEqual(presentation.slides[4].shapes.title.text, "04  |  Patient Care Pipeline")
            self.assertEqual(presentation.slides[5].shapes.title.text, "05  |  Design and Delivery Pipeline")
            with ZipFile(path) as archive:
                slide_xml = etree.fromstring(archive.read("ppt/slides/slide5.xml"))

        namespace = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
        self.assertIsNotNone(slide_xml.find("p:transition/p:fade", namespace))

    def test_clean_junk_requires_confirmation_and_only_removes_old_temp_files(self):
        agent = LocalAgent(voice_enabled=False)
        with tempfile.TemporaryDirectory() as folder:
            temp_root = Path(folder)
            old_file = temp_root / "old.tmp"
            new_file = temp_root / "new.tmp"
            old_file.write_text("old", encoding="utf-8")
            new_file.write_text("new", encoding="utf-8")
            old_time = time.time() - (2 * 24 * 60 * 60)
            os.utime(old_file, (old_time, old_time))
            agent.system_manager.temp_directory = temp_root

            preview = agent.handle_command("clean junk")
            self.assertIn("confirm cleanup", preview.lower())
            self.assertTrue(old_file.exists())

            result = agent.handle_command("confirm cleanup")
            self.assertIn("Cleaned 1 old temporary files", result)
            self.assertFalse(old_file.exists())
            self.assertTrue(new_file.exists())

    @unittest.skipIf(PowerPoint is None, "python-pptx is unavailable")
    def test_topic_presentation_creates_multiple_slides(self):
        automation = DesktopAutomation()
        with tempfile.TemporaryDirectory() as folder, patch.object(
            automation,
            "research_topic",
            return_value=["Solar energy facts.", "Solar energy benefits.", "Solar energy challenges."],
        ):
            path = automation.create_presentation_from_topic("solar energy", folder=folder)
            presentation = PowerPoint(path)

        self.assertEqual(len(presentation.slides), 10)
        self.assertEqual(presentation.slides[1].shapes.title.text, "Executive Overview")
        self.assertEqual(presentation.slides[9].shapes.title.text, "Success Measures and Conclusion")

    @unittest.skipIf(PowerPoint is None, "python-pptx is unavailable")
    def test_topic_presentation_respects_requested_total_slide_count(self):
        automation = DesktopAutomation()
        with tempfile.TemporaryDirectory() as folder, patch.object(automation, "research_topic", return_value=[]):
            path = automation.create_presentation_from_topic("solar energy", folder=folder, slide_count=6)
            presentation = PowerPoint(path)

        self.assertEqual(len(presentation.slides), 6)
        self.assertEqual(presentation.slides[-1].shapes.title.text, "Success Measures and Conclusion")


if __name__ == "__main__":
    unittest.main()
