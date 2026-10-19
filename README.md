# goals-iterm-skill

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

Let a coding agent use [goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp) to direct Claude Code, Codex, and other CLIs running in iTerm2, monitor their progress, advise on decisions, and verify completion.

## Required MCP: goals-iterm-mcp

This skill uses **[lucky-goals/goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp)** to operate iTerm2. Install and connect that MCP server in the **coordinating agent's client**, then install this skill and use the task prompts below. Installing the skill alone does not expose terminal tools. If the MCP is already connected, verify the connection instead of installing a duplicate.

Setup order:

1. On the Mac running the terminals, install and open iTerm2. Enable **Settings → General → Magic → Python API**, and approve its API authorization dialog when prompted.
2. Configure goals-iterm-mcp as a local stdio server in the coordinating client. The client must be able to access that Mac; a cloud-only chat cannot directly control its local iTerm2.
3. Install and authenticate the target Claude Code, Codex, or other CLI in iTerm2. Confirm it starts normally, including in new tabs. Keep credentials out of prompts.
4. Verify MCP tool discovery and a read-only `list_sessions` call, then install this skill. Task execution needs write tools; a `--read-only` server can only observe.

See the [MCP installation guide](https://github.com/lucky-goals/goals-iterm-mcp/blob/main/README.md) for the full instructions and version updates. The following example pins the documented version `0.1.2`; it does not assert that future versions are incompatible.

```text
Please install goals-iterm-mcp for [target client] on this Mac.
Repository: https://github.com/lucky-goals/goals-iterm-mcp

1. Read the project's installation guide. Check macOS, iTerm2, and uv/uvx.
   If uv is missing, install it using its official instructions.
2. Verify the package using Python 3.12:
   uvx --python 3.12 goals-iterm-mcp@0.1.2 --help
3. Back up the client's existing MCP configuration. Add or update one local stdio
   server named iterm, preserving all unrelated settings and avoiding duplicates:
   command: the absolute path to uvx
   args: ["--python", "3.12", "goals-iterm-mcp@0.1.2", "serve"]
   Use the target client's supported configuration format and location.
4. Guide me through enabling the iTerm2 Python API and approving its dialog if needed.
   Reload MCP using the supported mechanism; explain any required manual restart.
5. Verify the handshake, tool discovery, and list_sessions only. Do not read terminal
   contents, send input, create/close windows, or start coding tasks during setup.
6. Report the configuration location, pinned version, and connection results.
   Distinguish standalone server connectivity from tools loaded in the target client.
   Explain any remaining blocker, then continue with the skill installation below.
```

`serve` is the MCP server entry point, launched by the client over stdio; it is not a coding CLI. MCP installation does not provide a monitor or configure the target CLI's authentication.

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

## Advanced example: pursue a task to completion with a Goal

For a multi-step task, use a Goal in the coordinating Codex chat when the host supports it. The CLI running inside iTerm does not need a separate Goal. A Goal tracks the overall objective; the skill guides coordination, and the monitor observes terminal output. A Goal does not replace a monitor or provide an independent background service. See the [official Goals guide](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex).

Replace the placeholders below and send this prompt to the coordinating Codex agent. For a host without Goals, omit the Goal creation and completion instructions while keeping the monitoring and acceptance requirements.

```text
Create and start a Codex Goal. Use $goals-iterm-skill to continuously direct
a Coding CLI through iTerm MCP until the following task passes acceptance checks.

Project directory: [absolute path]
Execution CLI: [Claude Code / Codex CLI]
Target session: [existing nickname or ID; otherwise create a dedicated session]

Objective:
[Describe the desired final outcome]

Acceptance criteria:
1. [Observable feature or behavior]
2. [Relevant tests that must pass]
3. [Required files, results, or explanation]

Execution requirements:
- Maintain a Markdown audit ledger throughout execution. Record each instruction,
  CLI response and pending decision, your decision and its basis, actions and results,
  with timestamps, outer/CLI rounds, and linked event IDs. Announce its path at the
  start and include the ledger link in the final report.
- Coordinate, monitor, make decisions, and verify results; have the target CLI
  perform the development work.
- Check the session first. If the task is already running, take over monitoring
  without dispatching it again.
- After every task, follow-up, decision, or recovery instruction, create or update
  the same monitor.
- Use a monitoring mechanism actually available in the host. Without background
  wakeups, keep polling during the active run and report the limitation honestly;
  do not merely promise to check later.
- Make routine technical decisions using the context and project conventions,
  and advise the CLI so it can continue.
- Observe while the CLI is working or retrying automatically; do not resend work.
- Recover only after confirming the task has stopped and will not resume itself.
  Check what has already completed and use bounded recovery attempts.
- Do not treat a progress report, idle prompt, or completion claim as proof that
  the entire task is complete.
- Request missing acceptance evidence. Once all criteria are met, stop the monitor,
  mark the Goal complete, and summarize changes, verification, and remaining issues.

Constraints:
- Follow the project's AGENTS.md.
- Run relevant targeted tests; avoid full test suites unless necessary.
- Do not start Python processes with --reload.
- Publishing, pushing, and destructive operations are not authorized for this task.
- When my decision is necessary, give the specific question, your recommendation,
  and the action needed. Preserve context and stop the related automatic writes.
```

## Task audit ledger

Every delegated task now maintains a Markdown audit ledger as it runs. The coordinator records instructions, CLI feedback (including questions and options), decisions and their basis, delivery evidence, recovery, acceptance results, and monitor cleanup. Entries include timestamps with UTC offsets, outer conversation rounds, per-session CLI rounds, and linked event/decision IDs. The outer round is a task-local user-message counter, not an invented native chat ID.

The coordinator announces the absolute ledger path at the start and links it in the final report. Specify a path if desired; otherwise it uses a private host state directory, falling back to `~/.local/state/goals-iterm-skill/audits/`. Ledgers are not automatically committed to your repository. Secrets are redacted; unchanged polls may be consolidated, but decisions and significant feedback remain recorded. This is an append-oriented operational record, not a tamper-proof log or a full terminal recording.

See the [audit protocol](references/audit.md) and [Markdown template](references/audit-template.md), currently in Simplified Chinese. A planned action is recorded before sending, and its actual delivery result is appended afterward. If recording fails, the agent reports the gap and pauses new automatic work instructions rather than silently continuing without an audit trail.

## Maintenance and validation

The entry point is [SKILL.md](SKILL.md). See [iterm-tools.md](references/iterm-tools.md) for tool semantics and [monitoring.md](references/monitoring.md) for monitoring, recovery, and behavioral validation scenarios. These instruction files are currently in Simplified Chinese. Tool conventions are based on `src/goals_iterm_mcp/direct.py` in cc-iterm-mcp; the installed tool schema takes precedence at runtime.

After changes, validate the skill frontmatter and relative links, then walk through the scenarios in the monitoring protocol. Real CLI checks should use a dedicated test session and cover dispatch, decisions, recovery, and monitor cleanup. Static validation does not establish that background scheduling or live CLI integration works.

## Contributing and support

Bug reports, workflow improvements, and translations are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request, or open an [issue](https://github.com/lucky-goals/goals-iterm-skill/issues) for reproducible problems and suggestions. For vulnerabilities, follow [SECURITY.md](SECURITY.md) and use private reporting rather than posting terminal logs publicly. These contributor documents are currently in English.

## License

[MIT License](LICENSE). Copyright (c) 2026 lucky-goals.
