# MCP tool conventions

These conventions were checked against goals-iterm-mcp source files `direct.py`, `sdk_auth.py`, `process_inspection.py`, `closing.py`, `closing_backend.py`, and `cli_recovery.py` (14 MCP tools in current source; 13 tools in published MCP `0.2.2` before `activate_session` and creation `activate`). Source implementation does not prove the installed service is updated. Host tool names may use different namespaces; match the short names below. Inspect schema differences before calling an installed version with a different interface, and never substitute non-MCP scripts or AppleScript when an MCP tool is absent.

| Tool | Parameters | Purpose |
| --- | --- | --- |
| list_sessions | None | Returns `sessions[]` with session_id, name, window_id, tab_id, and internal target; does not read terminal content |
| inspect_sessions | session_id OR nickname, optional; omit both for all authorized visible sessions | Read-only cleanup capability diagnostics; use only if exposed by the installed service |
| read_screen | session_id | Returns screen (including lines/cursor), captured_at, and truncated |
| read_history | session_id, lines (default 100, range 1–2000) | Retained recent history with position/text/wrapped, source_bounds, and truncated |
| send_text | session_id, text | Sends 1–16384 UTF-8 bytes verbatim without adding a newline |
| send_keys | session_id, key | Sends one control key |
| activate_session | session_id | Selects the Session's Tab/pane and brings its iTerm2 Window to the foreground; discover schema first on older servers |
| create_window | name optional, command optional, activate=true | Creates a Window (foregrounded by default) with an explicit unique `name` (required by this skill; see [nickname library](nicknames.md)); returns session_id, tab_id, window_id, name, and activated |
| create_tab | window_id, name optional, command optional, activate=true | Creates a Tab in the exact Window (foregrounded by default) with an explicit unique `name` (required by this skill; see [nickname library](nicknames.md)), returning new IDs/name/activated |
| rename_session | session_id, name optional | Sets an explicit nickname (`name` required when establishing a skill-created session on older MCP servers); omitting name assigns a random one |

### Closing tools, when supported

Discover the actual schema first; the following is the public source interface. `OR` means exactly one selector, not a parameter name. `force` and `dry_run` accept JSON booleans `true/false`, not strings or 0/1. Omit unused selectors. Record missing closing/safety capabilities. A stopped CLI and a verified idle remaining shell authorized for cleanup may exit through MCP input tools under [normal exit](natural-exit.md). If eligibility cannot be verified, retain the target. Do not switch to AppleScript or another terminal channel or evade scope, permission, real-activity, or unknown-side-effect protections.

| Tool | Parameters | Scope and default behavior |
| --- | --- | --- |
| close_session | session_id OR nickname, force=false, dry_run=false | One Session; refuses busy/unknown |
| close_tab | tab_id OR session_id OR nickname, force=false, dry_run=false | All panes in a Tab; refuses the whole target if any is busy/unknown |
| close_window | window_id OR session_id OR nickname, force=false, dry_run=false | All Tabs/panes in a Window; refuses the whole target if any is busy/unknown |
| clean_all_sessions | force=false, dry_run=false | Selects safely idle sessions, skipping busy/unknown individually; force attempts all authorized targets |

Nicknames match the directory's `name` exactly after trimming whitespace and case-folding, and must identify a unique Session. No fuzzy matching or Tab-name selection. IDs must come verbatim from enumeration; do not pass `active/current/focused/all/*` or expect nickname fallback. Bind stable IDs for long workflows; do not retry by nickname. Force does not bypass target, permission, or recovery-information protections. The running service determines actual arguments, fields, and restrictions. Resolve differences affecting scope/safety before acting; missing capability is not satisfied capability. Read [closing and recovery](closing-and-recovery.md) before closing.

Supported keys: `enter`, `tab`, `escape`, `backspace`, `up`, `down`, `left`, `right`, `ctrl_c`, `ctrl_d`, `ctrl_u`, `ctrl_l`.

## Exact calls and result parsing

