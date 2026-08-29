import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from core.di.runtime_config import HolixRuntimeConfig
from core.memory.vector_backend import open_vector_backend, uses_on_disk_chroma
from core.skills.assignments import is_skill_allowed_for_agent
from core.skills.paths import join_under, resolve_under_any

# One-liners in the system prompt; extra skills stay behind skill_view().
_SKILLS_PROMPT_CAP = 32
_SKILL_DESC_LIMIT = 160


def _one_line(text: str, limit: int = _SKILL_DESC_LIMIT) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) > limit:
        return compact[: limit - 3] + "..."
    return compact or "No description"


def _skill_index_line(skill: dict[str, Any]) -> str:
    name = skill.get("name") or "Unnamed"
    desc = _one_line(skill.get("description") or "")
    extra: list[str] = []
    origin = str(skill.get("origin") or skill.get("_source") or "").strip()
    if origin:
        extra.append(origin)
    tags = skill.get("tags") or []
    if tags:
        extra.append(", ".join(str(t) for t in tags[:6]))
    suffix = f" ({'; '.join(extra)})" if extra else ""
    return f"- `{name}`: {desc}{suffix}"


def tool_names_from_messages(messages: list[dict[str, Any]]) -> set[str]:
    """Unique tool names from tool rows and assistant tool_calls.

    Sub-agent loops often store ``role=tool`` without ``name`` — only
    ``tool_call_id``. Fall back to the preceding assistant ``tool_calls``.
    """
    names: set[str] = set()
    for msg in messages:
        role = str(msg.get("role") or "")
        if role == "tool":
            names.add(str(msg.get("name") or msg.get("tool") or "").strip())
            continue
        if role != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            names.add(str((fn or {}).get("name") or tc.get("name") or "").strip())
    names.discard("")
    return names


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

        chroma_path = None
        if uses_on_disk_chroma(cfg):
            chroma_path = Path(cfg.vector_db_path).parent / "skills_db"
        self._backend = open_vector_backend(cfg, chroma_path=chroma_path)
        self.chroma_client = getattr(self._backend, "chroma_client", None)
        self.skills_collection = self._backend.get_collection("skills")
        self._index_hashes: dict[str, str] = {}

    def _skill_roots(self) -> list[Path]:
        roots = [self.skills_dir]
        if self._local_skills_dir is not None:
            roots.append(self._local_skills_dir)
        return roots

    def _confine_skill_path(self, filepath: Path | str) -> Path:
        return resolve_under_any(filepath, self._skill_roots())

    def _profile_skill_path(self, name: str) -> Path:
        from core.hub.normalize import slugify_skill_name

        safe = slugify_skill_name(name)
        if not safe:
            raise ValueError("invalid skill name")
        return join_under(self.skills_dir, f"{safe}.md")

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
                metadatas=[
                    {
                        "name": skill.get("name", ""),
                        "description": skill.get("description", ""),
                        "tags": ",".join(skill.get("tags", [])),
                        "success_count": skill.get("success_count", 0),
                        "failure_count": skill.get("failure_count", 0),
                    }
                ],
                ids=[name],
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
        filepath = self._confine_skill_path(filepath)
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        # Split YAML frontmatter and markdown content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    metadata = yaml.safe_load(parts[1])
                    markdown_content = parts[2].strip()

                    # Empty YAML frontmatter yields None; **None is TypeError.
                    return {
                        **(metadata or {}),
                        "content": markdown_content,
                        "filepath": str(filepath),
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
                query_texts=[query], n_results=min(top_k, len(self.all_skills))
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
                    -(x.get("success_count", 0) / max(x.get("failure_count", 0) + 1, 1)),
                )
            )

            return relevant[:top_k]

        except Exception as e:
            print(f"Error during semantic skill search: {e}")
            # Fallback to empty list
            return []

    async def should_create_skill(self, messages: list[dict[str, Any]], final_result: str) -> bool:
        """Determine if a skill should be created from this session.

        Args:
            messages: Conversation messages
            final_result: Final result/response

        Returns:
            True if skill should be created
        """
        from core.skills.dedup import (
            find_duplicate_skill,
            is_transient_failure_lesson,
            is_trivial_session,
        )

        tool_calls_count = sum(1 for msg in messages if msg.get("role") == "tool")
        tool_names = tool_names_from_messages(messages)
        message_count = len([m for m in messages if m.get("role") in ["user", "assistant"]])
        result = final_result or ""
        if "error" in result.lower():
            return False
        if is_trivial_session(messages, result):
            return False
        if is_transient_failure_lesson(messages, result):
            return False
        # Require a real workflow, not a two-call ping that still wrote a file.
        if tool_calls_count < 4 or message_count < 4 or len(tool_names) < 2:
            return False
        users = [
            str(m.get("content") or "")
            for m in messages
            if m.get("role") == "user" and str(m.get("content") or "").strip()
        ]
        if not self.all_skills:
            self.load_all_skills()
        if find_duplicate_skill(
            self.all_skills,
            name=users[0][:80] if users else "",
            description=users[0][:240] if users else "",
        ):
            return False
        return True

    def _attach_skill_to_agent(self, name: str, agent_slot: str) -> None:
        """Add skill to the creating agent's allowlist (runtime + profile when applicable)."""
        from core.skills.assignments import assign_created_skill

        assigns = assign_created_skill(self.skill_assignments, name, agent_slot)
        self._config = self._config.with_overrides(skill_assignments=assigns)

        profile = getattr(self._config, "profile_name", None) or "default"
        try:
            from core.profile import ProfileManager

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
        assign: bool = False,
        origin: str = "user",
        source_session: str = "",
        quality_score: int = 0,
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
        from core.skills.dedup import find_duplicate_skill, looks_like_junk_skill

        name = slugify_skill_name(name)
        if looks_like_junk_skill(name=name, description=description, tags=tags):
            raise ValueError(f"refusing junk skill {name!r}")
        if not self.all_skills:
            self.load_all_skills()
        dup = find_duplicate_skill(self.all_skills, name=name, description=description or "")
        if dup:
            try:
                existing_path = self._confine_skill_path(str(dup.get("filepath") or ""))
            except ValueError:
                existing_path = Path()
            if existing_path.is_file():
                return existing_path
            existing_path = self._profile_skill_path(str(dup.get("name") or name))
            if existing_path.is_file():
                return existing_path

        # Prepare metadata
        metadata = {
            "name": name,
            "description": description,
            "tags": tags or [],
            "success_count": 0,
            "failure_count": 0,
            "created_at": datetime.now().isoformat(),
            "last_used": None,
            "origin": origin or "user",
            "use_count": 0,
            "quality_score": int(quality_score or 0),
        }
        if source_session:
            metadata["source_session"] = source_session

        if examples:
            metadata["examples"] = examples

        # Create skill file
        filepath = self._profile_skill_path(name)

        with open(filepath, "w", encoding="utf-8") as f:
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

        if assign:
            self._attach_skill_to_agent(name, agent_slot)

        try:
            from core.hub.slash_registry import rebuild_slash_registry

            rebuild_slash_registry(self.skills_dir)
        except Exception:
            pass

        return filepath

    def patch_skill(
        self,
        name: str,
        *,
        description: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> Path:
        """Update an existing skill in place (no new slug, no auto-assign)."""
        from core.hub.normalize import slugify_skill_name

        name = slugify_skill_name(name)
        if not self.all_skills:
            self.load_all_skills(defer_index=True)
        skill = self.all_skills.get(name)
        if not skill:
            raise FileNotFoundError(name)
        try:
            filepath = self._confine_skill_path(str(skill.get("filepath") or ""))
        except ValueError:
            filepath = self._profile_skill_path(name)
        if not filepath.is_file():
            filepath = self._profile_skill_path(name)
        if not filepath.is_file():
            raise FileNotFoundError(name)
        current = self._load_skill_file(filepath) or dict(skill)
        if description:
            current["description"] = description
        if tags is not None:
            current["tags"] = tags
        if content is not None:
            current["content"] = content
        current["updated_at"] = datetime.now().isoformat()
        current.pop("filepath", None)
        body = current.pop("content", "") or ""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write(yaml.dump(current, default_flow_style=False))
            f.write("---\n\n")
            f.write(body)
        reloaded = self._load_skill_file(filepath)
        if reloaded:
            reloaded["_source"] = skill.get("_source") or "profile"
            self.all_skills[name] = reloaded
            self._index_skill(reloaded)
        return filepath

    def update_skill_metrics(self, skill_name: str, success: bool) -> None:
        """Update skill usage metrics.

        Args:
            skill_name: Name of the skill
            success: Whether the skill was used successfully
        """
        try:
            filepath = self._profile_skill_path(skill_name)
        except ValueError:
            return

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
        with open(filepath, "w", encoding="utf-8") as f:
            # Extract metadata
            metadata = {k: v for k, v in skill.items() if k not in ["content", "filepath"]}

            f.write("---\n")
            f.write(yaml.dump(metadata, default_flow_style=False))
            f.write("---\n\n")
            f.write(skill.get("content", ""))

        # Reload
        self.load_all_skills()

    def is_inline_skill(self, skill: dict[str, Any]) -> bool:
        """Deprecated: skill bodies are never auto-inlined (use skill_view)."""
        del skill
        return False

    def mark_skill_used(self, name: str, *, conversation_id: str = "") -> None:
        """Bump use_count / last_used when a skill is viewed or inlined."""
        if not name:
            return
        if not self.all_skills:
            self.load_all_skills(defer_index=True)
        skill = self.all_skills.get(name)
        if not skill:
            return
        origin = str(skill.get("origin") or skill.get("_source") or "")
        source_session = str(skill.get("source_session") or "")
        skill["use_count"] = int(skill.get("use_count") or 0) + 1
        skill["last_used"] = datetime.now().isoformat()
        if (
            conversation_id
            and origin in {"agent", "learn"}
            and source_session
            and source_session != conversation_id
        ):
            try:
                from core.achievements.engine import record_skill_signal

                record_skill_signal(
                    self.skills_dir,
                    "reused",
                    evidence={"skill_name": name, "conversation_id": conversation_id},
                )
            except Exception:
                pass
        try:
            filepath = self._confine_skill_path(str(skill.get("filepath") or ""))
        except ValueError:
            return
        if not filepath.is_file():
            return
        current = self._load_skill_file(filepath)
        if not current:
            return
        current["use_count"] = skill["use_count"]
        current["last_used"] = skill["last_used"]
        body = current.pop("content", "") or ""
        current.pop("filepath", None)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("---\n")
                f.write(yaml.dump(current, default_flow_style=False))
                f.write("---\n\n")
                f.write(body)
        except OSError:
            return

    def format_skills_for_prompt(
        self,
        skills: list[dict[str, Any]],
        *,
        include_body: bool = False,
        suggested_names: list[str] | None = None,
        catalog_total: int | None = None,
    ) -> str:
        """Compact skill index for the system prompt.

        Bodies are omitted unless ``include_body`` is True. The model must call
        ``skill_view(name)`` before following a procedure.
        """
        if not skills:
            return ""

        suggested_order = [str(n) for n in (suggested_names or []) if n]
        suggested_set = set(suggested_order)
        by_name: dict[str, dict[str, Any]] = {}
        rest: list[dict[str, Any]] = []
        for skill in skills:
            name = str(skill.get("name") or "")
            if name:
                by_name[name] = skill
            if name and name in suggested_set:
                continue
            rest.append(skill)
        rest.sort(key=lambda s: str(s.get("name") or "").lower())
        suggested_skills = [by_name[n] for n in suggested_order if n in by_name]

        lines = [
            "## Available Skills",
            "",
            "Compact index only — no SKILL.md bodies. "
            "Call `skill_view(name)` before following a skill. "
            "`skill_view()` with no name lists every installed skill. "
            "To save a procedure, call `skill_manage` "
            "(it stages a draft for approval — it does not write live skills).",
            "",
        ]
        if suggested_skills:
            lines.append("Suggested for this turn:")
            for skill in suggested_skills:
                lines.append(_skill_index_line(skill))
            lines.append("")
        if rest:
            lines.append("Installed:")
            for skill in rest:
                lines.append(_skill_index_line(skill))
            lines.append("")
        if catalog_total and catalog_total > len(skills):
            lines.append(
                f"Index truncated ({len(skills)} of {catalog_total}). "
                "Call `skill_view()` with no name for the rest."
            )
            lines.append("")
        if include_body:
            lines.append("Full bodies (debug):")
            for skill in [*suggested_skills, *rest]:
                name = skill.get("name", "Unnamed")
                body = (skill.get("content") or "").strip()
                if body:
                    lines.append(f"### {name}\n{body}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def skills_prompt_block(
        self,
        query: str,
        *,
        agent_slot: str = "main",
        top_k: int = 5,
        cap: int | None = None,
    ) -> str:
        """Index of skills allowed for *agent_slot*, with query-relevant names first."""
        limit = _SKILLS_PROMPT_CAP if cap is None else cap
        if not self.all_skills:
            self.load_all_skills(defer_index=True)
        allowed = [
            skill
            for skill in self.all_skills.values()
            if self.is_allowed_for_agent(skill, agent_slot)
        ]
        if not allowed:
            return ""
        allowed.sort(key=lambda s: str(s.get("name") or "").lower())
        suggested = self.get_relevant_skills(
            query or "",
            top_k=top_k,
            agent_slot=agent_slot,
        )
        suggested_names = [str(skill.get("name") or "") for skill in suggested if skill.get("name")]
        catalog_total = len(allowed)
        shown = allowed
        if catalog_total > limit:
            by_name = {str(s.get("name") or ""): s for s in allowed}
            ordered: list[str] = []
            for name in suggested_names:
                if name in by_name and name not in ordered:
                    ordered.append(name)
                if len(ordered) >= limit:
                    break
            for skill in allowed:
                name = str(skill.get("name") or "")
                if name and name not in ordered:
                    ordered.append(name)
                if len(ordered) >= limit:
                    break
            shown = [by_name[n] for n in ordered if n in by_name][:limit]
        shown_names = {str(s.get("name") or "") for s in shown}
        return self.format_skills_for_prompt(
            shown,
            suggested_names=[n for n in suggested_names if n in shown_names],
            catalog_total=catalog_total if catalog_total > len(shown) else None,
        )
