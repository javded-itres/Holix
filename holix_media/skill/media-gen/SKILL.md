---
name: media-gen
description: Generate images and short videos from a prompt, or from user-uploaded reference photos (edit, combine, animate).
---

# Media generation

When the user asks to **нарисуй**, **сгенерируй картинку**, **imagine**, **make a video**, **сделай ролик**, **оживи фото**, **перерисуй**, **сделай из этих фото**:

1. Call `generate_image` or `generate_video` with a clear prompt (language of the user).
2. **Reference photos:** if the user already sent images (this turn or earlier — paths in «Вложения из Telegram/MAX»), pass those paths in `references`. Typical flow: they upload first, then say what to do. Do not ask them to send the files again. Do not `read_file` binary photos.
3. The tool writes a file under workspace `media/` and returns a `file://` Open link. In TUI, put that markdown link in the reply so the user can click it.
4. In TUI, never call `send_chat_files`. The Open link is already in the transcript.
5. In Telegram/MAX, the file is sent when auto_send is on. If the tool result does not contain `Sent N file(s)`, call `send_chat_files` with the saved path.
6. Never paste base64. Never claim the user received the file unless a messenger send was reported.

## Hard rule: do not assemble video yourself

Video comes **only** from `generate_video` (the configured model). The tool returns immediately and keeps running in the background with no timeout; a 502 is retried, not a failure. In TUI, wait for the Open link. In Telegram/MAX, the file is sent for you. Do **not**:

- install or call `ffmpeg` / `moviepy` / `opencv` to stitch frames
- turn a sequence of `generate_image` stills into an mp4
- write a Python/shell script that encodes video
- fake a clip from screenshots

Stills are `generate_image`. Motion is `generate_video` with the same prompt and `references` if the user sent photos.

Leave `provider` empty. Each model has a note in holix-media settings. A plain generate uses the text-only model. Pass `references` when the user attached a picture or asks to change, add, or interact with one; the tool then picks the model that accepts a reference.
