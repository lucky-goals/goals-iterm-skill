# Close, clean up, and restore CLI sessions

Use this guide when the user requests Session/Tab/Window closure, idle-session cleanup, or restoration of a closed conversation, or when [automatic cleanup](automatic-cleanup.md) establishes eligibility. See [iterm-tools.md](iterm-tools.md) for the tool contract. Business completion must be combined with ownership and retention policy; it does not authorize arbitrary terminal closure. Reuse existing authorization and ask only when scope or a specific choice is unresolved.

## Choose the narrowest tool and establish scope

| User intent | Tool |
| --- | --- |
| “Close the session named api-worker” | `close_session(nickname="api-worker")`; affects that Session only |
| “Close the tab containing this session” | `close_tab(session_id=bound_id)`; enumerate all panes in the Tab first |
| “Close this window” | `close_window(window_id=verified_id)`; enumerate all Tabs/Sessions first |
| “Clean up idle sessions” | `clean_all_sessions()` only when its entire accessible scope is authorized; selection uses idle state |
| “Force-close all sessions, including running tasks” | `clean_all_sessions(force=true)` attempts all targets within user authorization and server permissions |

Pass exactly one selector. Nicknames belong to Sessions; each pane may be named separately. Matching uses the complete trimmed, case-folded name; resolve duplicates. Prefer exact IDs for bound tasks. If an original ID disappears, do not substitute a new same-nickname session. Selecting a Tab/Window through a Session affects the whole container, not just that pane.

The service selects idle by activity. It does not decide whether a session is useful, task-owned, or idle for long enough. To retain some idle sessions, close other authorized targets individually by exact ID. `clean_all_sessions` has no arbitrary target-list parameter. A server allowlist restricts access but does not grant user authorization. If only this task is authorized and server scope is broader, close exact task Sessions individually; do not call global cleanup and expect it to infer ownership. Force “all” is likewise not task-scoped. The service protects its MCP host process and ancestors. Retain and report `SELF_PROTECTION`; never bypass it with force or another channel.

## Choose the exit path first

For accepted work or explicitly authorized closure of a stopped CLI, prefer [normal exit](natural-exit.md): preserve known recovery details, submit a verified exit command, then verify and normally exit the remaining idle shell. The sole finalizer performs this through MCP input tools, without requiring a new chat recovery receipt. This does not change the checks enforced by closing tools below. Do not resend a command to an already exited CLI. Existing terminal-cleanup authorization covers eligible shell `exit` without another confirmation; CLI-exit-only or terminal-retention requests do not expand into cleanup permission.

Use the MCP path below when interrupting running work, when normal exit is ineligible but MCP permits safe closure, or when the user explicitly requests force. Force authorization alone does not waive service permissions, identity checks, receipts, or unknown-outcome protections.

`force=true` does not guarantee immediate closure of an empty Tab. The service may first interrupt and verify process exit; an interactive shell may survive interruption. Do not default to force to address a false activity diagnosis on an idle shell. Check normal-exit eligibility first. After `INTERRUPT_UNVERIFIED`, reconcile current state and possible side effects read-only before further shell input; see the normal-exit protocol for conditions.

## MCP closing path

