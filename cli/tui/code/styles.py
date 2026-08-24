"""Strict code-style TUI stylesheet."""

CODE_TUI_CSS = """
Screen {
    layout: vertical;
    background: $surface;
}

#process-bar {
    display: none;
    height: auto;
    max-height: 6;
    background: $success 12%;
    color: $text;
}

#process-bar.visible {
    display: block;
}

#process-bar .process-bar-row {
    height: 1;
    padding: 0 1;
}

#process-bar .process-bar-row:hover {
    background: $success 22%;
    text-style: bold;
}

#transcript {
    height: 1fr;
    border: none;
    padding: 0 1;
    scrollbar-gutter: stable;
}

#thinking-line {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    text-style: dim;
}

#stream-line {
    height: auto;
    max-height: 10;
    padding: 0 1;
    overflow-y: auto;
    border-top: solid $primary 15%;
}

#status-bar {
    height: 1;
    padding: 0 1;
    background: $boost;
    color: $text-muted;
    text-style: dim;
}

#context-bar {
    height: 1;
    min-height: 1;
    padding: 0 1;
    background: $boost;
    color: $text;
}

#input-area {
    height: 5;
    min-height: 3;
    max-height: 8;
    border-top: solid $primary 20%;
    padding: 0 1;
}

#scroll-hint {
    height: 1;
    display: none;
    padding: 0 1;
    color: $warning;
    text-style: italic;
}

#scroll-hint.visible {
    display: block;
}

#prompt-queue {
    display: none;
    height: auto;
    max-height: 8;
    overflow-y: auto;
    background: $warning 18%;
    border-top: solid $warning;
    border-bottom: solid $warning;
    padding: 0 1 0 1;
}

#prompt-queue.visible {
    display: block;
}

#queue-header {
    height: 1;
    color: $warning;
}

#queue-rows {
    height: auto;
}

#prompt-queue .queue-row {
    height: 1;
    layout: horizontal;
    background: $warning 10%;
}

#prompt-queue .queue-row:hover {
    background: $warning 28%;
}

#prompt-queue .queue-label {
    width: 1fr;
    height: 1;
    padding: 0 1 0 0;
}

#prompt-queue Button {
    min-width: 6;
    width: auto;
    height: 1;
    min-height: 1;
    border: none;
    padding: 0 1;
    background: $warning 30%;
}

#prompt-queue Button.queue-del {
    min-width: 3;
    background: $error 35%;
}

#prompt-queue Button:hover {
    background: $warning 50%;
}

#prompt-queue Button.queue-del:hover {
    background: $error 55%;
}

#command-suggestions {
    display: none;
    height: auto;
    max-height: 9;
    border: tall $accent;
    background: $panel;
    margin: 0 1;
}

#command-suggestions.-visible {
    display: block;
}

#command-suggestions ListItem {
    padding: 0 1;
    height: 1;
}

#command-suggestions ListItem:hover {
    background: $accent 25%;
}

#command-suggestions ListItem.-highlighted {
    background: $accent 45%;
}

#prompt-history {
    display: none;
    height: auto;
    max-height: 6;
    border: tall $primary 25%;
    background: $panel;
    margin: 0 1;
}

#prompt-history.-visible {
    display: block;
}

#prompt-history ListItem {
    padding: 0 1;
    height: 1;
}

#prompt-history ListItem:hover {
    background: $primary 20%;
}

#prompt-history ListItem.-highlighted {
    background: $primary 40%;
}

"""
