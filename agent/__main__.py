from .agent import LocalAgent

if __name__ == "__main__":
    agent = LocalAgent(voice_enabled=False)
    agent.run_console()
