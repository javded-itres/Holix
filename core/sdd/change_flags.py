"""Per-change flags stored beside the OpenSpec change directory."""

from __future__ import annotations

from core.sdd.paths import change_dir, validate_change_id

CHANGE_FLAGS_FILE = ".sdd.yaml"


def _flags_path(workspace, change_id: str):
    cid = validate_change_id(change_id)
    return change_dir(workspace, cid) / CHANGE_FLAGS_FILE


def as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def load_skip_specs(workspace, change_id: str) -> bool:
    """True when this change declares it has no behavior spec to merge."""
    path = _flags_path(workspace, change_id)
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        if key.strip() != "skip_specs":
            continue
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def save_skip_specs(workspace, change_id: str, enabled: bool) -> None:
    path = _flags_path(workspace, change_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "skip_specs: true\n" if enabled else "skip_specs: false\n",
        encoding="utf-8",
    )
