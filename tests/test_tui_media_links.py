from pathlib import Path

from cli.tui.shared.media_links import (
    extract_media_hrefs,
    format_media_tool_result,
    path_to_file_uri,
)


def test_extract_file_uri_and_saved_path(tmp_path: Path) -> None:
    p = tmp_path / "cat.png"
    p.write_bytes(b"x")
    body = f"Saved image: {p}\n[Open image]({p.resolve().as_uri()})\nOpen: {p.resolve().as_uri()}"
    hrefs = extract_media_hrefs(body)
    assert hrefs
    assert hrefs[0].startswith("file:")
    assert "cat.png" in hrefs[0]


def test_tui_shows_only_the_local_file_when_a_remote_url_is_present(tmp_path: Path) -> None:
    image = tmp_path / "clip.mp4"
    image.write_bytes(b"mp4")
    uri = image.resolve().as_uri()
    body = f"Saved video: {image}\n[Open video]({uri})\nURL: http://192.168.88.252:8188/view?filename=clip.mp4"
    renderable = format_media_tool_result(body, tool_name="generate_video")
    assert "Open video" in renderable.plain
    assert uri in renderable.plain
    assert "8188" not in renderable.plain
    assert "http:" not in renderable.plain


def test_extract_http_url() -> None:
    body = "URL: https://cdn.example/a.png"
    hrefs = extract_media_hrefs(body)
    assert "https://cdn.example/a.png" in hrefs


def test_saved_image_does_not_need_another_agent_turn(tmp_path: Path) -> None:
    from cli.tui.shared.media_links import saved_media_needs_agent_report

    image = tmp_path / "pic.png"
    image.write_bytes(b"png")
    body = f"Saved image: {image}\nOpen: {image.resolve().as_uri()}"
    assert (
        saved_media_needs_agent_report(body, status="completed", description="image: a cat")
        is False
    )
    assert saved_media_needs_agent_report("Error: HTTP 502", status="failed") is True


def test_background_task_output_becomes_a_tui_link(tmp_path: Path) -> None:
    from cli.tui.shared.media_links import media_link_renderable

    image = tmp_path / "20260928-153326.png"
    image.write_bytes(b"png")
    body = (
        f"Saved image: {image}\n"
        f"[Open image]({image.resolve().as_uri()})\n"
        "provider=mikrollm type=openai_images model=image-z-image-turbo bytes=4"
    )
    renderable = media_link_renderable(body, description="image: a dog on a horse")
    assert renderable is not None
    assert "Open image" in renderable.plain
    assert "file:" in renderable.plain
    assert media_link_renderable("Error: HTTP 429 gpu busy") is None


def test_rendered_open_image_keeps_a_file_link() -> None:
    from cli.tui.shared.media_links import href_from_line_text, href_from_segments
    from rich.console import Console
    from rich.segment import Segment
    from textual.strip import Strip

    uri = path_to_file_uri("/tmp/pic.png")
    renderable = format_media_tool_result(
        f"Saved image: /tmp/pic.png\nOpen: {uri}",
        tool_name="generate_image",
    )
    console = Console(width=100, force_terminal=True)
    strips = Strip.from_lines(Segment.split_lines(console.render(renderable)))
    hrefs = [href_from_segments(strip) for strip in strips]
    assert any(href.startswith("file:") and href.endswith("pic.png") for href in hrefs)
    assert href_from_line_text(f"Open: {uri}").endswith("pic.png")


def test_format_media_tool_result_has_link_style() -> None:
    uri = path_to_file_uri("/tmp/pic.png")
    renderable = format_media_tool_result(
        f"Saved image: /tmp/pic.png\nOpen: {uri}",
        tool_name="generate_image",
    )
    plain = renderable.plain
    assert "Open image" in plain
    assert "file:" in plain
