"""Strict code-style TUI stylesheet."""

CODE_TUI_CSS = """
Screen {
    layout: vertical;
    background: $surface;
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

"""