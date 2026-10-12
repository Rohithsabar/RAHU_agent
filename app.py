from __future__ import annotations

import argparse
import ipaddress
import secrets
import socket
import threading
import traceback
import webbrowser

from flask import Flask, jsonify, render_template, request, session
from config import DATA_DIR

try:
    import pystray
except Exception:  # pragma: no cover
    pystray = None

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover
    Image = None
    ImageDraw = None

from agent.agent import LocalAgent

app = Flask(__name__, template_folder="templates", static_folder="static")
agent = LocalAgent(voice_enabled=False)
tray_icon = None
voice_thread = None
mobile_access_enabled = False
mobile_pairing_code = ""
dashboard_url = "http://127.0.0.1:5000"
pairing_failures: dict[str, int] = {}
app.secret_key = secrets.token_bytes(32)


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception) -> tuple[dict, int]:
    error_details = traceback.format_exc()
    try:
        log_directory = DATA_DIR / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        with (log_directory / "rahu-errors.log").open("a", encoding="utf-8") as log_file:
            log_file.write(error_details + "\n")
    except OSError:
        pass
    app.logger.error("Unhandled RAHU request error: %s", error_details)
    return jsonify({"error": f"RAHU couldn't complete that request: {error}"}), 500


def _is_loopback_request() -> bool:
    try:
        return ipaddress.ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        return False


def _mobile_addresses() -> list[str]:
    addresses = set()
    try:
        import psutil

        for interface_addresses in psutil.net_if_addrs().values():
            for address in interface_addresses:
                if address.family == socket.AF_INET:
                    candidate = ipaddress.ip_address(address.address)
                    if candidate.is_private and not candidate.is_loopback:
                        addresses.add(str(candidate))
    except Exception:
        pass
    return sorted(addresses)


@app.before_request
def require_mobile_pairing() -> tuple[dict, int] | None:
    if not mobile_access_enabled or _is_loopback_request():
        return None
    if request.endpoint in {"index", "pair_mobile"} or request.endpoint == "static":
        return None
    if session.get("mobile_paired"):
        return None
    return jsonify({"error": "Pair this phone using the code shown in RAHU on your computer."}), 401


def _start_voice_loop() -> None:
    global voice_thread
    if not agent.voice.enabled or (voice_thread is not None and voice_thread.is_alive()):
        return
    voice_thread = threading.Thread(target=agent.run_voice_loop, daemon=True)
    voice_thread.start()


def _create_tray_image() -> object:
    if Image is None or ImageDraw is None:
        return None
    image = Image.new("RGB", (64, 64), color=(20, 30, 60))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), fill=(34, 197, 94))
    draw.rectangle((18, 18, 46, 46), fill=(15, 23, 42))
    draw.text((22, 20), "R", fill=(255, 255, 255))
    return image


def _open_dashboard() -> None:
    webbrowser.open(dashboard_url)


def _toggle_voice() -> None:
    agent.set_voice_enabled(not agent.voice.enabled)
    state = "enabled" if agent.voice.enabled else "disabled"
    print(f"Voice is now {state}.")


def _show_status() -> None:
    print(agent.status())


def _shutdown_tray() -> None:
    global tray_icon
    agent.running = False
    agent.status_window.stop()
    if tray_icon is not None:
        tray_icon.stop()
    raise SystemExit(0)


