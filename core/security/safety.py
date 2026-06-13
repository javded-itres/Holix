import re

from core.platform_compat import IS_WINDOWS

_UNIX_SAFE: set[str] = {
    "ls", "cat", "head", "tail", "less", "more",
    "find", "grep", "awk", "sed",
    "pwd", "whoami", "date", "uptime", "hostname",
    "df", "du", "free",
    "ps", "top", "htop",
    "ping", "curl", "wget", "dig", "nslookup",
    "git status", "git log", "git diff", "git show",
    "git branch", "git remote",
    "python", "python3", "node", "npm",
    "pip list", "pip show",
    "pytest", "npm test", "make test",
    "holix", "uv",
}

_WINDOWS_SAFE: set[str] = {
    "dir", "type", "more", "findstr", "where", "cd", "echo", "tree",
    "whoami", "hostname", "date", "systeminfo", "tasklist", "ipconfig",
    "ping", "curl", "nslookup",
    "git status", "git log", "git diff", "git show",
    "git branch", "git remote",
    "python", "python3", "py", "node", "npm",
    "pip list", "pip show",
    "pytest", "npm test",
    "holix", "uv",
}

_COMMON_DANGEROUS: list[str] = [
    r"rm\s+-rf",
    r">\s*/dev/",
    r"dd\s+",
    r"mkfs",
    r"fdisk",
    r"shutdown",
    r"reboot",
    r"killall",
    r":\(\)\{ :\|:& \};:",
    r"curl.*\|.*sh",
    r"wget.*\|.*sh",
]

_WINDOWS_DANGEROUS: list[str] = [
    r">\s*nul\b",
    r">\s*con\b",
    r"format\s+",
    r"diskpart",
    r"del\s+/[fq]",
    r"rmdir\s+/s",
]


_SHELL_CHAINING = re.compile(
    r"(?:&&|\|\||[;|&`$<>]|\$\(|\n|\r)"
)


class CommandWhitelist:
    """Manage allowed commands for terminal execution."""

    def __init__(self):
        self.safe_commands: set[str] = set(_WINDOWS_SAFE if IS_WINDOWS else _UNIX_SAFE)
        self.dangerous_patterns: list[str] = list(_COMMON_DANGEROUS)
        if IS_WINDOWS:
            self.dangerous_patterns.extend(_WINDOWS_DANGEROUS)

    def is_command_allowed(self, command: str) -> tuple[bool, str | None]:
        """Check if a command is safe to execute.

        Args:
            command: Command string to check

        Returns:
            Tuple of (is_allowed, reason)
        """
        command_lower = command.lower().strip()

        if _SHELL_CHAINING.search(command):
            return False, "Blocked shell chaining or redirection"

        for pattern in self.dangerous_patterns:
            if re.search(pattern, command_lower):
                return False, f"Blocked dangerous pattern: {pattern}"

        base_cmd = command_lower.split()[0] if command_lower else ""

        if base_cmd in self.safe_commands:
            return True, None

        for safe_cmd in self.safe_commands:
            if command_lower == safe_cmd or command_lower.startswith(f"{safe_cmd} "):
                return True, None

        return False, f"Command '{base_cmd}' not in whitelist"

    def add_to_whitelist(self, command: str):
        """Add a command to the whitelist."""
        self.safe_commands.add(command.lower())

    def remove_from_whitelist(self, command: str):
        """Remove a command from the whitelist."""
        self.safe_commands.discard(command.lower())

    def apply_extra(self, extra: str | None) -> None:
        """Add comma-separated commands from HOLIX_TERMINAL_WHITELIST_EXTRA."""
        if not extra:
            return
        for part in extra.split(","):
            cmd = part.strip().lower()
            if cmd:
                self.safe_commands.add(cmd)


class ConfirmationRequired:
    """Track operations that require user confirmation."""

    def __init__(self):
        self.confirmation_patterns = [
            r"rm\s+",
            r"mv\s+",
            r"git\s+push",
            r"git\s+commit",
            r"npm\s+install",
            r"pip\s+install",
            r"docker\s+run",
        ]
        if IS_WINDOWS:
            self.confirmation_patterns.extend([
                r"del\s+",
                r"rmdir\s+",
                r"move\s+",
                r"ren\s+",
            ])

    def requires_confirmation(self, command: str) -> bool:
        """Check if command requires user confirmation."""
        command_lower = command.lower().strip()

        for pattern in self.confirmation_patterns:
            if re.search(pattern, command_lower):
                return True

        return False


command_whitelist = CommandWhitelist()
confirmation_checker = ConfirmationRequired()