- The four closing tools and `inspect_sessions` accept `nickname`; reads, sends, foreground activation (`activate_session`), and renaming still require `session_id`. `rename_session`, `create_window`, and `create_tab` use parameter `name`, not `nickname`. **Although MCP marks `name` optional for generic callers, `goals-iterm-skill` must always specify an explicit unused nickname from the 200-word 4–6 character [nickname library](nicknames.md) (or a valid user-requested name) when creating any Session.** On older MCP servers (`0.2.2` and earlier) whose creation schema lacks `name`, immediately call `rename_session(session_id, name="<chosen-nickname>")` after creation and verify in `list_sessions` before registering or sending input. Explicit names are 1–64 characters after trimming, with no control characters, reserved selectors (`active/all/current/focused/*`), or case-insensitive duplicates.
- On servers supporting foreground activation, `create_window` and `create_tab` accept JSON boolean `activate` (default `true`, bringing the new Tab/Window to the foreground; pass `false` only when the user explicitly requests background creation) and return `activated` (`true/false`). For existing Sessions, call `activate_session(session_id)` when exposed by the installed schema.
- `command` is an optional startup command of 1–16384 UTF-8 bytes when provided; an empty string does not mean omitted. In iTerm2 (`use_custom_command`), `command` runs **in lieu of a login shell**: shell builtins/operators (`cd ... && ...`, `export`, `source`) and `~/.zshrc` `PATH` entries are unavailable and may fail immediately with `CREATE_FAILED`. Omit `command` when launching interactive Coding CLIs and start them inside the login shell via `send_text` + `send_keys("enter")`. Do not send internal target, PID, chat UUID, resume, session_ids, or suppress_broadcast fields to public tools.
- `list_sessions.sessions` includes only the service allowlist. Hidden sibling panes do not establish authorization for an entire Tab/Window. Container dry runs/closures may still return `OUT_OF_SCOPE`. Allowlist mode prohibits creating Windows/Tabs.
- Closing tools return MCP `CallToolResult`. Prefer `structuredContent`; if unavailable, parse the JSON text in `content`, and also inspect `isError`. Argument validation may produce a tool error without a closing result. Early failures such as connection errors may omit target/blocking_sessions; treat those fields as optional. Do not force ordinary read/write errors into the closing-result schema.

Closing fields and interpretation:

| Field | Meaning and handling |
| --- | --- |
| `status` | `closed/partial/refused/noop/dry_run/unknown`; partial may contain no successful closure, so inspect arrays |
| `closed_sessions` | Sessions whose terminal disappearance was verified; successful and skipped items yield partial, while only skipped items with no candidates usually yield noop; neither means all closed |
| `skipped_sessions`, `failed_sessions`, `unknown_sessions` | Report retained, failed, and unknown items individually; isError=true may coexist with successful items, so never retry the whole batch |
| `would_close_sessions`, `would_skip_sessions` | Dry-run candidates/exclusions; status=dry_run does not prove all checks passed. Inspect both arrays, blocking_sessions, and code |
| `target.session_ids` | Original scope selected by this call, not a lock or approval token for the next call |
| `recovery_record_id`, `recovery_record_path` | Actual receipt; may be null for dry runs, no candidates, or pre-exit refusal. Do not invent paths |
| Per-item `state/reason/probe_reason/skip_code` | Activity/blockers (`ACTIVITY_BLOCKED` vs `ACTIVITY_UNKNOWN` plus underlying `probe_reason` such as `prompt_unavailable`, or `exited`/`session_processes_exited` on ended panes); read actual values, not prompt appearance as idle evidence |
| Per-item `interruption/exit/closure_status` | Interruption, exit, and closure states (`interruption="not_attempted"` is preserved on pre-signal validation refusals); public results do not use internal task_interrupted / cli_exit_status fields |
| Per-item `cli_sessions[]` | cli/chat_uuid/cwd/identity_source/persistence_status/resume; resume is an executable plus argv array, not a shell string ready for concatenation |

If a target disappears automatically after exit, results may include `closure_method=auto_closed_after_exit` without a native close call. Verified disappearance is the criterion; success need not include native closing. The current public force value also passes through to iTerm's native `async_close(force=...)`; it is not a separately configurable parameter.

`isError` is true for refused/unknown or failed/unknown items. Skips alone are not errors. Inspect would_skip_sessions even when candidates are empty or isError=false. `dry_run=true` sends no input, writes no receipt, renames nothing, and closes nothing. Execution samples fresh state rather than reusing its plan.

Common errors: recheck exact targets for `INVALID_SELECTOR/AMBIGUOUS_SELECTOR/SELECTOR_NOT_FOUND`; do not auto-escalate force for `ACTIVITY_BLOCKED`; never bypass `OUT_OF_SCOPE/SELF_PROTECTION`. `CLI_IDENTITY_MISSING/CLI_IDENTITY_STARTUP_ONLY` block MCP closing, but missing chat evidence alone permits an independent normal-exit assessment. Retain and investigate `CLI_IDENTITY_AMBIGUOUS` and process-identity errors; normal exit cannot evade them. `RECOVERY_PERSISTENCE_FAILED` during initial receipt/first execution-log persistence blocks exit; a later log-update failure after exit/closure may already have side effects, requiring result-array and topology checks. Reconcile `TARGET_CHANGED`, exit/closure failures, `TIMEOUT/CANCELLED`, and similar results read-only per Session, without blind retries. Ordinary read/write `SESSION_NOT_FOUND` differs from closing `SELECTOR_NOT_FOUND`.

## Call examples with JSON arguments

Replace example IDs/nicknames with actual enumerated values. Each example includes a tool short name and arguments. Prefer an already bound exact ID; do not switch to a nickname just to reuse an example.

