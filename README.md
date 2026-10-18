# goals-iterm-skill

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

Let a coding agent use [goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp) to direct Claude Code, Codex, and other CLIs running in iTerm2, monitor their progress, advise on decisions, and verify completion.

## Install through a coding agent

Copy the prompt below to a coding agent with local filesystem access. Replace `[target client]` with the client where you want to install the skill. For an existing checkout, you can replace the repository URL with its absolute local path.

```text
Please install goals-iterm-skill for [target client].
Repository: https://github.com/lucky-goals/goals-iterm-skill

1. Check the target client's existing configuration and supported skill installation
   mechanism. Use its documented location and scope; do not guess configuration paths.
2. Fetch the repository or use the local checkout I specified. Inspect SKILL.md and
   its referenced files. The repository root is the skill package.
3. Install it as goals-iterm-skill, preserving SKILL.md, references/, and agents/.
   Do not copy only SKILL.md. If an installation already exists, compare it first,
   preserve local changes, and back it up before updating. Leave other skills intact.
4. Check whether this client has goals-iterm-mcp connected. Installing the skill
   does not install the MCP server. If it is missing, report the prerequisite and
   provide setup instructions; do not change unrelated MCP configuration.
5. Validate the skill metadata and relative references. Reload skills using the
   client's supported mechanism, or tell me exactly which manual reload is needed.
   Confirm that the target client discovers the skill when this can be checked.
6. If the MCP is available, validate tool discovery and use only list_sessions for
   the connection check. During installation, do not read terminal contents, send
   input, create windows, or launch coding tasks.
7. Report the installation path, skill discovery status, MCP readiness, and available
   monitoring mode: host scheduling/wakeups or polling during an active agent run.
   Do not claim background monitoring works without an actual wakeup mechanism.
```

## Prerequisites and manual installation

The repository root is a skill package. Install the whole directory under the name `goals-iterm-skill` using the host client's supported skill mechanism. Keep `SKILL.md`, `references/`, and `agents/` together so relative references remain valid. Follow the target client's documentation and existing configuration for the installation location and reload procedure.

This skill does not install MCP or provide a standalone background service. Connect goals-iterm-mcp in the host client, enable the iTerm2 Python API, and prepare the target CLI and its authentication in the terminal. Required tools cover session listing, screen/history reading, and text/key input; creating terminals also requires the corresponding creation tools.

Continuous monitoring requires host scheduling/wakeups or polling within an active agent run. Without background wakeups, monitoring cannot continue after the agent run ends. The skill requires the agent to report this limitation explicitly.

## Example

```text
Use goals-iterm-skill to have Claude Code in iTerm fix the login issue in
/path/to/project. Diagnose first, then fix it and run only relevant tests.
Monitor after every instruction, make routine technical decisions, and recover
from network failures only when the task has stopped and will not resume itself.
After acceptance checks pass, stop monitoring and summarize changes, tests,
and remaining issues. Do not publish.
```

You can also name an existing session to take over its task. The skill resolves the exact `session_id` first and avoids resubmitting work already in progress.

## Maintenance and validation

The entry point is [SKILL.md](SKILL.md). See [iterm-tools.md](references/iterm-tools.md) for tool semantics and [monitoring.md](references/monitoring.md) for monitoring, recovery, and behavioral validation scenarios. These instruction files are currently in Simplified Chinese. Tool conventions are based on `src/goals_iterm_mcp/direct.py` in cc-iterm-mcp; the installed tool schema takes precedence at runtime.

After changes, validate the skill frontmatter and relative links, then walk through the scenarios in the monitoring protocol. Real CLI checks should use a dedicated test session and cover dispatch, decisions, recovery, and monitor cleanup. Static validation does not establish that background scheduling or live CLI integration works.
