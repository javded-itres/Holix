"""The generation tool picks a text-only or reference model from the prompt."""

from holix_media.config import MediaProvider
from holix_media.select import choose_provider, request_needs_reference


def _model(pid: str, *, note: str, accepts: bool | None) -> MediaProvider:
    return MediaProvider(
        id=pid,
        kind="image",
        type="openai_images",
        base_url="http://hub/v1",
        api_key_env="MIKROLLM_API_KEY",
        model=pid,
        note=note,
        accepts_reference=accepts,
    )


def test_plain_prompt_uses_the_text_only_model() -> None:
    text = _model("zimage", note="Только текст в изображение", accepts=False)
    edit = _model("edit", note="Правка по референсу", accepts=True)
    chosen, problem = choose_provider(
        [edit, text],
        prompt="сгенерируй изображение кота",
        has_references=False,
    )
    assert problem == ""
    assert chosen is not None and chosen.id == "zimage"


def test_edit_without_a_file_does_not_start_a_text_model() -> None:
    text = _model("zimage", note="text to image", accepts=False)
    edit = _model("edit", note="принимает референс", accepts=True)
    assert request_needs_reference("измени изображение, добавь шляпу", has_references=False)
    chosen, problem = choose_provider(
        [text, edit],
        prompt="измени изображение, добавь шляпу",
        has_references=False,
    )
    assert chosen is None
    assert "references" in problem
    assert "edit" in problem


def test_attached_image_uses_the_reference_model() -> None:
    text = _model("zimage", note="только текст", accepts=False)
    edit = _model("edit", note="добавление по присланному изображению", accepts=True)
    chosen, problem = choose_provider(
        [text, edit],
        prompt="добавь розу",
        has_references=True,
    )
    assert problem == ""
    assert chosen is not None and chosen.id == "edit"


def test_note_alone_marks_a_text_model_when_the_flag_is_omitted() -> None:
    text = _model("zimage", note="Только текст в изображение, без референса", accepts=None)
    edit = _model("edit", note="Правка по референсу", accepts=None)
    chosen, _problem = choose_provider(
        [edit, text],
        prompt="сгенерируй изображение",
        has_references=False,
    )
    assert chosen is not None and chosen.id == "zimage"


def test_yaml_keeps_the_note_and_the_flag() -> None:
    from holix_media.config import load_media_config

    cfg = load_media_config(
        {
            "image_providers": [
                {
                    "id": "zimage",
                    "type": "openai_images",
                    "base_url": "http://hub/v1",
                    "api_key_env": "MIKROLLM_API_KEY",
                    "model": "image-z-image-turbo",
                    "note": "Только текст",
                    "accepts_reference": False,
                }
            ]
        }
    )
    provider = cfg.image_providers[0]
    assert provider.note == "Только текст"
    assert provider.accepts_reference is False
