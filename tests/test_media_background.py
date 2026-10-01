"""generate_image / generate_video return before the provider finishes."""

import asyncio
from pathlib import Path

import pytest
from core.runtime.agent_tasks import get_agent_task_registry
from holix_media.config import MediaConfig, MediaProvider
from holix_media.providers import MediaBlob
from holix_media.tools import GenerateVideoTool


@pytest.fixture(autouse=True)
def _clear_tasks():
    get_agent_task_registry().clear()
    yield
    get_agent_task_registry().clear()


@pytest.mark.asyncio
async def test_generate_video_returns_while_the_job_is_still_running(
    monkeypatch, tmp_path: Path
) -> None:
    gate = asyncio.Event()

    async def _slow(*_args, **_kwargs):
        await gate.wait()
        return MediaBlob(b"mp4", "video/mp4", "clip.mp4")

    monkeypatch.setattr("holix_media.tools.generate_video", _slow)
    monkeypatch.setattr(
        "holix_media.tools.save_blob",
        lambda blob, agent=None, subdir="media": tmp_path / "clip.mp4",
    )
    cfg = MediaConfig(
        enabled=True,
        auto_send=False,
        output_subdir="media",
        image_providers=(),
        video_providers=(
            MediaProvider(
                id="mikrollm",
                kind="video",
                type="openai_videos",
                base_url="http://192.168.88.1:4000/v1",
                api_key_env="",
                model="minimax-hailuo-02",
                extra={"api_key": "test"},
            ),
        ),
    )
    tool = GenerateVideoTool(config=cfg)
    result = await tool.execute(prompt="stormy shore", duration_s=5)
    assert result.startswith("Background task started:")
    assert "оно придёт в чат" in result
    assert "do not poll" not in result.lower()
    assert "send_chat_files" not in result
    task_id = result.split("id=", 1)[1].split(" ", 1)[0]
    running = get_agent_task_registry().get(task_id)
    assert running is not None and running.is_running()
    assert running.description == "Генерация видео"
    gate.set()
    for _ in range(50):
        if not running.is_running():
            break
        await asyncio.sleep(0.02)
    assert running.status == "completed"
    assert "Saved video" in running.output


@pytest.mark.asyncio
async def test_same_prompt_is_not_generated_twice(monkeypatch, tmp_path: Path) -> None:
    gate = asyncio.Event()

    async def _slow(*_args, **_kwargs):
        await gate.wait()
        return MediaBlob(b"png", "image/png", "pic.png")

    monkeypatch.setattr("holix_media.tools.generate_image", _slow)
    monkeypatch.setattr(
        "holix_media.tools.save_blob",
        lambda blob, agent=None, subdir="media": tmp_path / "pic.png",
    )
    cfg = MediaConfig(
        enabled=True,
        auto_send=False,
        output_subdir="media",
        image_providers=(
            MediaProvider(
                id="mikrollm",
                kind="image",
                type="openai_images",
                base_url="http://192.168.88.1:4000/v1",
                api_key_env="",
                model="image-z-image-turbo",
                extra={"api_key": "test"},
            ),
        ),
        video_providers=(),
    )
    from holix_media.tools import GenerateImageTool

    tool = GenerateImageTool(config=cfg)
    first = await tool.execute(prompt="a cat on an elephant")
    second = await tool.execute(prompt="a cat on an elephant")
    assert first.startswith("Background task started:")
    assert second.startswith("Already generated this prompt:")
    assert "Do not start another" in second
    gate.set()
