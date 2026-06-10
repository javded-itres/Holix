from datetime import datetime
from pathlib import Path
from typing import Any


class MarkdownMemory:
    """Manages human-readable markdown-based memory."""

    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            from core.paths import resolve_profile_data_dir

            base_dir = str(resolve_profile_data_dir() / "memory" / "markdown")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_to_markdown(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
        title: str | None = None
    ) -> Path:
        """Save conversation to a markdown file.

        Args:
            conversation_id: Conversation identifier
            messages: List of messages
            title: Optional conversation title

        Returns:
            Path to saved markdown file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{conversation_id}_{timestamp}.md"
        filepath = self.base_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            # Write header
            f.write(f"# {title or f'Conversation {conversation_id}'}\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Conversation ID:** {conversation_id}\n\n")
            f.write("---\n\n")

            # Write messages
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")

                if role == "user":
                    f.write(f"## 👤 User\n\n{content}\n\n")
                elif role == "assistant":
                    f.write(f"## 🤖 Assistant\n\n{content}\n\n")
                elif role == "system":
                    f.write(f"## ⚙️ System\n\n{content}\n\n")
                elif role == "tool":
                    f.write(f"## 🔧 Tool Output\n\n```\n{content}\n```\n\n")

                f.write("---\n\n")

        return filepath

    def load_relevant_markdown_files(
        self,
        query: str = "",
        limit: int = 5
    ) -> list[dict[str, Any]]:
        """Load relevant markdown conversation files.

        Args:
            query: Optional search query
            limit: Maximum number of files to return

        Returns:
            List of file information
        """
        files = []

        for md_file in sorted(self.base_dir.glob("*.md"), reverse=True):
            if len(files) >= limit:
                break

            files.append({
                "path": str(md_file),
                "name": md_file.name,
                "modified": datetime.fromtimestamp(md_file.stat().st_mtime).isoformat()
            })

        return files

    def get_markdown_content(self, filepath: str) -> str:
        """Read markdown file content.

        Args:
            filepath: Path to markdown file

        Returns:
            File content
        """
        try:
            with open(filepath, encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"
