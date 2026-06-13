"""Holix TUI stylesheet fragments (composed by HolixTUI)."""

HOLIX_TUI_CSS = """

    Screen {
        layout: horizontal;   /* Sidebar + Main content */
        background: $surface;
    }

    /* === Sidebar === */
    #sidebar {
        width: 0;                 /* Collapsed by default */
        min-width: 0;
        background: $boost;
        border-right: thick $primary;
        padding: 1 1;
        overflow: hidden;         /* Hide content when collapsed */
    }

    #sidebar Static {
        margin-bottom: 1;
    }

    #sidebar .label {
        color: $text-muted;
        text-style: bold;
    }

    #sidebar .value {
        color: $text;
        margin-bottom: 1;
    }

    /* Make current profile more prominent (Phase 2 visual polish) */
    #sidebar-profile {
        text-style: bold;
        color: $accent;
    }

    /* Small density mode indicator in sidebar header (light theming) */
    .density-indicator {
        text-style: dim;
        color: $text-muted;
        margin-bottom: 1;
    }

    /* Tools list in sidebar (Phase 2 - dynamic Collapsible title, no separate label) */
    .tools-list {
        height: 8;           /* Compact, scrollable if many tools */
        border: tall $primary 30%;
        background: $boost;
    }

    .tools-list ListItem {
        padding: 0 1;
        color: $text-muted;
    }

    .tools-list ListItem:hover {
        background: $accent 20%;
        color: $text;
    }

    .tools-list ListItem.-highlighted {
        background: $accent 30%;
        color: $text;
    }

    /* Memory list in sidebar (Phase 2 - dynamic Collapsible title) */
    .memory-list {
        height: 6;           /* Even more compact */
        border: tall $secondary 30%;
        background: $boost;
    }

    .memory-list ListItem {
        padding: 0 1;
        color: $text-muted;
        text-style: dim;
    }

    .memory-list ListItem:hover {
        background: $secondary 20%;
        color: $text;
        text-style: none;
    }

    /* Sessions list in sidebar (Phase 2 - dynamic Collapsible title) */
    .sessions-list {
        height: 5;           /* Very compact for Phase 1 */
        border: tall $accent 25%;
        background: $boost;
    }

    .sessions-list ListItem {
        padding: 0 1;
        color: $text-muted;
        text-style: dim;
    }

    .sessions-list ListItem:hover {
        background: $accent 20%;
        color: $text;
    }

    .sessions-list ListItem.-highlighted {
        background: $accent 35%;
    }

    /* Skills list in sidebar (Phase 2 - dynamic Collapsible title + tags) */
    .skills-list {
        height: 6;
        border: tall $primary 20%;
        background: $boost;
    }

    .skills-list ListItem {
        padding: 0 1;
        color: $text-muted;
        text-style: dim;
    }

    .skills-list ListItem:hover {
        background: $primary 15%;
        color: $text;
        text-style: none;
    }

    .skills-list ListItem.-highlighted {
        background: $primary 25%;
    }

    /* Slash command suggestions dropdown (Phase 2) - polished */
    .command-suggestions {
        display: none;
        height: auto;
        max-height: 9;
        border: tall $accent;
        background: $panel;
        margin-bottom: 1;
    }

    .command-suggestions.-visible {
        display: block;
    }

    .command-suggestions ListItem {
        padding: 0 1;
        height: 1;
    }

    .command-suggestions ListItem:hover {
        background: $accent 25%;
    }

    .command-suggestions ListItem.-highlighted {
        background: $accent 45%;
    }

    /* Profiles list in sidebar (Phase 2 - dynamic Collapsible title, current marker) */
    .profiles-list {
        height: 5;
        border: tall $secondary 20%;
        background: $boost;
    }

    .profiles-list ListItem {
        padding: 0 1;
        color: $text-muted;
        text-style: dim;
    }

    .profiles-list ListItem:hover {
        background: $secondary 15%;
        color: $text;
        text-style: none;
    }

    .profiles-list ListItem.-highlighted {
        background: $secondary 25%;
    }

    /* === Density modes (Phase 2 - light customization) === */
    .density-compact #sidebar {
        padding: 0 1;
    }
    .density-compact .tools-list,
    .density-compact .memory-list,
    .density-compact .sessions-list,
    .density-compact .skills-list,
    .density-compact .profiles-list {
        height: 4;
    }
    .density-compact .tools-list ListItem,
    .density-compact .memory-list ListItem,
    .density-compact .sessions-list ListItem,
    .density-compact .skills-list ListItem,
    .density-compact .profiles-list ListItem,
    .density-compact .command-suggestions ListItem {
        padding: 0;
        height: 1;
        /* Slightly lift readability in ultra-dense mode while keeping hierarchy */
        color: $text-muted;
        text-style: none;
    }

    /* When a compact list is focused via keyboard, text must pop even more */
    .density-compact .tools-list:focus-within ListItem,
    .density-compact .memory-list:focus-within ListItem,
    .density-compact .sessions-list:focus-within ListItem,
    .density-compact .skills-list:focus-within ListItem,
    .density-compact .profiles-list:focus-within ListItem {
        color: $text;
    }

    /* Light theming: tighter chat area in compact mode */
    .density-compact #chat-log {
        padding: 0 1;
    }
    .density-compact #input-area {
        padding: 0 1;
        margin-top: 0;
    }

    .density-normal #sidebar {
        padding: 1 1;
    }
    .density-normal .tools-list { height: 8; }
    .density-normal .memory-list { height: 6; }
    .density-normal .sessions-list { height: 5; }
    .density-normal .skills-list { height: 6; }
    .density-normal .profiles-list { height: 5; }

    .density-comfort #sidebar {
        padding: 1 2;
    }
    .density-comfort .tools-list { height: 10; }
    .density-comfort .memory-list { height: 8; }
    .density-comfort .sessions-list { height: 6; }
    .density-comfort .skills-list { height: 8; }
    .density-comfort .profiles-list { height: 6; }
    .density-comfort #main-content {
        padding: 0 2;
    }

    /* Light theming: more breathing room for chat area in comfort mode */
    .density-comfort #chat-log {
        padding: 2 3;
        border: tall $primary 60%;
    }
    .density-comfort #input-area {
        padding: 1 2;
        margin-top: 2;
        border: tall $accent 60%;
    }

    /* Light theming: scale the scroll indicator banner with density */
    .density-compact .scroll-indicator {
        padding: 0;
        margin: 0 0 0 0;
    }
    .density-comfort .scroll-indicator {
        padding: 0 2;
        margin: 0 0 2 0;
    }

    /* Chat history uses RichLog (reliable streaming + panels). Selection/copy is best-effort via terminal or /copy commands. */

    Collapsible > .collapsible--title {
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    /* === Main content area === */
    #main-content {
        width: 1fr;
        layout: vertical;
        padding: 0 1;
    }

    #chat-log {
        height: 1fr;
        border: tall $primary;
        padding: 1 2;
        background: $panel;
    }

    #input-area {
        height: auto;
        min-height: 4;
        border: tall $accent;
        padding: 0 1;
        margin-top: 1;
        background: $panel;
    }

    TextArea {
        background: $panel;
        color: $text;
    }

    /* Scroll indicator banner - appears between chat log and input when user scrolled up
       and new messages arrived. Clickable (it's a Button) to jump to bottom. */
    .scroll-indicator {
        display: none;           /* Hidden by default via class toggle */
        height: 1;
        min-height: 1;
        background: $warning 25%;
        color: $text;
        text-align: center;
        padding: 0 1;
        border: tall $warning;
        margin: 0 0 1 0;         /* Small gap above input */
        text-style: bold;
    }

    .scroll-indicator.-visible {
        display: block;
    }

    /* Make the indicator button look like a banner, not a regular button */
    .scroll-indicator:hover {
        background: $warning 35%;
    }

    /* === Context usage bar (between chat log and input) === */
    #context-bar {
        height: 1;
        min-height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        margin-top: 0;
        margin-bottom: 0;
        content-align: left middle;
        text-style: bold;
    }

    /* === Focus states for strong keyboard navigation visibility (Phase 2 polish) === */
    /* Input gets a thicker accent border + lift when focused (very important for power users) */
    #input-area:focus {
        border: thick $accent;
        background: $boost;
    }

    /* Sidebar lists: when the ListView container receives focus (arrow keys), highlight its border */
    .tools-list:focus-within,
    .memory-list:focus-within,
    .sessions-list:focus-within,
    .skills-list:focus-within,
    .profiles-list:focus-within {
        border: tall $accent 70%;
    }

    /* Also ensure the highlighted item inside a focused list is extra visible */
    .tools-list:focus-within ListItem.-highlighted,
    .memory-list:focus-within ListItem.-highlighted,
    .sessions-list:focus-within ListItem.-highlighted,
    .skills-list:focus-within ListItem.-highlighted,
    .profiles-list:focus-within ListItem.-highlighted {
        background: $accent 40%;
        color: $text;
        text-style: bold;
    }
    """
