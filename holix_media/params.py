"""Parameters Holix can send to an image or video model, plus the last job."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from holix_media.config import MediaProvider
from holix_media.refs import ReferenceImage

IMAGE_PARAMETERS: tuple[tuple[str, str], ...] = (
    ("prompt", "What to draw. Required."),
    ("size", "WIDTHxHEIGHT, for example 1024x1024. Change only when the user asks."),
    (
        "seed",
        "Integer. On an edit of an existing image, send the same seed. "
        "Pick a new seed only for a new picture or when the user asks.",
    ),
    (
        "references",
        "File paths. When the user wants to change an existing image, pass that file. "
        "Also pass photos the user uploaded.",
    ),
)

VIDEO_PARAMETERS: tuple[tuple[str, str], ...] = (
    ("prompt", "What the clip shows. Required."),
    ("duration_s", "Length in seconds, when the user asks for a length."),
    (
        "seed",
        "Integer. Keep the previous seed when revising the same clip.",
    ),
    (
        "references",
        "File paths of a source image or the previous clip's still, when the model should follow them.",
    ),
)


def parameter_lines(kind: str) -> list[str]:
    rows = VIDEO_PARAMETERS if kind == "video" else IMAGE_PARAMETERS
    return [f"- {name}: {note}" for name, note in rows]


def meta_path_for(media_path: Path) -> Path:
    return media_path.with_name(media_path.name + ".meta.json")


def load_generation_meta(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    target = meta_path_for(path) if path.suffix.lower() != ".json" else path
    if not target.is_file() and path.is_file() and path.name.endswith(".meta.json"):
        target = path
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_generation_meta(media_path: Path, meta: dict[str, Any]) -> None:
    meta_path_for(media_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def last_job_path(directory: Path, kind: str) -> Path:
    return directory / f".last-{kind}.json"


def read_last_job(directory: Path, kind: str) -> dict[str, Any] | None:
    return load_generation_meta(last_job_path(directory, kind))


def write_last_job(directory: Path, kind: str, meta: dict[str, Any]) -> None:
    path = last_job_path(directory, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def previous_generation_field(
    references: list[ReferenceImage] | None,
    field: str,
) -> str:
    for ref in references or []:
        meta = load_generation_meta(ref.path)
        if not meta:
            continue
        value = str(meta.get(field) or "").strip()
        if value:
            return value
    return ""


def compose_edit_prompt(new_text: str, references: list[ReferenceImage] | None) -> str:
    """Append a revision to the prompt stored with the reference image.

    The previous prompt stays at the front so the same seed keeps the picture stable.
    A caller that already extended that prompt is left unchanged.
    """
    edit = (new_text or "").strip()
    base = previous_generation_field(references, "prompt")
    if not base or not edit:
        return edit or base
    if edit == base or edit.startswith(base):
        return edit
    return f"{base}\n{edit}"


def choose_seed(seed: int | None, references: list[ReferenceImage] | None) -> int:
    """Keep the seed of a referenced generation unless the caller set a new one."""
    if seed is not None:
        return int(seed)
    for ref in references or []:
        meta = load_generation_meta(ref.path)
        if meta and meta.get("seed") is not None:
            try:
                return int(meta["seed"])
            except (TypeError, ValueError):
                continue
    return secrets.randbelow(2_147_483_646) + 1


def format_model_card(
    provider: MediaProvider,
    *,
    kind: str,
    record: dict[str, Any] | None,
    last_job: dict[str, Any] | None,
) -> str:
    lines = [
        f"kind: {kind}",
        f"provider: {provider.id}",
        f"type: {provider.type}",
        f"model: {provider.model}",
    ]
    if provider.note:
        lines.append(f"note: {provider.note}")
    if provider.accepts_reference is True:
        lines.append("accepts_reference: yes")
    elif provider.accepts_reference is False:
        lines.append("accepts_reference: no")
    card = record or {}
    published = card.get("parameters") if isinstance(card, dict) else None
    if isinstance(published, list) and published:
        lines.append("parameters from the model catalog:")
        for item in published:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            typ = item.get("type") or "string"
            required = "required" if item.get("required") else "optional"
            desc = str(item.get("description") or "").strip()
            line = f"- {name} ({typ}, {required})"
            if desc:
                line += f": {desc}"
            lines.append(line)
        lines.append(
            "Use only these parameters. On an edit, keep seed and pass the previous file as a reference when input_image or references is listed."
        )
    else:
        lines.append("The catalog did not list parameters. These controls are still forwarded:")
        lines.append("parameters:")
        lines.extend(parameter_lines(kind))
    if card:
        mode = card.get("mode") or ""
        supported = card.get("supported_generation") or []
        upstream = card.get("provider") or ""
        if mode:
            lines.append(f"hub mode: {mode}")
        if supported:
            lines.append(f"hub supported_generation: {supported}")
        if upstream:
            lines.append(f"hub upstream: {upstream}")
    else:
        lines.append("hub model card: not listed for this key")
    if last_job:
        lines.append("last generation:")
        for key in ("path", "seed", "size", "model", "prompt"):
            if last_job.get(key) not in (None, ""):
                lines.append(f"  {key}: {last_job[key]}")
        lines.append("To revise that result, pass its path in references and its seed unchanged.")
    return "\n".join(lines)
