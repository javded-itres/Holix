"""A2A protocol: models, card, server, client tools, config."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from core.a2a.card import build_agent_card
from core.a2a.client import extract_task_text
from core.a2a.config import load_a2a_config
from core.a2a.models import A2AMessage, TaskState
from core.a2a.server import cancel_task, get_task_public, handle_message_send
from core.a2a.store import A2ATaskStore


def test_message_parse_and_text() -> None:
    msg = A2AMessage.parse(
        {
            "role": "user",
            "parts": [{"kind": "text", "text": "hello"}],
            "contextId": "ctx1",
        }
    )
    assert msg.role == "user"
    assert msg.text_content() == "hello"
    assert msg.contextId == "ctx1"


def test_load_a2a_config_from_raw() -> None:
    cfg = load_a2a_config(
        raw={
            "a2a": {
                "enabled": True,
                "public_url": "https://x.example/a2a",
                "remote_agents": [
                    {"name": "r1", "url": "https://r1.example/a2a"},
                ],
            }
        }
    )
    assert cfg.enabled is True
    assert cfg.public_url == "https://x.example/a2a"
    assert len(cfg.remote_agents) == 1
    assert cfg.remote_agents[0].name == "r1"


def test_per_agent_remotes_do_not_inherit_profile_list() -> None:
    cfg = load_a2a_config(
        raw={
            "a2a": {
                "enabled": True,
                "remote_agents": [{"name": "shared", "url": "https://shared.example/a2a"}],
                "agents": {
                    "coder": {
                        "enabled": True,
                        "remote_agents": [
                            {"name": "docs", "url": "https://docs.example/a2a"},
                        ],
                    },
                    "researcher": {"enabled": False, "remote_agents": []},
                },
            }
        }
    )
    from core.a2a.config import remotes_for_slot

    main_on, main_peers = remotes_for_slot(cfg, "main")
    assert main_on is True
    assert [peer.name for peer in main_peers] == ["shared"]
    coder_on, coder_peers = remotes_for_slot(cfg, "coder")
    assert coder_on is True
    assert [peer.name for peer in coder_peers] == ["docs"]
    research_on, research_peers = remotes_for_slot(cfg, "researcher")
    assert research_on is False
    assert research_peers == []


def test_resolve_remote_uses_agent_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.a2a.config import A2AConfig, RemoteA2AAgent
    from core.tools.a2a import _resolve_remote

    cfg = A2AConfig(
        enabled=True,
        remote_agents=[RemoteA2AAgent(name="shared", url="https://shared.example/a2a")],
        agent_remotes={
            "coder": [RemoteA2AAgent(name="docs", url="https://docs.example/a2a")],
        },
        agent_enabled={"coder": True, "researcher": False},
    )
    cfg.agent_remotes["researcher"] = []
    monkeypatch.setattr("core.tools.a2a.load_a2a_config", lambda _profile: cfg)
    coder = SimpleNamespace(agent_slot="coder", config=SimpleNamespace(profile_name="p"))
    url, _headers, _timeout = _resolve_remote(coder, "docs")
    assert url == "https://docs.example/a2a"
    with pytest.raises(ValueError, match="docs"):
        _resolve_remote(coder, "shared")
    main = SimpleNamespace(agent_slot="main", config=SimpleNamespace(profile_name="p"))
    shared, _, _ = _resolve_remote(main, "shared")
    assert shared == "https://shared.example/a2a"
    researcher = SimpleNamespace(
        agent_slot="researcher",
        config=SimpleNamespace(profile_name="p"),
    )
    with pytest.raises(RuntimeError, match="disabled"):
        _resolve_remote(researcher, "https://other.example/a2a")


def test_parse_mikrollm_from_profile_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_MIKROLLM_A2A_URL", raising=False)
    monkeypatch.delenv("HOLIX_MIKROLLM_A2A_TOKEN", raising=False)
    monkeypatch.delenv("HOLIX_MIKROLLM_A2A_TOKEN_FILE", raising=False)
    cfg = load_a2a_config(
        raw={
            "a2a": {
                "mikrollm": {
                    "url": "http://gw.example:4000/",
                    "token_file": "~/.holix/agent.token",
                }
            }
        }
    )
    assert cfg.mikrollm is not None
    assert cfg.mikrollm.url == "http://gw.example:4000"
    assert cfg.mikrollm.token_file == "~/.holix/agent.token"
    monkeypatch.setenv("HOLIX_MIKROLLM_A2A_URL", "http://env.example:4000")
    overridden = load_a2a_config(raw={"a2a": {"mikrollm": {"url": "http://gw.example:4000"}}})
    assert overridden.mikrollm is not None
    assert overridden.mikrollm.url == "http://env.example:4000"
    monkeypatch.delenv("HOLIX_MIKROLLM_A2A_URL")
    assert load_a2a_config(raw={"a2a": {"enabled": True}}).mikrollm is None


def test_neighbor_rows_skip_blank_names() -> None:
    from core.a2a.mikrollm import neighbor_rows

    rows = neighbor_rows(
        {
            "self": {"name": "holix"},
            "agents": [
                {"name": "holix-mac1", "groups": ["holix"], "display_name": "Mac"},
                {"name": "  "},
                "not-a-card",
            ],
        }
    )
    assert rows == [
        {
            "name": "holix-mac1",
            "display_name": "Mac",
            "company": "",
            "description": "",
            "skills": [],
            "groups": ["holix"],
            "source": "mikrollm",
        }
    ]


@pytest.mark.asyncio
async def test_list_agents_merges_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.a2a.config import A2AConfig, RemoteA2AAgent
    from core.a2a.mikrollm import MikroLLMLink
    from core.tools.a2a import A2AListAgentsTool

    cfg = A2AConfig(
        enabled=True,
        remote_agents=[
            RemoteA2AAgent(name="holix-mac1", url="https://gw.example/a2a/u/holix-mac1")
        ],
        mikrollm=MikroLLMLink(url="http://gw.example:4000", token="agt-test"),
    )
    monkeypatch.setattr("core.tools.a2a.load_a2a_config", lambda _profile: cfg)

    async def fake_directory(_link):
        return {
            "agents": [
                {"name": "holix-mac1", "groups": ["holix"], "display_name": "Mac"},
                {"name": "shop", "groups": ["orders"], "description": "Shop agent"},
            ]
        }

    monkeypatch.setattr("core.tools.a2a.fetch_directory", fake_directory)
    parent = SimpleNamespace(agent_slot="main", config=SimpleNamespace(profile_name="default"))
    raw = await A2AListAgentsTool(parent).execute()
    import json

    body = json.loads(raw)
    by_name = {item["name"]: item for item in body["agents"]}
    assert by_name["holix-mac1"]["source"] == "both"
    assert by_name["holix-mac1"]["groups"] == ["holix"]
    assert by_name["shop"]["source"] == "mikrollm"
    assert body["mikrollm_error"] is None


@pytest.mark.asyncio
async def test_send_to_directory_neighbor_posts_group(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.a2a.config import A2AConfig, RemoteA2AAgent
    from core.a2a.mikrollm import MikroLLMLink
    from core.tools.a2a import A2ASendMessageTool

    cfg = A2AConfig(
        enabled=True,
        remote_agents=[RemoteA2AAgent(name="known", url="https://known.example/a2a")],
        mikrollm=MikroLLMLink(url="http://gw.example:4000", token="agt-test"),
    )
    monkeypatch.setattr("core.tools.a2a.load_a2a_config", lambda _profile: cfg)

    async def fake_directory(_link):
        return {"agents": [{"name": "shop", "groups": ["orders", "holix"]}]}

    posted: dict[str, str] = {}

    async def fake_post(_link, *, group: str, to: str, text: str):
        posted.update(group=group, to=to, text=text)
        return {"message": {"id": 7}}

    monkeypatch.setattr("core.tools.a2a.fetch_directory", fake_directory)
    monkeypatch.setattr("core.tools.a2a.post_group_message", fake_post)
    parent = SimpleNamespace(agent_slot="main", config=SimpleNamespace(profile_name="default"))
    tool = A2ASendMessageTool(parent)
    import json

    body = json.loads(await tool.execute(agent="shop", message="ping"))
    assert body["ok"] is True
    assert body["via"] == "mikrollm"
    assert posted == {"group": "orders", "to": "shop", "text": "ping"}
    chosen = json.loads(await tool.execute(agent="shop", message="ping", group="holix"))
    assert chosen["group"] == "holix"
    # A configured URL still uses the blocking client, not the group post.
    called = {"n": 0}

    async def refuse_post(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("configured remote must not post to the group")

    monkeypatch.setattr("core.tools.a2a.post_group_message", refuse_post)

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def send_message(self, text, **_kwargs):
            return {"id": "t1", "contextId": "c1", "status": {"state": "completed"}, "text": text}

    monkeypatch.setattr("core.tools.a2a.A2AClient", FakeClient)
    monkeypatch.setattr("core.tools.a2a.extract_task_text", lambda task: "reply")
    direct = json.loads(await tool.execute(agent="known", message="hello"))
    assert direct["ok"] is True
    assert direct["text"] == "reply"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_send_message_folds_sse_and_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from core.a2a.client import A2AClient, extract_task_text

    calls: list[bytes] = []
    mode = {"stream": True}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.content)
        if b"message/stream" in request.content and not mode["stream"]:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "error": {"code": -32601, "message": "Method not found"},
                },
            )
        if b"message/stream" in request.content:
            body = (
                'data: {"jsonrpc":"2.0","id":"1","result":{"artifactUpdate":{"append":true,'
                '"artifact":{"parts":[{"text":"hel"}]}}}}\n\n'
                'data: {"jsonrpc":"2.0","id":"1","result":{"artifactUpdate":{"append":true,'
                '"artifact":{"parts":[{"text":"lo"}]}}}}\n\n'
                'data: {"jsonrpc":"2.0","id":"1","result":{"task":{"id":"t1","status":{"state":"completed"}},'
                '"statusUpdate":{"final":true}}}\n\n'
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "result": {
                    "id": "t2",
                    "status": {"state": "completed", "message": {"parts": [{"text": "plain"}]}},
                },
            },
        )

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    streamed = await A2AClient("http://agent.example/a2a").send_message("ping")
    assert extract_task_text(streamed) == "hello"
    assert len(calls) == 1

    mode["stream"] = False
    plain = await A2AClient("http://agent.example/a2a").send_message("ping")
    assert extract_task_text(plain) == "plain"
    assert b"message/send" in calls[-1]


def test_build_agent_card_minimal() -> None:
    card = build_agent_card(
        "default",
        public_url="https://gw.example/a2a",
        config=load_a2a_config(raw={"enabled": True, "name": "TestAgent"}),
    )
    assert card["name"] == "TestAgent"
    assert card["url"] == "https://gw.example/a2a"
    assert card["protocolVersion"] == "0.3.0"
    assert card["capabilities"]["streaming"] is True
    assert isinstance(card["skills"], list) and card["skills"]


@pytest.mark.asyncio
async def test_handle_message_send_success() -> None:
    store = A2ATaskStore()
    agent = SimpleNamespace(
        run=AsyncMock(return_value="pong from holix"),
    )
    result = await handle_message_send(
        agent=agent,
        message={
            "role": "user",
            "parts": [{"kind": "text", "text": "ping"}],
            "contextId": "ctx-test",
        },
        profile="p1",
        store=store,
    )
    assert result["contextId"] == "ctx-test"
    assert result["status"]["state"] == TaskState.COMPLETED.value
    assert extract_task_text(result) == "pong from holix"
    agent.run.assert_awaited_once()
    # conversation mapped
    kwargs = agent.run.await_args.kwargs
    assert kwargs["conversation_id"] == "a2a:ctx-test"
    assert kwargs["user_input"] == "ping"

    got = get_task_public(result["id"], store=store, profile="p1")
    assert got is not None
    assert got["id"] == result["id"]


@pytest.mark.asyncio
async def test_handle_message_send_failure() -> None:
    store = A2ATaskStore()
    agent = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("boom")))
    result = await handle_message_send(
        agent=agent,
        message=A2AMessage.from_user_text("x"),
        profile="p1",
        store=store,
    )
    assert result["status"]["state"] == TaskState.FAILED.value
    assert "boom" in extract_task_text(result)


def test_cancel_task() -> None:
    store = A2ATaskStore()
    from core.a2a.models import A2ATask, A2ATaskStatus

    task = A2ATask(
        id="task_c1",
        profile="p1",
        status=A2ATaskStatus(state=TaskState.WORKING),
    )
    store.put(task)
    out = cancel_task("task_c1", store=store, profile="p1")
    assert out is not None
    assert out["status"]["state"] == TaskState.CANCELED.value


def test_extract_task_text_from_artifacts() -> None:
    text = extract_task_text(
        {
            "status": {"state": "completed"},
            "artifacts": [
                {"parts": [{"kind": "text", "text": "artifact body"}]},
            ],
        }
    )
    assert text == "artifact body"


@pytest.mark.asyncio
async def test_handle_message_stream_events() -> None:
    from core.a2a.server import handle_message_stream
    from core.agent_events import FinalResponseEvent, ThinkingEvent

    store = A2ATaskStore()

    async def _fake_run_holix(
        agent, user_input, conversation_id, *, stream=False, execution_mode=None
    ):
        yield ThinkingEvent(message="planning")
        yield FinalResponseEvent(content="streamed answer")

    agent = SimpleNamespace(
        _initialized=True,
        emit=lambda e: None,
        run=AsyncMock(return_value="fallback"),
    )

    # Patch run_holix import path used inside handle_message_stream
    import core.runtime.executor as executor_mod

    original = executor_mod.run_holix
    executor_mod.run_holix = _fake_run_holix  # type: ignore[assignment]
    try:
        events = []
        async for item in handle_message_stream(
            agent=agent,
            message={"role": "user", "parts": [{"kind": "text", "text": "hi"}]},
            profile="p1",
            store=store,
        ):
            events.append(item)
    finally:
        executor_mod.run_holix = original

    assert events, "expected stream events"
    assert "task" in events[0]
    assert events[0]["task"]["status"]["state"] in {"working", "submitted"}
    # should include statusUpdate and/or artifactUpdate and final completed
    kinds = set()
    for e in events:
        kinds.update(e.keys())
    assert "statusUpdate" in kinds or "artifactUpdate" in kinds
    finals = [
        e
        for e in events
        if e.get("statusUpdate", {}).get("final")
        or (e.get("task", {}).get("status", {}).get("state") in {"completed", "failed"})
    ]
    assert finals
    # completed answer stored
    last_task = get_task_public(events[0]["task"]["id"], store=store, profile="p1")
    assert last_task is not None
    assert last_task["status"]["state"] == "completed"
    assert extract_task_text(last_task) == "streamed answer"
