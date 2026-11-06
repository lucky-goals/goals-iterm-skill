# goals-iterm-skill

Skill version: [v0.4.0-dev](https://github.com/lucky-goals/goals-iterm-skill/releases/tag/v0.4.0-dev) (prerelease)

[Website](https://lucky-goals.github.io/goals-iterm-skill/)
[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

When this skill is activated to delegate, take over, or continue a task, the coordinating agent acts as the root orchestrator. It uses the bundled standalone runner to direct Claude Code, Codex, and other CLIs running in iTerm2, monitor progress, make routine decisions, and verify completion. Follow the [execution boundary](references/orchestrator.md): project writes, artifacts, tests, builds, dependency/configuration/service changes, and Git mutations go through the terminal CLI; the root agent and native subagents use read-only project access for context, acceptance, and review. Read-only Git inspection is allowed. Publishing still requires explicit authorization.

Inline monitoring in the current execution is the default. Before each wait, the coordinator posts a brief evidence-based update to the user, reports stage changes and blockers, and does not invent percentages or completion estimates. Background monitoring is used only when explicitly requested and a real host wakeup or scheduler handle is verified. See the [progress narration protocol](references/monitoring.md#progress-narration-before-inline-waits).

## Local runtime prerequisites

The bundled runner requires local macOS execution, iTerm2 with its Python API enabled and authorized, and Python 3.12 with the skill's minimal locked dependencies. A cloud-only host without a local execution channel cannot control this Mac. Install and authenticate the target CLI in iTerm2, and keep credentials out of prompts.

From the installed skill directory, prepare and inspect the runtime:

```sh
scripts/bootstrap.sh --check
scripts/bootstrap.sh --apply
scripts/itermctl capabilities --json
scripts/itermctl doctor --json --live-api-check
```

The runtime requires no MCP server, client tool discovery, or client MCP configuration. Its fixed policy is stored at `~/.local/state/goals-iterm-skill/policy.json`; absent policy is read-only. Writes require explicit policy configuration, such as `scripts/itermctl policy configure --allow-writes --session-id SESSION_ID`. Do not silently broaden an existing read-only or session allowlist. See [runtime.md](references/runtime.md) for the request contract, all 13 operations, recovery receipts, and policy rules.

## Install through a coding agent

Copy the prompt below to a coding agent with local filesystem access. Replace `[target client]` with the client where you want to install the skill. For an existing checkout, you can replace the repository URL with its absolute local path.

```text
Please install goals-iterm-skill for [target client].
Repository: https://github.com/lucky-goals/goals-iterm-skill

1. Check the target client's existing configuration and supported skill installation
   mechanism. Use its documented location and scope; do not guess configuration paths.
2. Fetch the repository or use the local checkout I specified. Inspect SKILL.md and
   its referenced files. The repository root is the skill package.
3. Install it as goals-iterm-skill, preserving SKILL.md, references/, agents/, scripts/, and runtime/.
   Do not copy only SKILL.md. If an installation already exists, compare it first,
   preserve local changes, and back it up before updating. Leave other skills intact.
4. Check local macOS execution and run `scripts/bootstrap.sh --check`. If the runtime
   is unprepared or mismatched, run `scripts/bootstrap.sh --apply` under this installation
   request, then repeat `--check`. Run `scripts/itermctl capabilities --json` and
   `scripts/itermctl doctor --json --live-api-check`. The live check only lists sessions;
   it does not read screen/history contents or send input. Report any required manual
   API setting or permission response without bypassing consent. Do not modify client
   MCP configuration.
5. Validate the skill metadata and relative references. Reload skills using the
   client's supported mechanism, or tell me exactly which manual reload is needed.
   Confirm that the target client discovers the skill when this can be checked.
6. During installation, do not read terminal contents, send input, create windows,
   or launch coding tasks. Do not configure a write policy without explicit authorization.
7. Report the installation path, skill discovery status, runtime readiness, policy state,
   and available monitoring capabilities. Delegated tasks default to inline monitoring; background
   monitoring requires an explicit request and real host capability. Installation does
   not start a monitor, and no checks after this run may be promised without a real handle.
```

## Update an existing installation

Give the following prompt to a coding agent when an older copy is already installed. “Latest” means the latest commit on the remote default branch unless you specify a tag or commit SHA. Updating a source checkout does not automatically update a copied installation.

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
   installation, synchronize the complete package, including SKILL.md, references/, agents/, scripts/, and runtime/.
   For a client-managed installation, use its supported updater. Do not replace only SKILL.md.
   Remove confirmed obsolete package-owned files after backup, retaining unknown files so that
   old package files do not silently remain mixed with the new revision.
5. Validate metadata, relative references, and the installed content against the target revision.
   Reload through the client's supported mechanism; give exact restart/new-session steps if needed.
   Verify discovery of the updated skill when possible. Copying files does not prove that the
   current conversation has reloaded them.
6. Run `scripts/bootstrap.sh --check`; if unprepared or mismatched, prepare the locked
   environment with `scripts/bootstrap.sh --apply` under this update request, then repeat
   `--check`. Check `scripts/itermctl capabilities --json` and `scripts/itermctl doctor --json`.
   Preserve existing write policy and task state; do not perform terminal mutations during the update.
7. Report installation and backup paths, old/new revisions, retained local changes, validation,
   pending reload steps, and rollback instructions. Use a commit SHA when no separate version
   number exists; state clearly if client loading could not be verified.
```

For a manual update, identify the installation type and back it up first. In a clean Git installation already tracking the intended branch, run `git fetch origin`, inspect the target, then use `git pull --ff-only`; resolve differences if it cannot fast-forward. For a copied installation, obtain the target commit in a temporary directory, compare and synchronize the complete skill package, check obsolete package-owned files, and reload the client. Update the real target of a symlink installation. To roll back, preserve changes made since the update, restore the backup, and reload; rolling back the skill does not roll back terminal tasks already performed. Keep mutable runtime environments and audit/recovery state outside the skill directory.

## Prerequisites and manual installation

The repository root is a skill package. Install the whole directory under the name `goals-iterm-skill` using the host client's supported skill mechanism. Keep `SKILL.md`, `references/`, `agents/`, `scripts/`, and `runtime/` together so the runner and relative references remain available; `scripts/` contains the launchers and the standard-library helper used by the local session registry. Follow the target client's documentation and existing configuration for the installation location and reload procedure.

Enable and authorize the iTerm2 Python API, prepare the target CLI and its authentication in the terminal, and use the bundled runtime for iTerm operations. Local Python 3.12 and the minimal locked runtime dependencies are required. The runner does not provide an agent scheduler or background service.

Monitoring defaults to polling inline during the current execution. Use real, interruptible host sleeps: 10–15 seconds after dispatch, then 30–60 seconds between checks, with no sleep segment longer than 60 seconds. A single multi-session loop observes every due or runnable session, then waits once for the nearest next check. Do not start a background monitor by default. Continue monitoring after the current run only when the user explicitly requests it and the host provides a verified scheduler/wakeup handle; otherwise report that it cannot continue after the run ends.

### Short instructions and decision files

For multiline, long, or conditional task instructions, decisions, and resumptions, the coordinator first writes a private decision file that the CLI can read, then sends a single-line instruction containing its absolute path and a unique dispatch ID. Verify the input before submitting separately, then monitor evidence of file reading and execution. Simple single-line replies can be sent directly; use the actual controls for menus. A `[Pasted text #N]` marker is not a reason to submit or resend blindly. Clear a draft only when it is confirmed to be unsubmitted, owned by this coordinator, and the editor's clearing behavior is known. Files stay outside the business repository by default, remain unchanged after dispatch, and are linked to the audit log. See the [file dispatch protocol](references/dispatch.md) for the template, path requirements, and recovery steps.

### Session lifecycle and durable coordination state

Follow the [session lifecycle guide](references/session-lifecycle.md) before starting or handing off CLI work. Before launching a new CLI process or session, inspect the operations and readiness reported by the bundled runtime. After the CLI starts, and before dispatching new work, verify conversation persistence and the current Session/Tab/Window identity. If transcript or history is disabled, fix it through a verified launch method supported by that CLI before sending new work; do not restart an already active session merely to change the setting. A CLI identity or recovery receipt alone is not proof that history is persisted or resumable. When recovery is unknown, record the limitation and independently check normal-exit eligibility; do not equate missing recovery evidence with a mandatory manual cleanup.

The coordinator keeps a durable local registry at `~/.local/state/goals-iterm-skill/session-registry.json`. Use the bundled standard-library helper `scripts/session_registry.py` for lock, revision, and generation guards. Registry entries are host observations, not authorization or a lock on the real terminal; the runner enforces its fixed local policy and fresh-operation checks. The optional `monitor_mode` is `inline`, `background`, `none`, or `unknown` (legacy entries without it mean `unknown`). `schedule_status` is `scheduled` only when a real host handle exists; inline monitoring is normally unscheduled and records the coordinator's assertion, not guaranteed liveness. Cross-task handoff/reuse and session identity/topology changes invalidate stale completion state; a same-task handoff that changes only the coordinator preserves recorded business and cleanup facts, including unknown outcomes, while generation guards still prevent stale writes. Renaming a CLI chat does not create a new identity. Once a per-session task is accepted, put it in `finalizing`: stop the business-writing monitor, but continue authorized cleanup coordination inline with bounded read/sleep/rechecks until each owned resource is actually `closed`, explicitly `retained`, or `blocked` with an actionable disposition. Keep any `unknown` cleanup result visible and reconcile it read-only before changing it. Checks after the current run require an explicitly requested background monitor and a real host handle. Child tasks may be accepted or reclaimed independently once no consumer needs them.

Cleanup rechecks are bounded and may run inline during finalization when authorized, even after the business monitor stops. Checks after the current run require an explicitly requested background monitor and a real host scheduler/wakeup handle. If a write result is unknown, reconcile it by read-only observation only. Do not default to `force` or a global sweep. Final responses must include resource-accounting totals and reasons, recovery evidence, and pending follow-ups.

## Explicit session cleanup

The bundled runner provides `close_session`, `close_tab`, `close_window`, and `clean_all_sessions`. Read `capabilities --json` for the installed argument schemas. Bind exact IDs with `list_sessions`; a fresh `list_sessions.data.observation` is required for mutations on existing resources. Container closes must verify every current member and refuse the full target when a member is out of scope or busy/unknown. A dry run is read-only and does not save a close receipt.

`clean_all_sessions` is a global cleanup within the configured policy scope. Use it only when the user authorized that entire scope, the fixed policy permits it, and the request includes top-level `authorization_scope: "all_sessions"`. An allowlist restricts access; it does not grant ownership or user authorization. `force=true` does not bypass policy, identity, ownership, receipt, or unknown-outcome protections. The operation applies idle filtering by default, records per-session partial outcomes, and does not include sessions that arrive after its initial snapshot.

Before interruption, CLI exit, or native close, the runtime persists a private recovery receipt. Initial receipt-write failure stops terminal writes; a later update failure may follow side effects, so inspect per-session results. Bounded SIGINT/SIGTERM may request CLI exit, and the target closes only after exit is verified. The result envelope carries `schema_version`, `request_id`, `status`, `code`, `data`, `warnings`, and `side_effects`; read every field and every per-session outcome. When a receipt exists, use its exact `recovery_record_id` and `recovery_record_path`. Empty/unknown CLI-history `persistence_status` does not itself block cleanup or prove recovery.

For uncertain mutation results, query `operation-status --request-id ID` and reconcile with fresh read-only observations. Never replay a mutation. See [runtime.md](references/runtime.md) and [closing and recovery](references/closing-and-recovery.md) for the complete contract.

### Automatic cleanup for task-owned resources

New task-owned sessions use `auto_owned`, including launch-only tests; a request to start a session does not itself request retention. Record the source of explicit retention requests. After a verified CLI exit (`/quit`, `/exit`, or a supported exit key), a verified idle shell may receive `exit` through the runner under the existing cleanup authorization, without another approval. Shell `exit` has no slash. Verify that the original Session/Tab disappears; if it remains, use the guarded runtime close path. Activity diagnostics may be incomplete, but counts alone do not prove a shell is idle; unknown jobs, scope restrictions, and uncertain writes still block automatic exit.

After acceptance criteria are verified and the business monitor has stopped, reclaim task-owned resources by first following the [normal CLI exit protocol](references/natural-exit.md): preserve known recovery information, submit the verified exit command once, and verify exit before closing any remaining shell. Missing chat UUID evidence alone does not prevent this path; an explicit requirement to preserve a resumable conversation still takes precedence. A CLI claim that it is done is not acceptance evidence. Retain borrowed or user-kept resources unless existing authorization permits cleanup.

Record the origin, owning task, and accurate Session, Tab, and Window IDs when a resource is created or explicitly adopted. Select the largest safe non-overlapping owned container: use an owned exclusive Window only when every current descendant belongs to this task and is completed and eligible; otherwise use an owned exclusive Tab; otherwise use individual owned eligible Sessions. Empty or exclusive-looking state alone does not prove ownership. Retain borrowed parents without cleanup authorization, and shared or unknown panes. If an allowlist is incomplete and container ownership cannot be proven, use exact Sessions.

After normal exit, refresh topology, preview remaining exact targets with `dry_run=true`, obtain a fresh expected observation, and close with `force=false`; never use global `clean_all_sessions` for task cleanup. Actual active work, uncertain ownership/process binding, identity conflicts, policy restrictions, initial receipt failures, and unknown write outcomes remain blockers. Activity-diagnostic limitations require the separate evidence checks in the normal exit protocol, not a forced close. Never resend an exit command after an unknown response. Verify CLI exit, terminal disappearance, and recovery capability separately; a later shell-close receipt does not prove that the former chat can be resumed.

Keep business completion separate from the cleanup outcome. Write each session's CLI/chat UUID, cwd, resume metadata, recovery receipt, request ID, and cleanup result to the audit record. Paused, failed, and canceled tasks are not auto-cleaned. The existing monitoring and audit workflow remains in force, and the bundled runtime contract is authoritative for arguments and results. Explicit authorization is still required for borrowed resources, global cleanup, and force cleanup; reuse existing authorization instead of asking again. Because `clean_all_sessions` can affect unrelated tasks, call it only when the user authorized the full configured policy scope and the request carries `authorization_scope: "all_sessions"`. See the [automatic cleanup and recovery guide](references/automatic-cleanup.md) and [closing and recovery guide](references/closing-and-recovery.md) for the detailed workflow.

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
a Coding CLI in iTerm through the bundled runner until the following task passes acceptance checks.

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
  CLI through the bundled runner. Read-only Git inspection is allowed. Use root/native agents for
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

See the [audit protocol](references/audit.md) and [Markdown template](references/audit-template.md), in English. A planned action is recorded before sending, and its actual delivery result is appended afterward. If recording fails, the agent reports the gap and pauses new automatic work instructions rather than silently continuing without an audit trail.

## Maintenance and validation

The entry point is [SKILL.md](SKILL.md). See [runtime.md](references/runtime.md) for the runner and policy contract, [orchestrator.md](references/orchestrator.md) for the execution boundary, [monitoring.md](references/monitoring.md) for monitoring and behavioral scenarios, and [closing-and-recovery.md](references/closing-and-recovery.md) for cleanup recovery details. These instruction files are in English. The upstream provenance and license are documented in [runtime/UPSTREAM.md](runtime/UPSTREAM.md).

After changes, validate the skill frontmatter and relative links, then walk through the scenarios in the monitoring protocol. Real CLI checks should use a dedicated test session and cover dispatch, decisions, recovery, and monitor cleanup. Static validation does not establish that background scheduling or live CLI integration works.

## Contributing and support

Bug reports, workflow improvements, and translations are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request, or open an [issue](https://github.com/lucky-goals/goals-iterm-skill/issues) for reproducible problems and suggestions. For vulnerabilities, follow [SECURITY.md](SECURITY.md) and use private reporting rather than posting terminal logs publicly. These contributor documents are currently in English.

## License

[MIT License](LICENSE). Copyright (c) 2026 lucky-goals.
