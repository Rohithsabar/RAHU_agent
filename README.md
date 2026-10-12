# Local Personal AI Agent

This project gives you a local personal AI assistant that runs on your computer and can:

- execute terminal commands
- open files by name and apps on accessible local drives
- assist with daily work and project tasks
- preview and clean old user temporary files after confirmation
- create 10-slide presentations by default or use a requested slide count
- speak in English with a human-like tone
- ask for payment preferences and save them for later
- request and manage permission for a remote connected device
- disconnect and reconnect a connected device with explicit approval

## Quick start

1. Create a Python environment.
2. Install dependencies:

   python -m pip install -r requirements.txt

3. Start the assistant in command-console mode for direct typing:

   python app.py --console

4. Start the browser-based dashboard with voice support:

   python app.py --voice

5. Start the full desktop assistant mode with tray icon, voice loop, and dashboard together:

   python app.py --desktop

6. Start the tray-only launcher mode:

   python app.py --tray

7. Open the local web dashboard at http://localhost:5000

For dashboard-only use without microphone permission, run `python app.py --web-only`.

To use RAHU from a phone on the same trusted Wi-Fi network, start `python app.py --mobile` or click the desktop shortcut. The laptop dashboard displays private-network URLs and a temporary eight-digit pairing code. Open an address on the phone and enter that code. Do not share the code outside your network or forward the RAHU port to the public internet. The default `python app.py --web-only` remains loopback-only.

If Windows Firewall blocks the phone, open PowerShell as Administrator once and run:

   if (-not (Get-NetFirewallRule -DisplayName 'RAHU Assistant Mobile' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName 'RAHU Assistant Mobile' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000 -Profile Private }

Keep the Wi-Fi network set to Private. This opens only the RAHU dashboard port on Private networks; never add a router port-forward for RAHU.

## Build the Windows app

1. Activate the project virtual environment.
2. Run `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1` from this folder.
3. The script creates `dist\RAHU Assistant.exe` and a branded desktop shortcut. Double-click the shortcut to start RAHU and open its local dashboard.

The executable keeps settings and learning memory in `%LOCALAPPDATA%\RAHU Assistant`; generated documents are saved in `%USERPROFILE%\Documents\RAHU Assistant`.

## Enable AI reasoning

RAHU always has its local, deterministic desktop tools. For general AI answers and planning, configure either or both of these providers:

- Online free tier: choose **Use Gemini free tier** in the dashboard, create a Gemini API key in Google AI Studio, paste it into the password field, and save. RAHU uses the OpenAI-compatible Gemini endpoint and current Flash model by default. Free usage has quotas and may change; Google's free-tier terms say prompts may be used to improve its products.
- Other online providers: set `RAHU_AI_API_KEY` to an API key for an OpenAI-compatible provider. Optionally set `RAHU_AI_BASE_URL` and `RAHU_AI_MODEL` for that provider. Keys are stored in Windows Credential Manager when entered in the dashboard and are never written to the settings JSON.
- Offline: install Ollama, run `ollama pull qwen2.5:7b`, and leave the default local endpoint at `http://127.0.0.1:11434/v1`. The model download is separate from the executable.

RAHU tries the configured online provider first, then the local model. If neither is running, fixed local actions such as opening apps, finding files, and opening maps remain available.

You can configure a provider in the dashboard under **AI connection → Connect an AI model**. Select the Gemini preset, paste the key, then save. The key is stored in Windows Credential Manager; the settings file contains only the endpoint and model name. Online prompts are sent to the provider you select. For offline chat, install Ollama and download the model shown in the dashboard. Until one of these providers is configured and running, RAHU can use its built-in desktop tools but cannot generate open-ended AI answers.

## Activate the assistant by name

You can call the assistant like this:

- Hey RAHU
- RAHU help
- open notepad
- launch chrome
- search for python jobs
- search about gods eye
- search map
- open map
- make presentation for hospital management system
- RAHU open my files
- RAHU run command dir
- RAHU make a Word document
- RAHU make a PowerPoint presentation
- open file budget.xlsx
- open meeting-notes
- find file meeting notes
- make me a presentation on solar energy
- prepare a 12-slide presentation on solar energy
- clean junk
- check my system performance
- open Microsoft Store
- RAHU search for jobs for Python developer

The system recognizes the wake word and responds as your personal local assistant.

## Work automation commands

The desktop assistant can help with:

- create Word documents
- create PowerPoint presentations
- open websites and job searches
- run commands on your laptop
- open local files and apps
- manage remote access permission
- track payment plans and income tasks

## Features

- Desktop command execution
- File opening
- App launching
- Local English chat style interaction
- Voice output through pyttsx3
- Windows tray icon for quick access
- Desktop dashboard launcher with responsive action menu
- Remote connection approval flow
- Termination and reconnect control

## Security

The project is designed for local use and requires explicit permission before remote device connection.

## GitHub publishing

`.gitignore` excludes local data, AI settings, logs, virtual environments, builds, executables, generated Word/PowerPoint files, and environment files. RAHU stores online API keys in Windows Credential Manager, not the repository. Never add an API key to source code, screenshots, README examples, or commits. Gemini's free tier has quotas and its terms may allow prompts to be used to improve Google products.

To publish a private repository, install Git for Windows and GitHub CLI, run `gh auth login`, then run `powershell -ExecutionPolicy Bypass -File .\publish_private_github.ps1`. The script refuses to publish local data, builds, generated Office files, keys, or environment files and stops if an origin remote already exists.

## Example commands

- open my files
- run python script
- open notepad
- connect remote device
- disconnect remote device
- tell me about my payment schedule

## Notes

This is a local helper project built for personal automation and offline operation. Some features need permission and a real device or network connection to operate in a production environment.
