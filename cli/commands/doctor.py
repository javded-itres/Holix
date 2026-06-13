"""holix doctor — diagnose and optionally fix Holix configuration."""

from __future__ import annotations

import asyncio

import typer

from cli.doctor.runner import run_doctor
from cli.utils.rich_console import print_error

app = typer.Typer(
    help="Diagnose Holix setup; repair with --fix (uses default LLM for config.yaml)",
    invoke_without_command=True,
)


@app.callback()
def doctor_main(
    ctx: typer.Context,
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Apply safe fixes and use default LLM to repair config.yaml",
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Skip LLM (deterministic fixes/checks only)",
    ),
    no_advice: bool = typer.Option(
        False,
        "--no-advice",
        help="Skip LLM remediation plan in check-only mode",
    ),
) -> None:
    """Check profile, LLM, gateway, and Telegram configuration.

    Without --fix: report issues and recommendations only.

    With --fix: create dirs, fix paths, gateway state, model/provider issues;
    broken config.yaml is repaired by the default LLM.

    Examples:
        holix doctor
        holix doctor --fix
        holix doctor --fix -p work
    """
    profile = ctx.obj["profile"]
    try:
        code = asyncio.run(
            run_doctor(
                profile,
                fix=fix,
                use_llm=not no_llm,
                llm_advice=not no_advice,
                skip_llm_check=no_llm,
            )
        )
    except Exception as e:
        print_error(f"Doctor failed: {e}")
        raise typer.Exit(1) from e
    raise typer.Exit(code)