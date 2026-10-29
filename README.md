# goals-iterm-skill

Skill version: [v0.3.0](https://github.com/lucky-goals/goals-iterm-skill/releases/tag/v0.3.0)

[Website](https://lucky-goals.github.io/goals-iterm-skill/)
[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

When this skill is activated to delegate, take over, or continue a task, the coordinating agent acts as the root orchestrator. It uses [goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp) to direct Claude Code, Codex, and other CLIs running in iTerm2, monitor progress, make routine decisions, and verify completion. Follow the [execution boundary](references/orchestrator.md): project writes, artifacts, tests, builds, dependency/configuration/service changes, and Git mutations go through the terminal CLI; the root agent and native subagents use read-only project access for context, acceptance, and review. Read-only Git inspection is allowed. Publishing still requires explicit authorization.

Inline monitoring in the current execution is the default. Before each wait, the coordinator posts a brief evidence-based update to the user, reports stage changes and blockers, and does not invent percentages or completion estimates. Background monitoring is used only when explicitly requested and a real host wakeup or scheduler handle is verified. See the [progress narration protocol](references/monitoring.md#内联等待的进度旁白).

## Required MCP: goals-iterm-mcp

This skill uses **[lucky-goals/goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp)** to operate iTerm2. Install and connect that MCP server in the **coordinating agent's client**, then install this skill and use the task prompts below. Installing the skill alone does not expose terminal tools. If the MCP is already connected, verify the connection instead of installing a duplicate.

Setup order:

1. On the Mac running the terminals, install and open iTerm2. Enable **Settings → General → Magic → Python API**, and approve its API authorization dialog when prompted.
2. Configure goals-iterm-mcp as a local stdio server in the coordinating client. The client must be able to access that Mac; a cloud-only chat cannot directly control its local iTerm2.
3. Install and authenticate the target Claude Code, Codex, or other CLI in iTerm2. Confirm it starts normally, including in new tabs. Keep credentials out of prompts.
4. Verify MCP tool discovery and a read-only `list_sessions` call, then install this skill. Task execution needs write tools; a `--read-only` server can only observe.

See the [MCP installation guide](https://github.com/lucky-goals/goals-iterm-mcp/blob/main/README.md) for the full instructions and version updates. The following example pins the documented version `0.2.2`; it does not assert that future versions are incompatible.

```text
Please install goals-iterm-mcp for [target client] on this Mac.
Repository: https://github.com/lucky-goals/goals-iterm-mcp

1. Read the project's installation guide. Check macOS, iTerm2, and uv/uvx.
   If uv is missing, install it using its official instructions.
2. Verify the package using Python 3.12:
   uvx --python 3.12 goals-iterm-mcp@0.2.2 --help
3. Back up the client's existing MCP configuration. Add or update one local stdio
   server named iterm, preserving all unrelated settings and avoiding duplicates:
   command: the absolute path to uvx
   args: ["--python", "3.12", "goals-iterm-mcp@0.2.2", "serve"]
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
3. Install it as goals-iterm-skill, preserving SKILL.md, references/, agents/, and scripts/.
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
   monitoring capabilities. Delegated tasks default to inline monitoring; background
   monitoring requires an explicit request and real host capability. Installation does
   not start a monitor, and no checks after this run may be promised without a real handle.
```

## Update an existing installation

Give the following prompt to a coding agent when an older copy is already installed. “Latest” means the latest commit on the remote default branch unless you specify a tag or commit SHA. Updating a source checkout does not automatically update a copied installation; upgrading the `goals-iterm-mcp` PyPI package does not update the skill either.

```text
Please update the existing goals-iterm-skill installation in [target client] to the latest revision.
Repository: https://github.com/lucky-goals/goals-iterm-skill
(Optional: specify a tag or commit SHA here.)

1. Locate the skill path and scope actually loaded by the client. Determine whether it is
   a Git checkout, symlink, copied directory, or client-managed installation. Record its
   current revision or file state; mark the old revision unknown if it cannot be established.
   Check local changes and duplicate installations; do not guess paths or add a competing copy.
2. Back up the complete installation and local changes outside directories scanned for skills.
   For a symlink, back up the target contents. Record the backup path and preserve audit ledgers,
   runtime records, custom files, and other skills.
3. Fetch upstream and resolve the remote default branch's latest commit, or my specified tag/SHA.
   Record the target SHA; do not describe a stale checkout or uncommitted edits as upstream latest.
4. Fast-forward a clean Git installation only when it tracks the intended branch. For local edits,
   divergence, detached HEAD, or another branch, do not reset, force-switch, or discard changes.
   Prepare upstream in a temporary directory, compare and preserve/merge customizations, and
   report conflicts that cannot be reconciled. For a symlink, update its real target; for a copied
   installation, synchronize the complete package, including SKILL.md, references/, agents/, and scripts/.
   For a client-managed installation, use its supported updater. Do not replace only SKILL.md.
   Remove confirmed obsolete package-owned files after backup, retaining unknown files so that
   old package files do not silently remain mixed with the new revision.
5. Validate metadata, relative references, and the installed content against the target revision.
   Reload through the client's supported mechanism; give exact restart/new-session steps if needed.
   Verify discovery of the updated skill when possible. Copying files does not prove that the
   current conversation has reloaded them.
6. Check MCP tool discovery separately, using only list_sessions if a connection check is needed.
   If new tools are absent, explain the separate MCP upgrade/reload needed; do not change its pin
   or unrelated configuration. Do not read terminal contents, send input, create/close sessions,
   or launch tasks while updating the skill.
7. Report installation and backup paths, old/new revisions, retained local changes, validation,
   pending reload steps, and rollback instructions. Use a commit SHA when no separate version
   number exists; state clearly if client loading could not be verified.
```

For a manual update, identify the installation type and back it up first. In a clean Git installation already tracking the intended branch, run `git fetch origin`, inspect the target, then use `git pull --ff-only`; resolve differences if it cannot fast-forward. For a copied installation, obtain the target commit in a temporary directory, compare and synchronize the complete skill package, check obsolete package-owned files, and reload the client. Update the real target of a symlink installation. To roll back, preserve changes made since the update, restore the backup, and reload; rolling back the skill does not roll back MCP or terminal tasks already performed.

## Prerequisites and manual installation

The repository root is a skill package. Install the whole directory under the name `goals-iterm-skill` using the host client's supported skill mechanism. Keep `SKILL.md`, `references/`, `agents/`, and `scripts/` together so relative references remain valid; `scripts/` contains the bundled standard-library helper used by the local session registry. Follow the target client's documentation and existing configuration for the installation location and reload procedure.

This skill does not install MCP or provide a standalone background service. Connect goals-iterm-mcp in the host client, enable the iTerm2 Python API, and prepare the target CLI and its authentication in the terminal. Required tools cover session listing, screen/history reading, and text/key input; creating terminals also requires the corresponding creation tools.

Monitoring defaults to polling inline during the current execution. Use real, interruptible host sleeps: 10–15 seconds after dispatch, then 30–60 seconds between checks, with no sleep segment longer than 60 seconds. A single multi-session loop observes every due or runnable session, then waits once for the nearest next check. Do not start a background monitor by default. Continue monitoring after the current run only when the user explicitly requests it and the host provides a verified scheduler/wakeup handle; otherwise report that it cannot continue after the run ends.

### Short instructions and decision files

For multiline, long, or conditional task instructions, decisions, and resumptions, the coordinator first writes a private decision file that the CLI can read, then sends a single-line instruction containing its absolute path and a unique dispatch ID. Verify the input before submitting separately, then monitor evidence of file reading and execution. Simple single-line replies can be sent directly; use the actual controls for menus. A `[Pasted text #N]` marker is not a reason to submit or resend blindly. Clear a draft only when it is confirmed to be unsubmitted, owned by this coordinator, and the editor's clearing behavior is known. Files stay outside the business repository by default, remain unchanged after dispatch, and are linked to the audit log. See the [file dispatch protocol](references/dispatch.md) for the template, path requirements, and recovery steps.

### Session lifecycle and durable coordination state

Follow the [session lifecycle guide](references/session-lifecycle.md) before starting or handing off CLI work. Before launching a new CLI process or session, inspect the cleanup and recovery capabilities actually available in the installed MCP. After the CLI starts, and before dispatching new work, verify conversation persistence and the current Session/Tab/Window identity. If transcript or history is disabled, fix it through a verified launch method supported by that CLI before sending new work; do not restart an already active session merely to change the setting. A CLI identity or recovery receipt alone is not proof that history is persisted or resumable. When recovery is unknown, record an explicit, actionable manual follow-up and never promise automatic closure.

The coordinator keeps a durable local registry at `~/.local/state/goals-iterm-skill/session-registry.json`. Use the bundled standard-library helper `scripts/session_registry.py` for lock, revision, and generation guards. Registry entries are host observations, not MCP authority and not a lock on the real terminal. The optional `monitor_mode` is `inline`, `background`, `none`, or `unknown` (legacy entries without it mean `unknown`). `schedule_status` is `scheduled` only when a real host handle exists; inline monitoring is normally unscheduled and records the coordinator's assertion, not guaranteed liveness. Cross-task handoff/reuse and session identity/topology changes invalidate stale completion state; a same-task handoff that changes only the coordinator preserves recorded business and cleanup facts, including unknown outcomes, while generation guards still prevent stale writes. Renaming a CLI chat does not create a new identity. Once a per-session task is accepted, put it in `finalizing`: stop the business-writing monitor, but continue authorized cleanup coordination inline with bounded read/sleep/rechecks until each owned resource is actually `closed`, explicitly `retained`, or `blocked` with an actionable disposition. Keep any `unknown` cleanup result visible and reconcile it read-only before changing it. Checks after the current run require an explicitly requested background monitor and a real host handle. Child tasks may be accepted or reclaimed independently once no consumer needs them.

Cleanup rechecks are bounded and may run inline during finalization when authorized, even after the business monitor stops. Checks after the current run require an explicitly requested background monitor and a real host scheduler/wakeup handle. If a write result is unknown, reconcile it by read-only observation only. Do not default to `force` or a global sweep. Final responses must include resource-accounting totals and reasons, recovery evidence, and pending follow-ups.

## Explicit session cleanup

The current MCP source implements four cleanup tools. Use them only when the installed server exposes the corresponding schema; the installed tool schema remains the runtime authority. This section describes the current implementation and makes no package-release or version-change claim.

- `close_session(session_id OR nickname, force=false, dry_run=false)` closes one session.
- `close_tab(tab_id OR session_id OR nickname, force=false, dry_run=false)` closes one tab.
- `close_window(window_id OR session_id OR nickname, force=false, dry_run=false)` closes one window.
- `clean_all_sessions(force=false, dry_run=false)` cleans up sessions within the server-authorized scope.

For the first three tools, provide exactly one selector. IDs must match exactly. A nickname is trimmed and case-folded before an exact match against one Session; for tab/window tools it selects that Session's containing object, never a Tab directly. Ambiguous matches are refused. By default, `clean_all_sessions` closes only confirmed idle sessions and skips busy, waiting, unknown, or otherwise unsafe sessions. It does not infer that a session is “unneeded” or useful; the coordinating agent must honor the requested retention and authorized scope. With `force=true`, it attempts every session in the initial authorized scope, including busy sessions, while still enforcing identifier, permission, target-change, and recovery-safety checks. A direct close refuses the whole affected session/tab/window when preflight finds a busy or unknown session unless force is authorized.

Before any interruption, CLI exit, or native close, the service persists a private recovery receipt containing the target and available CLI/chat UUID, cwd, and resume metadata; an initial receipt-write failure stops the operation before terminal writes. Later receipt-update failures can follow side effects, so inspect the per-session results. It then requests a graceful CLI exit and closes the target only after exit is verified. `dry_run=true` is truly read-only: it sends no terminal input, saves no recovery receipt, renames nothing, and interrupts or closes nothing.

Each session result uses the public fields `interruption`, `exit`, `closure_status`, and `cli_sessions`; chat records may include `cli`, `chat_uuid`, `cwd`, identity source, persistence status, and resume data. When a receipt exists, the operation reports its `recovery_record_id` and `recovery_record_path`. An empty or unknown CLI-history `persistence_status` is not itself a blocker. UUID identity evidence and recovery-receipt safeguards are separate from actual history persistence and resumability, so an ID alone does not guarantee resume. Read the response `status` and the `closed_sessions`, `skipped_sessions`, `failed_sessions`, and `unknown_sessions` arrays even when MCP sets `isError=true`.

### Automatic cleanup for task-owned resources

After acceptance criteria are verified and monitoring has stopped, the default automatic cleanup reclaims resources created specifically for the task. The close tool persists its recovery receipt internally before exiting the CLI or closing the terminal. A CLI claim that it is “done” is not acceptance evidence. Existing borrowed sessions and windows remain by default unless they are explicitly adopted for this task with cleanup authorization. Honor a user keep-open override and retain the resource.

Record the origin, owning task, and accurate Session, Tab, and Window IDs when a resource is created or explicitly adopted. Select the largest safe non-overlapping owned container: use an owned exclusive Window only when every current descendant belongs to this task and is completed and eligible; otherwise use an owned exclusive Tab; otherwise use individual owned eligible Sessions. Empty or exclusive-looking state alone does not prove ownership. Retain borrowed parents without cleanup authorization, and shared or unknown panes. If an allowlist is incomplete and container ownership cannot be proven, use exact Sessions.

Automatic cleanup previews with `dry_run=true`, checks membership again, then calls `close_window`, `close_tab`, or `close_session` with `force=false`; it never calls global `clean_all_sessions`. If preflight reports a busy or unknown target, missing identity, or an initial recovery-receipt error, retain the resource and report it. Errors after execution starts may have side effects; verify the actual result without claiming the terminal was retained. Do not auto-force or blindly retry. Explicit user authorization for force cleanup remains a separate manual flow.

Keep business completion separate from the cleanup outcome. Write each session's CLI/chat UUID, cwd, resume metadata, recovery receipt, and cleanup result to the audit record. Paused, failed, and canceled tasks are not auto-cleaned. The existing monitoring and audit workflow remains in force, and the installed tool schema remains the runtime authority. Explicit authorization is still required for borrowed resources, global cleanup, and force cleanup; reuse existing authorization instead of asking again. Because `clean_all_sessions` can affect unrelated tasks, call it only when the authorized scope matches the server scope, including any configured allowlist. See the [automatic cleanup and recovery guide](references/automatic-cleanup.md) and [closing and recovery guide](references/closing-and-recovery.md) for the detailed workflow.

## Example

```text
Use goals-iterm-skill to have Claude Code in iTerm fix the login issue in
/path/to/project. Diagnose first, then fix it and run only relevant tests. Route
project changes through the CLI; keep root/native agents read-only for context and review.
Monitor inline in the current run by default, make routine technical decisions, and recover
from network failures only when the task has stopped and will not resume itself.
After acceptance checks pass, stop the business-writing monitor and complete the
authorized finalization until owned resources are closed, explicitly retained,
or blocked with an actionable disposition. Summarize changes, tests,
resource-accounting totals and reasons, recovery evidence, and pending follow-ups.
Do not publish.
```

You can also name an existing session to take over or continue its task. The skill resolves the exact `session_id` first and avoids resubmitting work already in progress.

## Advanced example: pursue a task to completion with a Goal

Create a Goal only when the user explicitly requests one and the host supports it. The CLI running inside iTerm does not need a separate Goal. A Goal tracks the overall objective; the skill guides coordination, and inline monitoring observes terminal output. A Goal does not replace monitoring or provide an independent background service. See the [official Goals guide](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex).

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
- Act as the root orchestrator. Route project writes, artifacts, tests, builds,
  dependency/configuration/service changes, and Git mutations through the target
  CLI over MCP. Read-only Git inspection is allowed. Use root/native agents for
  read-only context, acceptance, and review; publish only with my explicit
  authorization. For cleanup-only requests, follow the narrow lifecycle path without
  starting a coding CLI or monitoring loop. For restore-only requests, start/resume
  a CLI only as required by the lifecycle, without extra business work or a monitor loop.
- Check the session first. If the task is already running, take over monitoring
  without dispatching it again.
- Monitor inline in this run by default. Use real interruptible sleeps of 10–15s
  after dispatch, then 30–60s between checks (never over 60s per segment). One loop
  observes all due/runnable sessions, then waits once for the nearest check. Do not
  start a background monitor by default.
- Use a background monitor only if I explicitly request it and a real host
  scheduler/wakeup handle is verified. If background monitoring is unavailable,
  continue inline only when that still fits my request. If I ask you to return now,
  save a checkpoint and hand off as unscheduled; do not promise future checks.
  Context growth alone calls for checkpointing and normal continuation; an unavoidable
  hard host limit may require a truthful handoff.
- After acceptance, stop business monitoring but finish authorized cleanup inline
  with bounded read/sleep/rechecks. Future after-run checks require my explicit
  request and an actual scheduler handle; an inline unscheduled monitor is not a
  liveness guarantee.
- Make routine technical decisions using the context and project conventions,
  and advise the CLI so it can continue.
- Observe while the CLI is working or retrying automatically; do not resend work.
- Recover only after confirming the task has stopped and will not resume itself.
  Check what has already completed and use bounded recovery attempts.
- Do not treat a progress report, idle prompt, or completion claim as proof that
  the entire task is complete.
- Request missing acceptance evidence. Once all criteria are met, stop the business-writing
  monitor and complete only the authorized finalization: continue cleanup coordination and record
  each owned resource as closed, explicitly retained, blocked with an actionable disposition, or
  unknown. Reconcile an unknown result by read-only observation and do not hide it. Mark the Goal
  complete only when no required work remains. If required work or cleanup is genuinely blocked,
  report the host's current state and the action needed, following its status-transition rules;
  do not force an immediate blocked transition or promise to keep the Goal open indefinitely.
  Summarize changes, verification, resource-accounting totals and reasons, recovery evidence, and
  pending follow-ups. Child tasks may be accepted or reclaimed independently when no consumer needs them.

Constraints:
- Follow the project's AGENTS.md.
- Run relevant targeted tests; avoid full test suites unless necessary.
- Do not start Python processes with --reload.
- Publishing, pushing, and destructive operations are not authorized for this task.
- When my decision is necessary, give the specific question, your recommendation,
  and the action needed. Preserve context and stop the related automatic writes.
```

## Task audit ledger

Every task delegated, taken over, or continued with this skill maintains a Markdown audit ledger as it runs. The coordinator records instructions, CLI feedback (including questions and options), decisions and their basis, delivery evidence, recovery, acceptance results, and monitor cleanup. Entries include timestamps with UTC offsets, outer conversation rounds, per-session CLI rounds, and linked event/decision IDs. The outer round is a task-local user-message counter, not an invented native chat ID.

The coordinator announces the absolute ledger path at the start and links it in the final report. Specify a path if desired; otherwise it uses a private host state directory, falling back to `~/.local/state/goals-iterm-skill/audits/`. Ledgers are not automatically committed to your repository. Secrets are redacted; unchanged polls may be consolidated, but decisions and significant feedback remain recorded. This is an append-oriented operational record, not a tamper-proof log or a full terminal recording.

Ledgers are split by **processing date** in the task's recorded timezone: each task defaults to `audits/<task-id>/index.md` and `audits/<task-id>/YYYY-MM-DD.md`. The index links daily files; event and round numbers continue across dates. Late entries go into the current processing date with the original time noted. Existing single-file records remain intact and are linked when work resumes. Daily splitting does not delete history, so total storage still grows.

See the [audit protocol](references/audit.md) and [Markdown template](references/audit-template.md), currently in Simplified Chinese. A planned action is recorded before sending, and its actual delivery result is appended afterward. If recording fails, the agent reports the gap and pauses new automatic work instructions rather than silently continuing without an audit trail.

## Maintenance and validation

The entry point is [SKILL.md](SKILL.md). See [orchestrator.md](references/orchestrator.md) for the execution boundary, [iterm-tools.md](references/iterm-tools.md) for tool semantics, [monitoring.md](references/monitoring.md) for monitoring, recovery, and behavioral validation scenarios, and [closing-and-recovery.md](references/closing-and-recovery.md) for cleanup recovery details. These instruction files are currently in Simplified Chinese. Tool conventions are based on `src/goals_iterm_mcp/direct.py` in cc-iterm-mcp; the installed tool schema takes precedence at runtime.

After changes, validate the skill frontmatter and relative links, then walk through the scenarios in the monitoring protocol. Real CLI checks should use a dedicated test session and cover dispatch, decisions, recovery, and monitor cleanup. Static validation does not establish that background scheduling or live CLI integration works.

## Contributing and support

Bug reports, workflow improvements, and translations are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request, or open an [issue](https://github.com/lucky-goals/goals-iterm-skill/issues) for reproducible problems and suggestions. For vulnerabilities, follow [SECURITY.md](SECURITY.md) and use private reporting rather than posting terminal logs publicly. These contributor documents are currently in English.

## License

[MIT License](LICENSE). Copyright (c) 2026 lucky-goals.
