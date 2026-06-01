from typing import List, Set, Optional
import re


class CommandWhitelist:
    """Manage allowed commands for terminal execution."""

    def __init__(self):
        # Safe commands that don't modify system
        self.safe_commands: Set[str] = {
            # File viewing
            "ls", "cat", "head", "tail", "less", "more",
            "find", "grep", "awk", "sed",

            # System info
            "pwd", "whoami", "date", "uptime", "hostname",
            "df", "du", "free",

            # Process info
            "ps", "top", "htop",

            # Network (read-only)
            "ping", "curl", "wget", "dig", "nslookup",

            # Git (read-only)
            "git status", "git log", "git diff", "git show",
            "git branch", "git remote",

            # Python/Node
            "python", "python3", "node", "npm",
            "pip list", "pip show",

            # Development
            "pytest", "npm test", "make test",
        }

        # Dangerous patterns to block
        self.dangerous_patterns: List[str] = [
            r"rm\s+-rf",  # Recursive delete
            r">\s*/dev/",  # Writing to devices
            r"dd\s+",  # Disk operations
            r"mkfs",  # Format filesystem
            r"fdisk",  # Partition management
            r"shutdown",  # System shutdown
            r"reboot",  # System reboot
            r"killall",  # Kill all processes
            r":(){ :|:& };:",  # Fork bomb
            r"curl.*\|.*sh",  # Pipe to shell
            r"wget.*\|.*sh",  # Pipe to shell
        ]

    def is_command_allowed(self, command: str) -> tuple[bool, Optional[str]]:
        """Check if a command is safe to execute.

        Args:
            command: Command string to check

        Returns:
            Tuple of (is_allowed, reason)
        """
        command_lower = command.lower().strip()

        # Check dangerous patterns
        for pattern in self.dangerous_patterns:
            if re.search(pattern, command_lower):
                return False, f"Blocked dangerous pattern: {pattern}"

        # Extract base command
        base_cmd = command_lower.split()[0] if command_lower else ""

        # Check if base command is in whitelist
        if base_cmd in self.safe_commands:
            return True, None

        # Check if full command prefix is in whitelist
        for safe_cmd in self.safe_commands:
            if command_lower.startswith(safe_cmd):
                return True, None

        return False, f"Command '{base_cmd}' not in whitelist"

    def add_to_whitelist(self, command: str):
        """Add a command to the whitelist.

        Args:
            command: Command to add
        """
        self.safe_commands.add(command.lower())

    def remove_from_whitelist(self, command: str):
        """Remove a command from the whitelist.

        Args:
            command: Command to remove
        """
        self.safe_commands.discard(command.lower())


class ConfirmationRequired:
    """Track operations that require user confirmation."""

    def __init__(self):
        self.confirmation_patterns = [
            r"rm\s+",  # File deletion
            r"mv\s+",  # Moving files
            r"git\s+push",  # Git push
            r"git\s+commit",  # Git commit
            r"npm\s+install",  # Package installation
            r"pip\s+install",  # Package installation
            r"docker\s+run",  # Docker operations
        ]

    def requires_confirmation(self, command: str) -> bool:
        """Check if command requires user confirmation.

        Args:
            command: Command to check

        Returns:
            True if confirmation required
        """
        command_lower = command.lower().strip()

        for pattern in self.confirmation_patterns:
            if re.search(pattern, command_lower):
                return True

        return False


# Global instances
command_whitelist = CommandWhitelist()
confirmation_checker = ConfirmationRequired()