1. **Discover and locate:** inspect the actual schema, bind original Session/Tab/Window IDs with list_sessions, and verify user intent and other container panes. For an explicit, unambiguous single-session request, dry_run may be omitted, but still perform monitor handoff, confirm receipt semantics, and record intent before closing. For batches, containers, or unclear scope, prefer dry_run=true to inspect targets, skips, and recovery readiness. A dry run only reads: no input, receipt writes, or closure. Check would_close_sessions/would_skip_sessions, blocking_sessions, and code, not just status=dry_run or isError=false. A preflight is neither a lock nor a guarantee of later success.
2. **Prevent stale monitoring:** before the first close action, persist closing for this task's actual targets through a version-checked registry update and new revision. Stop their writing monitors and verify the result. Do not send “continue” or recreate terminals during closure. Keep monitors for preflight-skipped sessions that still need work; do not stop unrelated task monitors. See the [monitoring protocol](monitoring.md).
3. **Confirm save-before-exit semantics:** this MCP path collects CLI identity and persists a receipt internally before the service interrupts, exits, and closes. The host does not need to manually fetch UUIDs or create a substitute receipt. Distinguish recovery receipts from history as described below. Under the [audit protocol](audit.md), record intent, authorization scope, original target, force, and dry-run results. Append actual receipt references after the call; never claim pre-call persistence. Reuse the task ledger or create a cleanup ledger for cleanup-only requests without fabricating CLI rounds.
4. **Call and verify:** let the closing tool perform bounded exit and terminal closure. Do not interleave exit commands/control keys while it runs or its outcome is unknown. Send verified normal-exit commands only under the separate normal-exit protocol; Ctrl-C/Ctrl-D are not universal exit commands. The current CLI adapter uses stable process identity for bounded SIGINT/SIGTERM and verifies exit, retaining the terminal when unconfirmed. This does not guarantee saved CLI history. Do not interrupt busy/unknown sessions by default. Explicit force authorization permits an interruption attempt, not a guarantee that every subagent/background process ends, arbitrary killing, or repeated blind Ctrl-C. Read the complete result, including structured errors and per-session outcomes, then enumerate to verify disappearance. API acknowledgment alone is not closure.
5. **Report actual outcomes:** distinguish closed, skipped, refused, failed, and unknown per Session with reasons and receipt links. Report acceptance, task interruption, CLI exit, terminal closure, and recoverability separately. Do not mark a partially successful batch as all successful. Reconcile unknowns read-only, without automatic forced-close retries. Do not add new sessions to the original batch without reassessing scope.

Default direct close_session/tab/window calls should refuse the whole target before mutation when any member is busy/unknown; they must not silently close a subset. Default clean_all_sessions instead selects eligible targets and skips unsafe ones. User input or runtime failure after preflight may still produce partial results; report them accurately. A prompt, zero message count, no new output, or one screen read does not establish idleness.

Retain original IDs and actual states for refused/skipped sessions. Resume their monitors only after fresh observation and only if the original work still needs to continue and the user has not asked to stop. Pause writes for unknown outcomes and investigate. Old callbacks must not undo the user's closure intent.

## Recovery receipts and CLI history

MCP closing persists its receipt before exit; verify returned fields. Normal exit instead records known recovery details and gaps in the ledger before exiting; that is not an MCP receipt. The four public closing entry points remain close_session, close_tab, close_window, and clean_all_sessions. MCP 0.2.1 also offers optional read-only inspect_sessions; check the installed schema first. It only reads diagnostics: no CLI registration, receipt saving, restoration, authorization, or closure. `close_readiness=eligible_if_unchanged` does not prove ownership or permission. There are no public register-chat, save-receipt, or restore-conversation tools. Internal adapter methods are not callable MCP tools, and a manually read UUID is not a close parameter. Diagnostics/dry runs may inspect readiness, but neither creates a receipt or permission. For each target, check at least:

- Original iTerm Session/Tab/Window IDs, nickname, and CLI type.
- **CLI chat UUID** and its evidence source. This is a CLI conversation identifier, not an iTerm Session ID, PID, or coordination task ID.
- Conversation cwd, usable resume command/arguments, and necessary session-file or record references. Mark unverified fields unknown.
- Whether an MCP receipt was persisted, its ID/absolute path, and whether running work was interrupted. Current receipts lack a capture-time field; record actual host observation time without calling it service capture time.

Current adapters recognize Claude Code, Codex, Cursor Agent, and Kiro. Prefer conversation records opened by the process for current identity; Cursor may also use logs opened by that process. A resume UUID in launch arguments proves only the starting conversation, not that it never changed. Even a known UUID cannot authorize interruption when CLI_IDENTITY_STARTUP_ONLY is returned. Use records currently opened by the process or current Cursor logs; retain on conflicts. Missing reliable mapping may produce CLI_IDENTITY_MISSING. “Latest conversation,” matching cwd, or a session list cannot replace process binding. A skill-recorded UUID is not automatically registered with MCP. Keep the blocker for MCP interruption/closing; assess normal exit independently for missing/startup-only chat identity rather than immediately asking the user to exit manually. Do not send `/status`, `/session-id`, or work to probe identity in a busy or unclear CLI.

Even with an input box, a CLI may be busy/unknown in the backend because its shell command remains active. This constrains default MCP closing but does not automatically rule out normal exit. Gather work-completion and interaction evidence under that protocol; do not override state from one screen read or pretend preflight passed. Use existing explicit force permission when actual running work needs interruption.

