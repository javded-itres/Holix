"""Orchestrate holix doctor checks and fixes."""

from __future__ import annotations

from cli.doctor.checks import run_all_checks
from cli.doctor.findings import DoctorFinding, Severity
from cli.doctor.fixes import apply_deterministic_fixes
from cli.doctor.llm_doctor import llm_remediation_advice, llm_repair_profile
from cli.doctor.report import (
    print_applied_fixes,
    print_findings,
    print_llm_note,
    print_summary,
)
from cli.utils.rich_console import print_error, print_info


def _needs_llm_config_fix(findings: list[DoctorFinding]) -> bool:
    llm_codes = {
        "profile.invalid_yaml",
        "profile.invalid_structure",
        "profile.validation_error",
    }
    return any(f.code in llm_codes and f.severity == Severity.ERROR.value for f in findings)


async def run_doctor(
    profile: str,
    *,
    fix: bool = False,
    use_llm: bool = True,
    llm_advice: bool = True,
    skip_llm_check: bool = False,
) -> int:
    """Run doctor. Exit code 1 if errors remain."""
    print_info(f"Holix Doctor — profile [cyan]{profile}[/cyan]")
    if fix:
        print_info("Mode: [bold]fix[/bold] (deterministic + LLM config repair)")
    else:
        print_info("Mode: [bold]check only[/bold] (use --fix to apply repairs)")

    findings = await run_all_checks(profile, skip_llm_check=skip_llm_check)
    print_findings(findings)

    applied: list[str] = []

    if fix:
        applied.extend(apply_deterministic_fixes(profile, findings))
        if applied:
            print_applied_fixes(applied)
            findings = await run_all_checks(profile, skip_llm_check=skip_llm_check)
            if findings:
                print_info("Re-check after deterministic fixes:")
                print_findings(findings)

        if use_llm and _needs_llm_config_fix(findings):
            print_info("Asking default LLM to repair config.yaml…")
            ok, msg = await llm_repair_profile(profile, findings)
            if ok:
                applied.append(msg)
                print_applied_fixes([msg])
                findings = await run_all_checks(profile, skip_llm_check=skip_llm_check)
                if findings:
                    print_info("Re-check after LLM repair:")
                    print_findings(findings)
            else:
                print_error(msg)

    elif use_llm and llm_advice and any(f.severity == Severity.ERROR.value for f in findings):
        advice = await llm_remediation_advice(profile, findings)
        if advice:
            print_llm_note(advice)

    errors = sum(1 for f in findings if f.severity == Severity.ERROR.value)
    warnings = sum(1 for f in findings if f.severity == Severity.WARNING.value)
    print_summary(fix_mode=fix, error_count=errors, warning_count=warnings)

    return 1 if errors else 0