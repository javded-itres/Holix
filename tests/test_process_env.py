"""Agent child processes do not inherit secret-named variables."""

from core.security.process_env import agent_process_env


def test_agent_process_env_drops_secret_names() -> None:
    env = agent_process_env(
        {
            "PATH": "/usr/bin",
            "HOME": "/Users/me",
            "HOLIX_HOME": "/Users/me/.holix",
            "HOLIX_PROFILE": "default",
            "OPENAI_API_KEY": "sk-test",
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "HOLIX_UNLOCK_KEY": "unlock",
            "DATABASE_PASSWORD": "pw",
            "SSH_AUTH_SOCK": "/tmp/agent.sock",
        }
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOLIX_HOME"] == "/Users/me/.holix"
    assert env["HOLIX_PROFILE"] == "default"
    assert env["SSH_AUTH_SOCK"] == "/tmp/agent.sock"
    assert "OPENAI_API_KEY" not in env
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "HOLIX_UNLOCK_KEY" not in env
    assert "DATABASE_PASSWORD" not in env
