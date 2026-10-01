"""Seed stays stable when an edit references a previous generation."""

from pathlib import Path

from holix_media.config import MediaProvider
from holix_media.params import choose_seed, format_model_card, write_generation_meta
from holix_media.refs import ReferenceImage


def test_edit_appends_to_the_saved_prompt(tmp_path: Path) -> None:
    from holix_media.params import compose_edit_prompt

    image = tmp_path / "shot.png"
    image.write_bytes(b"png")
    write_generation_meta(
        image,
        {"seed": 4242, "prompt": "A poster of a man and a woman with a hammer and sickle"},
    )
    ref = ReferenceImage(path=image, mime="image/png", data=b"png")
    merged = compose_edit_prompt("Add a bright sun on the horizon.", [ref])
    assert merged == (
        "A poster of a man and a woman with a hammer and sickle\nAdd a bright sun on the horizon."
    )
    again = compose_edit_prompt(merged + "\nMake the sun blue.", [ref])
    assert again.startswith("A poster of a man and a woman with a hammer and sickle\n")
    assert again.endswith("Make the sun blue.")


def test_edit_reuses_seed_from_the_reference_file(tmp_path: Path) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"png")
    write_generation_meta(image, {"seed": 4242, "size": "1024x1024", "path": str(image)})
    ref = ReferenceImage(path=image, mime="image/png", data=b"png")
    assert choose_seed(None, [ref]) == 4242
    assert choose_seed(7, [ref]) == 7


def test_model_card_lists_seed_size_and_references() -> None:
    provider = MediaProvider(
        id="mikrollm",
        kind="image",
        type="openai_images",
        base_url="http://192.168.88.1:4000/v1",
        api_key_env="",
        model="image-z-image-turbo",
        extra={"api_key": "test"},
    )
    text = format_model_card(
        provider,
        kind="image",
        record={"mode": "image_generation", "supported_generation": ["image"]},
        last_job={"path": "/tmp/shot.png", "seed": 4242, "size": "1024x1024"},
    )
    assert "seed" in text
    assert "size" in text
    assert "references" in text
    assert "4242" in text
    assert "image_generation" in text
