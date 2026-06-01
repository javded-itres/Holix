import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import chromadb

from config import settings


class SkillsManager:
    """Manages agent skills - reusable patterns learned from successful tasks."""

    def __init__(self):
        self.skills_dir = Path(settings.skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.active_skills: List[Dict[str, Any]] = []
        self.all_skills: Dict[str, Dict[str, Any]] = {}

        # Initialize ChromaDB for semantic skill search
        self.chroma_client = chromadb.PersistentClient(
            path=str(Path(settings.vector_db_path).parent / "skills_db"),
        )
        self.skills_collection = self.chroma_client.get_or_create_collection(
            name="skills",
            metadata={"hnsw:space": "cosine"}
        )

    def load_all_skills(self) -> None:
        """Load all skills from the skills directory."""
        self.all_skills = {}

        for skill_file in self.skills_dir.glob("*.md"):
            try:
                skill = self._load_skill_file(skill_file)
                if skill:
                    self.all_skills[skill["name"]] = skill
                    # Add to vector DB for semantic search
                    self._index_skill(skill)
            except Exception as e:
                print(f"Error loading skill {skill_file}: {e}")

        print(f"Loaded {len(self.all_skills)} skills")

    def _index_skill(self, skill: Dict[str, Any]) -> None:
        """Index a skill in the vector database for semantic search.

        Args:
            skill: Skill dictionary
        """
        try:
            # Create searchable text from skill
            searchable_text = f"{skill.get('name', '')} {skill.get('description', '')} "
            searchable_text += f"{' '.join(skill.get('tags', []))} {skill.get('content', '')}"

            # Add to collection
            self.skills_collection.upsert(
                documents=[searchable_text],
                metadatas=[{
                    "name": skill.get("name", ""),
                    "description": skill.get("description", ""),
                    "tags": ",".join(skill.get("tags", [])),
                    "success_count": skill.get("success_count", 0),
                    "failure_count": skill.get("failure_count", 0),
                }],
                ids=[skill.get("name", "")]
            )
        except Exception as e:
            print(f"Warning: Failed to index skill {skill.get('name')}: {e}")

    def _load_skill_file(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """Load a single skill file.

        Args:
            filepath: Path to skill markdown file

        Returns:
            Skill dictionary or None
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split YAML frontmatter and markdown content
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    metadata = yaml.safe_load(parts[1])
                    markdown_content = parts[2].strip()

                    return {
                        **metadata,
                        "content": markdown_content,
                        "filepath": str(filepath)
                    }
                except yaml.YAMLError as e:
                    print(f"Error parsing YAML in {filepath}: {e}")
                    return None

        return None

    def get_relevant_skills(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Get skills relevant to the current query using semantic search.

        Args:
            query: User query or task description
            top_k: Maximum number of skills to return

        Returns:
            List of relevant skills
        """
        if not self.all_skills:
            self.load_all_skills()

        if not self.all_skills:
            return []

        try:
            # Use ChromaDB for semantic search
            results = self.skills_collection.query(
                query_texts=[query],
                n_results=min(top_k, len(self.all_skills))
            )

            relevant = []
            if results["ids"] and results["ids"][0]:
                for i, skill_name in enumerate(results["ids"][0]):
                    if skill_name in self.all_skills:
                        skill = self.all_skills[skill_name].copy()
                        # Add distance score (lower is better)
                        skill["relevance_distance"] = results["distances"][0][i] if results.get("distances") else 1.0
                        relevant.append(skill)

            # Sort by success rate and relevance
            relevant.sort(
                key=lambda x: (
                    x.get("relevance_distance", 1.0),  # Lower distance = more relevant
                    -(x.get("success_count", 0) / max(x.get("failure_count", 0) + 1, 1))
                )
            )

            return relevant[:top_k]

        except Exception as e:
            print(f"Error during semantic skill search: {e}")
            # Fallback to empty list
            return []

    async def should_create_skill(
        self,
        messages: List[Dict[str, Any]],
        final_result: str
    ) -> bool:
        """Determine if a skill should be created from this session.

        Args:
            messages: Conversation messages
            final_result: Final result/response

        Returns:
            True if skill should be created
        """
        # Heuristics for skill creation:
        # 1. Multiple tool calls were made
        # 2. Task was complex (more than 3 messages)
        # 3. Task completed successfully

        tool_calls_count = sum(
            1 for msg in messages
            if msg.get("role") == "tool"
        )

        message_count = len([m for m in messages if m.get("role") in ["user", "assistant"]])

        # Create skill if there were multiple tool calls and reasonable complexity
        should_create = (
            tool_calls_count >= 2 and
            message_count >= 3 and
            "error" not in final_result.lower()
        )

        return should_create

    def save_skill(
        self,
        name: str,
        description: str,
        content: str,
        tags: Optional[List[str]] = None,
        examples: Optional[List[str]] = None
    ) -> Path:
        """Save a new skill to disk.

        Args:
            name: Skill name (slug format)
            description: Brief description
            content: Markdown content with instructions
            tags: Optional list of tags
            examples: Optional list of example use cases

        Returns:
            Path to saved skill file
        """
        # Prepare metadata
        metadata = {
            "name": name,
            "description": description,
            "tags": tags or [],
            "success_count": 0,
            "failure_count": 0,
            "created_at": datetime.now().isoformat(),
            "last_used": None
        }

        if examples:
            metadata["examples"] = examples

        # Create skill file
        filepath = self.skills_dir / f"{name}.md"

        with open(filepath, 'w', encoding='utf-8') as f:
            # Write YAML frontmatter
            f.write("---\n")
            f.write(yaml.dump(metadata, default_flow_style=False))
            f.write("---\n\n")

            # Write markdown content
            f.write(content)

        # Index the new skill
        skill_data = self._load_skill_file(filepath)
        if skill_data:
            self.all_skills[name] = skill_data
            self._index_skill(skill_data)

        return filepath

    def update_skill_metrics(
        self,
        skill_name: str,
        success: bool
    ) -> None:
        """Update skill usage metrics.

        Args:
            skill_name: Name of the skill
            success: Whether the skill was used successfully
        """
        filepath = self.skills_dir / f"{skill_name}.md"

        if not filepath.exists():
            return

        skill = self._load_skill_file(filepath)
        if not skill:
            return

        # Update metrics
        if success:
            skill["success_count"] = skill.get("success_count", 0) + 1
        else:
            skill["failure_count"] = skill.get("failure_count", 0) + 1

        skill["last_used"] = datetime.now().isoformat()

        # Save updated skill
        with open(filepath, 'w', encoding='utf-8') as f:
            # Extract metadata
            metadata = {k: v for k, v in skill.items() if k not in ["content", "filepath"]}

            f.write("---\n")
            f.write(yaml.dump(metadata, default_flow_style=False))
            f.write("---\n\n")
            f.write(skill.get("content", ""))

        # Reload
        self.load_all_skills()

    def format_skills_for_prompt(
        self,
        skills: List[Dict[str, Any]]
    ) -> str:
        """Format skills for inclusion in the system prompt.

        Args:
            skills: List of skills

        Returns:
            Formatted string for prompt
        """
        if not skills:
            return ""

        output = "## Available Skills\n\n"
        output += "You have access to these learned patterns from previous successful tasks:\n\n"

        for i, skill in enumerate(skills, 1):
            output += f"### {i}. {skill.get('name', 'Unnamed')}\n"
            output += f"**Description:** {skill.get('description', 'No description')}\n"

            if skill.get('tags'):
                output += f"**Tags:** {', '.join(skill['tags'])}\n"

            output += f"\n{skill.get('content', '')}\n\n"
            output += "---\n\n"

        return output