```json
{"tool":"close_session","arguments":{"nickname":"api-worker","dry_run":true}}
```

```json
{"tool":"close_tab","arguments":{"session_id":"session-1","dry_run":true}}
```

```json
{"tool":"close_window","arguments":{"window_id":"window-1","dry_run":true}}
```

```json
{"tool":"clean_all_sessions","arguments":{"dry_run":true}}
```

After a dry run, use the same tool with dry_run omitted/false only if authorization and scope still match. Pass force:true only for authorized interruption. A new call resamples; global cleanup does not freeze the earlier candidate list. For a fixed set, close verified Session IDs individually and check state before each call.

## Read-only cleanup capability diagnostics

MCP 0.2.1+ provides `inspect_sessions`, also available in read-only mode. Discover it before calling. Exact ID and nickname are mutually exclusive; omitting both inspects only allowlist-visible sessions. Prefer the bound ID for one task. Returned `sessions[]` separates prompt availability, process identity/TTY/job counts (plus bounded `process.active_jobs`, `process.stopped_jobs`, and `process.ignored_ancestors` such as `verified_login_ancestor` in current source), current CLI identity/persistence/activity evidence, `terminal_activity`, `business_acceptance`, and `close_readiness`. `business_acceptance=not_observed` means MCP does not accept work on the coordinator's behalf.

`close_readiness.status=eligible_if_unchanged` is only a conditional candidate from current evidence, with `authorization=not_granted`. It does not replace ownership, user authorization, a dry run, or a final recheck. Inspect reason, remediation, and CLI evidence_gap; a ready boolean is not a closing instruction. The tool writes no receipt, exits/closes nothing, sends no keys, and returns no raw command arguments, environment, or logs. It still reads necessary process and CLI metadata.

Report missing prompt and missing process evidence separately. Observed active/stopped jobs can establish busy, but observing no jobs alone does not establish idle. CLI identity can be verified while activity remains unknown. Ordinary registration is only a clue; without the current process instance and current-conversation evidence it is not verified. Old caches and startup UUIDs do not establish the current conversation. The source does not yet provide a trusted real-time lifecycle hook for every CLI or a public arbitrary PID/UUID registration endpoint; diagnostics must not invent one. On older installations without diagnostics, use exact-target closing dry runs under [startup checks](session-lifecycle.md).

```json
{"tool":"inspect_sessions","arguments":{"session_id":"session-1"}}
```

## Input and delivery semantics

- Newlines in send_text may execute immediately. For multiline, long, or complex instructions, default to a short instruction plus a decision file under the [file dispatch protocol](dispatch.md), not body pastes or piecemeal concatenation. Direct replies and file instructions contain no CR/LF, including trailing newlines. Read and verify the input, send enter separately according to actual submission semantics, then observe results.
- `[Pasted text #N]` may only indicate folding; it proves neither corruption nor submission. Do not press Enter blindly when contents cannot be verified. Clear only confirmed unsubmitted coordinator-owned drafts using known editor semantics, verify empty input, then switch to a file. For running or uncertain delivery, observe read-only without clearing/resending; see the dispatch protocol.
- Do not append to, clear, or overwrite existing user drafts. Establish ownership first. Record unsubmitted tasks as pending submission; echoed text is not execution evidence.
- Operate menus using actual screen options. Send text only when the interface explicitly accepts it; otherwise use the relevant keys and verify each step. Never blindly default to Enter.
- `api_acknowledged: true` / `task_completion: unknown` means only iTerm API acknowledgment, not CLI receipt, execution, or completion.
- Delivery may have occurred despite timeout/error. Check screen/history first and resend only if non-submission is confirmed. Otherwise keep observing or report uncertainty, especially for publishing, payments, or deletion.
- The service suppresses broadcasting internally. There is no public suppress_broadcast parameter; do not add nonexistent fields.

## Reading limitations

Screen/history are rendered text, not raw PTY data, internal CLI messages, or process state. TUIs may update only the screen without adding history, and prompts may remain visible during work. Combine current screen, history, and changes over time; one word or input box does not establish idle.

Read the screen first. If context is missing, read 100–300 recent lines, up to 2000 when needed. `truncated` means incomplete evidence. History coordinates may change with session resets or retention windows; they are not permanent event IDs. Deduplicate using positions and text summaries, but do not mistake animation changes for meaningful progress.

## Session and connection failures

On `SESSION_NOT_FOUND`, enumerate again; do not automatically bind a new Session by the same nickname. Disappearance does not prove task completion. Check existing results and ownership before creation/restoration.

MCP connection failures differ from CLI network errors. Restore read-only observation first; do not recreate terminals or replay instructions. `--read-only` exposes no write tools. Access restricted by `--session-id` prohibits new Windows/Tabs. The service serializes only within one MCP process; it does not lock user or other-agent input.
