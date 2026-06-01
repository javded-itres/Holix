"""Skills management commands."""

import typer
from pathlib import Path

from cli.utils.rich_console import print_table, print_info, print_error, print_panel

app = typer.Typer(help="Manage Helix skills")


@app.command("list")
def list_skills(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of skills to show")
):
    """List all available skills."""
    config = ctx.obj["config"]
    skills_dir = Path(config.skills_dir)

    if not skills_dir.exists():
        print_info("No skills directory found")
        return

    skill_files = list(skills_dir.glob("*.md"))

    if not skill_files:
        print_info("No skills found")
        return

    rows = []
    for skill_file in skill_files[:limit]:
        name = skill_file.stem
        # Try to read description from YAML frontmatter
        try:
            with open(skill_file, 'r') as f:
                content = f.read()
                if content.startswith('---'):
                    import yaml
                    parts = content.split('---', 2)
                    if len(parts) >= 3:
                        metadata = yaml.safe_load(parts[1])
                        desc = metadata.get('description', '')[:60]
                        tags = ', '.join(metadata.get('tags', []))
                        rows.append([name, desc, tags])
                        continue
        except:
            pass

        rows.append([name, "N/A", ""])

    print_table(f"Skills ({len(skill_files)} total)", ["Name", "Description", "Tags"], rows)


@app.command("search")
def search_skills(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query")
):
    """Search skills by query."""
    config = ctx.obj["config"]

    # Simple file-based search
    skills_dir = Path(config.skills_dir)
    if not skills_dir.exists():
        print_info("No skills directory found")
        return

    matches = []
    query_lower = query.lower()

    for skill_file in skills_dir.glob("*.md"):
        with open(skill_file, 'r') as f:
            content = f.read().lower()
            if query_lower in content or query_lower in skill_file.stem.lower():
                matches.append(skill_file.stem)

    if matches:
        rows = [[name] for name in matches]
        print_table(f"Search Results ({len(matches)} found)", ["Skill Name"], rows)
    else:
        print_info(f"No skills found matching '{query}'")


@app.command("show")
def show_skill(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Skill name")
):
    """Show detailed information about a skill."""
    config = ctx.obj["config"]
    skill_file = Path(config.skills_dir) / f"{name}.md"

    if not skill_file.exists():
        print_error(f"Skill '{name}' not found")
        return

    with open(skill_file, 'r') as f:
        content = f.read()

    print_panel(content, title=f"Skill: {name}", border_style="cyan")