Distinguish three evidence levels: **current UUID identified → conversation persisted → restoration actually verified**. A UUID or empty new-conversation record does not establish recoverability or tested restoration. MCP closing skips/refuses a recognized CLI with missing UUID, conflicting identity sources, unknown stable process identity, or failed receipt persistence. Force does not waive these protections. Missing UUID normal-exit eligibility is separate; conflicting sources or unknown processes are not merely degraded recovery. CLI persistence_status may be saved/empty/unknown/null and describes conversation history, not receipt persistence. Current implementation does not block solely for empty/unknown history. Act within authorization on actual closing results, report unverified history recovery, and do not invent RECOVERY_PERSISTENCE_FAILED. An ordinary shell/job may return empty cli_sessions, meaning no chat records were returned this time, not that the terminal never hosted a CLI. Preserve historical conversation references in the task ledger. Treat misidentification or missing evidence as blockers; an empty array is not proof of safe recovery.

Receipts hold recovery data; ledgers hold actions, evidence, and outcomes. Reference exact recovery_record_id and recovery_record_path fields. The default directory is `~/.local/state/goals-iterm-mcp/recovery`, overridable with GOALS_ITERM_MCP_RECOVERY_DIR; use the actual returned path. Do not replace a failed initial receipt with a host-created file and retry closure. Receipt sessions[] is a pre-operation snapshot and may still show interruption/exit/closure_status as not_attempted/pending; it is not the final result. Reconcile returned result arrays, receipt steps, and current topology. A receipt's existence does not prove later log entries are complete. Update failure may follow interruption/closure; inspect unknown/partial and per-item results instead of claiming no side effects. With a lost response, read the known receipt and topology. If the exact record mapping is unknown, retain uncertainty rather than choosing the newest file. Never put credentials in records or user reports.

## Restore a closed conversation

1. Locate the correct CLI conversation from the original target and recovery record. Check UUID, cwd, persistence evidence, and unfinished actions. If only a UUID exists without conversation storage, report unverified recovery rather than promising resumption.
2. Restore into an available dedicated session as requested. Verify shell state and cwd first. Construct the command from resume.executable and each resume.argv element with correct quoting, using cwd. For missing arguments or unclear versions, read local help in a ready dedicated shell. Do not directly concatenate arguments containing spaces/special characters or send natural-language continuation instructions to a shell.
3. Verify the loaded conversation's identity and contents, recording the new iTerm Session ID's relationship to the original CLI chat UUID. Do not dispatch work if identity cannot be confirmed or silently fall back to a new conversation that repeats the work.
4. If continuing the original task, check prior external side effects and artifacts first, then resume unfinished work. Update generation, single-writer ownership, ledger, and monitor. For interface-only restoration, stop once ready without adding work.

## Focused validation scenarios

| Scenario | Expected action |
| --- | --- |
| Two differently named panes; user wants only one closed | Exact close_session, retaining the other pane in the Tab |
| Two Session nicknames differ only by case | Reject ambiguous nickname selection and bind an exact ID |
| One idle and one busy pane; ordinary whole-Tab close | Refuse the whole target; do not close the idle pane first |
| Global cleanup includes idle, busy, and unknown sessions | Check retention needs first, then follow MCP idle selection and report per-item blockers |
| Only this task's cleanup authorized, server spans several projects | Close original task IDs individually; no global clean_all_sessions |
| Force authorized but chat UUID missing or MCP receipt write fails | Report the blocker; do not bypass protections |
| Force authorized, reliable UUID and writable receipt, history unknown/empty | Use actual close results and report unverified recovery, not fabricated receipt failure |
| dry_run status but would_skip_sessions has blockers | Explain each result; do not assume persisted receipts or universal eligibility |
| User starts work or adds a pane after preflight | Recheck targets/state; preflight is not a lock or scope expansion |
| Close timeout followed by an old monitor callback | Keep closing/unknown, do not redispatch, and inspect the actual target read-only |
| Startup-only UUID with skip_code=CLI_IDENTITY_STARTUP_ONLY | MCP interruption/closure remains blocked; independently eligible normal exit may proceed with recovery unverified |
| Current UUID visible but conversation not persisted | Record identified identity and unverified recovery; do not promise restoration |
| Resume command opens a new conversation | Do not dispatch; report identity mismatch and inspect the recovery record |
