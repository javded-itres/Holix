---
name: holix-ssh
description: >
  Run a command on another machine with ssh_exec. Use when the user names a
  server, host, IP, or asks to SSH. Do not assemble ssh, scp, or sftp in the
  local shell.
tags:
  - ssh
  - remote
  - holix
  - required
required: true
user-invocable: true
---

## When to use

The user wants a command, file read, or service check on another machine.
Load this skill with `skill_view` before the first remote call of the task.

## Procedure

1. Call `ssh_exec`. `host` and `command` are separate arguments.
2. `host` is an alias from the SSH config list in the system prompt, or `user@host` when the user gave an address and there is no alias. Do not invent a user when that list already names one.
3. Put a script in `stdin`. Do not build a local heredoc and do not wrap the command in quotes for the local shell.
4. Timeout defaults to 120 seconds. Raise it up to 600 only when the remote command needs it.
5. If the result is an error, show stderr to the user and stop. One failure is enough.

## Do not

- Do not call `run_terminal_command` with `ssh`, `scp`, or `sftp`.
- Do not allocate a TTY, run `ssh -v`, or run `ssh-add`.
- Do not append `&` or poll a background SSH session.
- Do not put SSH options in `host` (`-o`, `ProxyCommand`, an empty host).
- Do not print keys, tokens, or the contents of `.ssh`.

## Examples

```
ssh_exec(host="ai-server-local", command="uname -a")
ssh_exec(host="user@192.168.0.10", command="python3 -", stdin="<script>")
```

## Verification

- The turn used `ssh_exec`, not a local `ssh` string.
- A failure was reported once, without a second connection attempt.
