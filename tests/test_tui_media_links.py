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


def test_extract_http_url() -> None:
    body = "URL: https://cdn.example/a.png"
    hrefs = extract_media_hrefs(body)
    assert "https://cdn.example/a.png" in hrefs


def test_format_media_tool_result_has_link_style() -> None:
    uri = path_to_file_uri("/tmp/pic.png")
    renderable = format_media_tool_result(
        f"Saved image: /tmp/pic.png\nOpen: {uri}",
        tool_name="generate_image",
    )
    plain = renderable.plain
    assert "Open image" in plain
    assert "file:" in plain
