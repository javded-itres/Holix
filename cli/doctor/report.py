"""Render doctor findings to the terminal."""

from __future__ import annotations

from cli.doctor.findings import DoctorFinding, Severity
from cli.utils.rich_console import print_info, print_panel, print_success, print_warning

_SEVERITY_STYLE = {
    Severity.ERROR.value: "bold red",
    Severity.WARNING.value: "yellow",
    Severity.INFO.value: "cyan",
}


def print_findings(findings: list[DoctorFinding]) -> None:
    if not findings:
        print_success("No issues found — Helix looks healthy.")
        return

    errors = [f for f in findings if f.severity == Severity.ERROR.value]
    warnings = [f for f in findings if f.severity == Severity.WARNING.value]
    infos = [f for f in findings if f.severity == Severity.INFO.value]

    lines: list[str] = []
    for group, label in (
        (errors, "Errors"),
        (warnings, "Warnings"),
        (infos, "Info"),
    ):
        if not group:
            continue
        lines.append(f"[bold]{label}[/bold]")
        for f in group:
            style = _SEVERITY_STYLE.get(f.severity, "white")
            fix_hint = " [dim](auto-fixable)[/dim]" if f.auto_fixable else ""
            lines.append(f"  [{style}]• {f.title}[/{style}]{fix_hint}")
            lines.append(f"    {f.detail}")
            lines.append(f"    [dim]→ {f.recommendation}[/dim]")
        lines.append("")

    print_panel(
        "\n".join(lines).rstrip(),
        title=f"Doctor — {len(errors)} error(s), {len(warnings)} warning(s)",
        border_style="red" if errors else "yellow" if warnings else "cyan",
    )


def print_applied_fixes(actions: list[str]) -> None:
    if not actions:
        return
    body = "\n".join(f"  [green]✓[/green] {a}" for a in actions)
    print_panel(body, title="Fixes applied", border_style="green")


def print_llm_note(message: str) -> None:
    print_panel(message, title="Doctor (LLM)", border_style="cyan")


def print_summary(
    *,
    fix_mode: bool,
    error_count: int,
    warning_count: int,
) -> None:
    if error_count == 0 and warning_count == 0:
        return
    if fix_mode:
        if error_count == 0:
            print_success("Doctor finished — no remaining errors.")
        else:
            print_warning(f"Doctor finished — {error_count} error(s) still need attention.")
    else:
        print_info("Dry run (no changes). Re-run with --fix to apply safe fixes and LLM config repair.")