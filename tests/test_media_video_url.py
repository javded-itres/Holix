"""Video status URLs and the unbounded poll."""

import base64

import pytest
from holix_media.config import MediaProvider
from holix_media.providers import _join_api, _video_poll_url, generate_video


def test_join_api_keeps_single_v1() -> None:
    assert _join_api("http://192.168.88.1:4000/v1", "/videos") == (
        "http://192.168.88.1:4000/v1/videos"
    )
    assert _join_api("http://192.168.88.1:4000/v1", "/v1/videos") == (
        "http://192.168.88.1:4000/v1/videos"
    )


@pytest.mark.asyncio
async def test_image_job_polls_until_bytes_arrive(monkeypatch) -> None:
    import base64

    import holix_media.providers as providers
    from holix_media.config import MediaProvider
    from holix_media.providers import generate_image

    monkeypatch.setattr(providers, "_POLL_INTERVAL_S", 0)
    payload = base64.b64encode(b"png-bytes").decode()

    class _Job:
        def __init__(self) -> None:
            self.gets = 0

        async def post_json(self, url, *, headers, json, timeout=None):
            return {
                "id": "img_abc",
                "object": "image",
                "status": "queued",
                "polling_url": "http://192.168.88.1:4000/v1/images/img_abc",
            }

        async def get_json(self, url, *, headers, timeout=None):
            self.gets += 1
            assert "/images/img_abc" in url
            if self.gets == 1:
                return {"id": "img_abc", "status": "running"}
            return {"id": "img_abc", "status": "completed", "b64_json": payload}

        async def get_bytes(self, url, *, headers=None, timeout=None):
            raise AssertionError("inline bytes")

    provider = MediaProvider(
        id="mikrollm",
        kind="image",
        type="openai_images",
        base_url="http://192.168.88.1:4000/v1",
        api_key_env="",
        model="image-z-image-turbo",
        extra={"api_key": "test"},
    )
    blob = await generate_image(provider, "a cat", http=_Job(), size="1024x1024")
    assert blob.data == b"png-bytes"


def test_poll_url_strips_v1_already_present_on_base() -> None:
    url = _video_poll_url(
        "http://192.168.88.1:4000/v1",
        job_id="video_abc",
        model="minimax-hailuo-02",
        polling_url="http://192.168.88.1:4000/v1/videos/video_abc",
        poll_path="/videos/{id}",
    )
    assert url == ("http://192.168.88.1:4000/v1/videos/video_abc?model=minimax-hailuo-02")


def test_poll_url_openrouter_api_prefix() -> None:
    url = _video_poll_url(
        "https://openrouter.ai/api/v1",
        job_id="job1",
        model="seedance",
        polling_url="https://openrouter.ai/api/v1/videos/job1",
        poll_path="/videos/{id}",
    )
    assert url == "https://openrouter.ai/api/v1/videos/job1?model=seedance"


class _FlakyVideo:
    def __init__(self) -> None:
        self.gets = 0
        self.post_timeouts: list[object] = []

    async def post_json(self, url, *, headers, json, timeout=None):
        self.post_timeouts.append(timeout)
        return {"id": "job1", "status": "queued"}

    async def get_json(self, url, *, headers, timeout=None):
        self.gets += 1
        if self.gets == 1:
            raise RuntimeError(f"HTTP 502 {url}: bad gateway")
        payload = base64.b64encode(b"mp4-bytes").decode()
        return {"status": "succeeded", "b64_json": payload}

    async def get_bytes(self, url, *, headers=None, timeout=None):
        raise AssertionError("file was inline")


@pytest.mark.asyncio
async def test_video_poll_retries_502_without_a_deadline(monkeypatch) -> None:
    import holix_media.providers as providers

    monkeypatch.setattr(providers, "_POLL_INTERVAL_S", 0)
    http = _FlakyVideo()
    provider = MediaProvider(
        id="mikrollm",
        kind="video",
        type="openai_videos",
        base_url="http://192.168.88.1:4000/v1",
        api_key_env="",
        model="minimax-hailuo-02",
        extra={"api_key": "test"},
    )
    blob = await generate_video(provider, "a shore", http=http, duration_s=5)
    assert blob.data == b"mp4-bytes"
    assert http.gets == 2
    assert http.post_timeouts == [None]


@pytest.mark.asyncio
async def test_video_poll_does_not_retry_client_errors(monkeypatch) -> None:
    import holix_media.providers as providers

    monkeypatch.setattr(providers, "_POLL_INTERVAL_S", 0)

    class _Bad:
        async def post_json(self, url, *, headers, json, timeout=None):
            return {"id": "job1", "status": "queued"}

        async def get_json(self, url, *, headers, timeout=None):
            raise RuntimeError(f"HTTP 400 {url}: bad request")

        async def get_bytes(self, url, *, headers=None, timeout=None):
            raise AssertionError("no download")

    provider = MediaProvider(
        id="mikrollm",
        kind="video",
        type="openai_videos",
        base_url="http://192.168.88.1:4000/v1",
        api_key_env="",
        model="minimax-hailuo-02",
        extra={"api_key": "test"},
    )
    with pytest.raises(RuntimeError, match="HTTP 400"):
        await generate_video(provider, "a shore", http=_Bad(), duration_s=5)