def start_tray_icon() -> None:
    if pystray is None or Image is None or ImageDraw is None:
        print("Tray support is unavailable in this environment.")
        return

    image = _create_tray_image()
    if image is None:
        print("Tray icon image could not be created.")
        return

    global tray_icon
    tray_icon = pystray.Icon(
        "RAHU Assistant",
        image,
        "RAHU Assistant",
        menu=pystray.Menu(
            pystray.MenuItem("Open Dashboard", _open_dashboard),
            pystray.MenuItem("Toggle Voice", _toggle_voice),
            pystray.MenuItem("Status", _show_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", _shutdown_tray),
        ),
    )
    tray_icon.run()


@app.route("/")
def index() -> str:
    local_request = _is_loopback_request()
    paired = local_request or not mobile_access_enabled or bool(session.get("mobile_paired"))
    return render_template(
        "index.html",
        paired=paired,
        is_local=local_request,
        mobile_enabled=mobile_access_enabled,
        mobile_pairing_code=mobile_pairing_code if local_request and mobile_access_enabled else "",
        mobile_addresses=_mobile_addresses() if local_request and mobile_access_enabled else [],
        mobile_port=request.environ.get("SERVER_PORT", "5000"),
    )


@app.route("/api/pair", methods=["POST"])
def pair_mobile() -> tuple[dict, int] | dict:
    if not mobile_access_enabled:
        return jsonify({"error": "Mobile access is disabled. Start RAHU with --mobile."}), 403
    remote = request.remote_addr or "unknown"
    if pairing_failures.get(remote, 0) >= 5:
        return jsonify({"error": "Too many incorrect codes. Restart RAHU to try again."}), 429
    payload = request.get_json(silent=True) or {}
    code = payload.get("code", "")
    if not isinstance(code, str) or not secrets.compare_digest(code.strip(), mobile_pairing_code):
        pairing_failures[remote] = pairing_failures.get(remote, 0) + 1
        return jsonify({"error": "That pairing code is incorrect."}), 401
    session["mobile_paired"] = True
    session.permanent = True
    return jsonify({"paired": True})


@app.route("/api/status")
def status() -> dict:
    current_status = agent.status()
    current_status["mobile"] = {
        "enabled": mobile_access_enabled,
        "urls": [f"http://{address}:{request.environ.get('SERVER_PORT', '5000')}" for address in _mobile_addresses()],
        "pairing_code": mobile_pairing_code if _is_loopback_request() and mobile_access_enabled else "",
    }
    return jsonify(current_status)


@app.route("/api/ai/config", methods=["POST"])
def configure_ai() -> tuple[dict, int] | dict:
    payload = request.get_json(silent=True) or {}
    try:
        agent.ai.configure(payload)
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400
    message = (
        "The saved online API key was removed from Windows Credential Manager."
        if payload.get("clear_api_key")
        else (
            "AI settings and API key saved in Windows Credential Manager."
            if payload.get("api_key")
            else (
                "AI settings saved. Your existing API key is still available."
                if agent.ai.online_key
                else "AI settings saved. Add an API key to enable online chat."
            )
        )
    )
    return jsonify({"message": message})


@app.route("/api/command", methods=["POST"])
def command() -> dict:
    try:
        payload = request.get_json(silent=True) or {}
        text = payload.get("text", "")
        reply = agent.handle_command(text)
        return jsonify({"response": reply})
    except Exception as exc:
        error_details = traceback.format_exc()
        try:
            log_directory = DATA_DIR / "logs"
            log_directory.mkdir(parents=True, exist_ok=True)
            with (log_directory / "rahu-errors.log").open("a", encoding="utf-8") as log_file:
                log_file.write(error_details + "\n")
        except OSError:
            pass
        app.logger.error("RAHU failed to process a command: %s", error_details)
        return jsonify({"error": f"RAHU couldn't complete that request: {exc}"}), 500


@app.route("/api/voice/toggle", methods=["POST"])
def toggle_voice() -> dict:
    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled", not agent.voice.enabled))
    if enabled and not agent.voice.microphone_available:
        return jsonify({"error": "Voice recognition is not installed. Text commands remain available."}), 503
    agent.set_voice_enabled(enabled)
    if enabled:
        _start_voice_loop()
    return jsonify({"enabled": agent.voice.enabled})


@app.route("/api/connect", methods=["POST"])
def request_connect() -> dict:
    return jsonify({"response": agent.remote.request_permission()})


@app.route("/api/approve", methods=["POST"])
def approve_connection() -> dict:
    return jsonify({"response": agent.remote.approve_connection()})


@app.route("/api/disconnect", methods=["POST"])
def disconnect() -> dict:
    return jsonify({"response": agent.remote.disconnect()})


@app.route("/api/payment", methods=["POST"])
def payment() -> dict:
    payload = request.get_json(silent=True) or {}
    schedule = payload.get("schedule", agent.settings.payment_schedule)
    method = payload.get("method", agent.settings.default_payment_method)
    response = agent.payment.update_preferences(schedule, method)
    return jsonify({"response": response})


@app.route("/api/terminate", methods=["POST"])
def terminate() -> dict:
    agent.running = False
    agent.status_window.stop()
    return jsonify({"response": "The local agent session was terminated."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local personal AI agent.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--voice", action="store_true")
    parser.add_argument("--voice-loop", action="store_true", help="Listen for wake words and respond by voice while the dashboard stays active.")
    parser.add_argument("--console", action="store_true", help="Run in console mode so typed commands are recognized immediately in cmd or PowerShell.")
    parser.add_argument("--desktop", action="store_true", help="Run the assistant in desktop mode with tray icon, voice support, and the local dashboard active together.")
    parser.add_argument("--tray", action="store_true", help="Start only the system tray launcher with the dashboard running in the background.")
    parser.add_argument("--web-only", action="store_true", help="Run the local dashboard and tools without requesting microphone access.")
    parser.add_argument("--mobile", action="store_true", help="Allow paired phones on the same Wi-Fi to use the dashboard.")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the local dashboard.")
    args = parser.parse_args()

    if args.mobile and not any((args.console, args.voice, args.voice_loop, args.desktop, args.tray)):
        args.web_only = True
    if not (args.console or args.voice or args.voice_loop or args.desktop or args.tray or args.web_only):
        args.desktop = True

    if args.host is None:
        args.host = "0.0.0.0" if args.mobile else "127.0.0.1"
    dashboard_url = f"http://127.0.0.1:{args.port}"
    mobile_access_enabled = args.mobile
    mobile_pairing_code = f"{secrets.randbelow(100_000_000):08d}" if args.mobile else ""

    enable_voice = args.voice or args.voice_loop or args.desktop or args.tray
    if enable_voice:
        print("RAHU needs permission to listen with your microphone.")
        if not agent.request_voice_permission():
            print("Voice features are off. Text and desktop actions remain available.")

    if args.web_only:
        if not args.no_browser:
            threading.Timer(1.2, _open_dashboard).start()
        app.run(host=args.host, port=args.port, debug=False)
    elif args.desktop or args.tray:
        status_window_available = agent.status_window.start()
        if agent.voice.enabled:
            _start_voice_loop()
        tray_thread = threading.Thread(target=start_tray_icon, daemon=True)
        tray_thread.start()
        if status_window_available:
            server_thread = threading.Thread(
                target=app.run,
                kwargs={"host": args.host, "port": args.port, "debug": False},
                daemon=True,
            )
            server_thread.start()
            if not args.no_browser:
                threading.Timer(1.2, _open_dashboard).start()
            agent.status_window.run()
        else:
            if not args.no_browser:
                threading.Timer(1.2, _open_dashboard).start()
            app.run(host=args.host, port=args.port, debug=False)
    elif args.console:
        agent.run_console()
    elif args.voice_loop:
        if agent.voice.enabled:
            _start_voice_loop()
        if not args.no_browser:
            threading.Timer(1.2, _open_dashboard).start()
        app.run(host=args.host, port=args.port, debug=False)
    else:
        if not args.no_browser:
            threading.Timer(1.2, _open_dashboard).start()
        app.run(host=args.host, port=args.port, debug=False)
