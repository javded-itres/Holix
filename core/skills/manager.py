import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
import yaml

from core.di.runtime_config import HolixRuntimeConfig
from core.memory.chroma_embeddings import get_or_create_collection
from core.skills.assignments import is_skill_allowed_for_agent


class SkillsManager:
    """Manages agent skills - reusable patterns learned from successful tasks."""

    def __init__(self, config: HolixRuntimeConfig | None = None):
        cfg = config or HolixRuntimeConfig.from_settings()
        self._config = cfg
        self.skills_dir = Path(cfg.skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.active_skills: list[dict[str, Any]] = []
        self.all_skills: dict[str, dict[str, Any]] = {}

        # Local project supplement (./.holix/skills) — loaded in addition to profile skills_dir
        from core.config_utils import get_local_skills_dir
        self._local_skills_dir: Path | None = get_local_skills_dir()
        if self._local_skills_dir:
            self._local_skills_dir.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB for semantic skill search
        self.chroma_client = chromadb.PersistentClient(
            path=str(Path(cfg.vector_db_path).parent / "skills_db"),
        )
        self.skills_collection = get_or_create_collection(
            self.chroma_client,
            name="skills",
            metadata={"hnsw:space": "cosine"},
        )
        self._index_hashes: dict[str, str] = {}

    @property
    def skill_assignments(self) -> dict[str, list[str]]:
        return dict(getattr(self._config, "skill_assignments", None) or {})

    def is_allowed_for_agent(self, skill: dict[str, Any], agent_slot: str = "main") -> bool:
        return is_skill_allowed_for_agent(skill, agent_slot, self.skill_assignments)

    def filter_skills_for_agent(
        self,
        skills: list[dict[str, Any]],
        agent_slot: str = "main",
    ) -> list[dict[str, Any]]:
        return [s for s in skills if self.is_allowed_for_agent(s, agent_slot)]

    def list_skill_names_for_agent(self, agent_slot: str = "main") -> list[str]:
        if not self.all_skills:
            self.load_all_skills()
        return sorted(
            name
            for name, skill in self.all_skills.items()
            if self.is_allowed_for_agent(skill, agent_slot)
        )

    def load_all_skills(self, *, defer_index: bool = False) -> None:
        """Load skills from profile dir, hub bundles (SKILL.md), and local .holix/skills."""
        from core.hub.normalize import discover_skill_files, parse_skill_file

        self.all_skills = {}
        self._defer_index = defer_index

        def _register(skill: dict[str, Any], source: str) -> None:
            name = skill.get("name")
            if not name:
                return
            existing = self.all_skills.get(name)
            if existing:
                if source == "local":
                    skill["_source"] = "local"
                    self.all_skills[name] = skill
                    if not defer_index:
                        self._index_skill(skill)
                return
            skill["_source"] = source
            self.all_skills[name] = skill
            if not defer_index:
                self._index_skill(skill)

        def _load_tree(d: Path, source: str) -> None:
            for skill_file in discover_skill_files(d):
                try:
                    parsed = parse_skill_file(skill_file)
                    skill = parsed if parsed else self._load_skill_file(skill_file)
                    if skill:
                        if "name" not in skill:
                            skill["name"] = (
                                skill_file.parent.name
                                if skill_file.name == "SKILL.md"
                                else skill_file.stem
                            )
                        _register(skill, source)
                except Exception as e:
                    print(f"Error loading skill {skill_file}: {e}")

        _load_tree(self.skills_dir, "profile")
        if self._local_skills_dir and self._local_skills_dir.exists():
            _load_tree(self._local_skills_dir, "local")

        print(f"Loaded {len(self.all_skills)} skills (profile + local supplements if any)")

    def _skill_searchable_text(self, skill: dict[str, Any]) -> str:
        searchable_text = f"{skill.get('name', '')} {skill.get('description', '')} "
        searchable_text += f"{' '.join(skill.get('tags', []))} {skill.get('content', '')}"
        return searchable_text

    def _skill_index_hash(self, skill: dict[str, Any]) -> str:
        return hashlib.sha256(self._skill_searchable_text(skill).encode()).hexdigest()[:16]

    def index_all_skills(self) -> int:
        """Index all loaded skills in Chroma (skips unchanged entries)."""
        indexed = 0
        for skill in self.all_skills.values():
            if self._index_skill(skill):
                indexed += 1
        self._defer_index = False
        return indexed

    def _index_skill(self, skill: dict[str, Any]) -> bool:
        """Index a skill in the vector database for semantic search.

        Args:
            skill: Skill dictionary

        Returns:
            True if the skill was upserted, False if skipped (unchanged).
        """
        name = skill.get("name", "")
        if not name:
            return False
        content_hash = self._skill_index_hash(skill)
        if self._index_hashes.get(name) == content_hash:
            return False
        try:
            searchable_text = self._skill_searchable_text(skill)

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
                ids=[name]
            )
            self._index_hashes[name] = content_hash
            return True
        except Exception as e:
            print(f"Warning: Failed to index skill {name}: {e}")
            return False

    def _load_skill_file(self, filepath: Path) -> dict[str, Any] | None:
        """Load a single skill file.

        Args:
            filepath: Path to skill markdown file

        Returns:
            Skill dictionary or None
        """
        with open(filepath, encoding='utf-8') as f:
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
        top_k: int = 5,
        *,
        agent_slot: str = "main",
    ) -> list[dict[str, Any]]:
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
                    if skill_name not in self.all_skills:
                        continue
                    skill = self.all_skills[skill_name].copy()
                    if not self.is_allowed_for_agent(skill, agent_slot):
                        continue
                    skill["relevance_distance"] = (
                        results["distances"][0][i] if results.get("distances") else 1.0
                    )
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
        messages: list[dict[str, Any]],
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

    def _attach_skill_to_agent(self, name: str, agent_slot: str) -> None:
        """Add skill to the creating agent's allowlist (runtime + profile when applicable)."""
        from core.skills.assignments import assign_created_skill

        assigns = assign_created_skill(self.skill_assignments, name, agent_slot)
        self._config = self._config.with_overrides(skill_assignments=assigns)

        profile = getattr(self._config, "profile_name", None) or "default"
        try:
            from cli.core import ProfileManager

            manager = ProfileManager()
            if not manager.profile_exists(profile):
                return
            cfg = manager.load_profile(profile)
            if Path(cfg.skills_dir).resolve() != self.skills_dir.resolve():
                return
            cfg_assigns = assign_created_skill(
                dict(getattr(cfg, "skill_assignments", {}) or {}),
                name,
                agent_slot,
            )
            cfg.skill_assignments = cfg_assigns
            manager.save_profile(profile, cfg)
        except Exception:
            return

    def save_skill(
        self,
        name: str,
        description: str,
        content: str,
        tags: list[str] | None = None,
        examples: list[str] | None = None,
        *,
        agent_slot: str = "main",
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
        from core.hub.normalize import slugify_skill_name

        name = slugify_skill_name(name)

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
            skill_data["_source"] = "profile"
            self.all_skills[name] = skill_data
            self._index_skill(skill_data)

        self._attach_skill_to_agent(name, agent_slot)

        try:
            from core.hub.slash_registry import rebuild_slash_registry

            rebuild_slash_registry(self.skills_dir)
        except Exception:
            pass

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
        skills: list[dict[str, Any]]
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
