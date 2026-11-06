# Session registry, startup checks, and finalization responsibility

Read this protocol when creating, taking over, reusing, or completing sessions. MCP still performs terminal operations. Registry files describe host-observed facts; they do not authorize closure or replace MCP's live preflight.

## Check recovery and finalization capabilities first

Before creation, check closing/diagnostic tools, current client permissions, and actual monitoring capabilities. Record observed MCP/CLI/Skill versions. Prefer the installed service's read-only `inspect_sessions` diagnostics (see [tool conventions](iterm-tools.md)); if unavailable, use a closing dry run with `dry_run=true, force=false` on the exact Session. Never use global cleanup as a task probe or invent preflight results for an uncreated target.

After a new CLI starts and before dispatching work, check:

- Whether launch settings permit conversation history persistence. If the interface explicitly says transcript saving is off, fix the new launch using that CLI's local help before dispatching. Do not indiscriminately delete environment variables or use unverified flags. Keep existing active sessions running, record limitations, and wait for an appropriate handoff point.
- Whether current conversation UUID evidence is bound to the actual process instance. Distinguish current evidence, startup-only arguments, and unknown. An empty new conversation may have no UUID before its first response; record unknown and recheck after a real response. Do not invent work or probe a busy CLI just to obtain one.
- Whether MCP can establish activity, persist a recovery receipt, and exit safely. A live process, running shell command, CLI awaiting input, and business acceptance are four different facts.

Also verify the normal-exit command supported by this CLI version. Record insufficient recovery evidence as `recovery_status=degraded/unknown` with a reason, separating chat recovery from resource cleanup. Evaluate [normal exit](natural-exit.md); missing UUID alone does not justify promising manual cleanup or declaring cleanup impossible. Unknown capability does not automatically cancel authorized work, but explicitly disabled history saving is not a valid default for new work. Address known blockers early rather than discovering all of them at exit.

`recovery_status=ready` is only the latest observation. It does not mean the session is currently closeable or that restoration was tested. Recheck processes, conversation identity, persistence, and tool results at finalization.

## Shared registry and handoff

Coordinators on the same machine share the registry, by default `~/.local/state/goals-iterm-skill/session-registry.json`. Update it with the bundled `scripts/session_registry.py`; inspect its `--help` for actual arguments. It uses the Python standard library and needs no service installation. Store runtime state privately, outside repositories and skill installation directories.

Each entry needs the exact Session ID, owner_task_id, coordinator_id, generation, current revision, origin, retention policy, and absolute audit path. Routine work uses inline rechecks in the current execution with `monitor_mode=inline`. Use `background` only when explicitly authorized and supported by real scheduling. `none` means no monitor; absent legacy fields mean `unknown`. The mode describes where checks are planned, not whether monitoring is alive; `monitor_status` is an independent state assertion. Add evidence-backed `owned_container` (only tab_id/window_id/basis), cleanup_authorization, Tab/Window IDs, session/broker epochs, process instance, CLI/chat UUID, activity/recovery state, acceptance basis, monitor status, cleanup reasons, and pending work. A nickname, directory, or PID alone is not an identity.

- Register immediately after successful creation. If registration fails, do not dispatch new work. For legacy sessions, use created/adopted only with origin evidence; otherwise mark unknown and retain.
- A new ledger's `audit_path` points to its stable index, normally `audits/<task-id>/index.md`. Locate daily event files through that index and host checkpoints. Date rollover does not change generation or require daily audit_path updates. Continue legacy single-file ledgers under the [audit protocol](audit.md#daily-files-and-date-rollover), updating audit_path normally without a schema change.
- Synchronize delivery outcomes, acceptance, reuse, Tab moves, CLI replacement, closing preflight, and actual results with the registry and append events under the [audit protocol](audit.md).
- Updates carry coordinator_id, generation, and expected_revision. File locking protects registry writes. On a version conflict, reread and investigate the live state; do not force a stale patch.
- Same-task coordinator handoff preserves business and cleanup outcomes, especially closing/unknown. Handoff must not erase unknown side effects. Giving a terminal to a new task requires an explicit handoff, generation increment, and removal of old acceptance/closure eligibility; the new task has its own ledger. Renaming does not create a new task, and an old completion message cannot close a reused terminal.
- Rebind, increment generation, and reverify identity/topology changes as required by the helper, especially Window exclusivity. Coordinator disappearance or stale records trigger investigation, not automatic ownership.

Common commands follow. Replace `/absolute/path/to/skill` and example IDs/generations with real values; record/patch files contain only observed, redacted fields:

```sh
python3 /absolute/path/to/skill/scripts/session_registry.py register --record /private/path/record.json
python3 /absolute/path/to/skill/scripts/session_registry.py list --task-id task-1
python3 /absolute/path/to/skill/scripts/session_registry.py update --session-id S1 --coordinator-id C1 --generation 1 --expected-revision 1 --patch /private/path/patch.json
python3 /absolute/path/to/skill/scripts/session_registry.py handoff --session-id S1 --coordinator-id C1 --generation 1 --expected-revision 2 --new-coordinator-id C2 --new-task-id task-2 --audit-path /private/path/task-2.md --reason "explicit task handoff"
python3 /absolute/path/to/skill/scripts/session_registry.py report --task-id task-2 --require-settled
```

Minimal register structure; this illustrates format, not real authorization or targets:

```json
{"session_id":"S1","owner_task_id":"task-1","coordinator_id":"C1","origin":"created","cleanup_policy":"auto_owned","audit_path":"/private/path/task-1.md","monitor_mode":"inline"}
```

Registry schema remains v1. Legacy v1 entries without `monitor_mode` read as `unknown`; do not erase/reset other fields. Same-task handoff sets mode unknown and preserves old real `schedule_handle`/`next_check_at` for the next coordinator to verify or disable. Cross-task handoff and identity-generation changes invalidate the old mode. Older installed registry scripts reject new fields; upgrade the coordinator's helper before writing `monitor_mode`.

Generation identifies an identity/handoff epoch. Ordinary dispatch, observations, and finalizing updates increase revision, not generation; do not hand off merely to stop monitoring. Old callbacks check both values and cannot dispatch business work during finalizing. Reconcile closing/unknown read-only and record the result before changing tasks or identity. Use returned revision/generation values, not mechanically reused examples. Identity/topology updates invalidate old completion/recovery eligibility; observe the live state again before restoring completed status. Cross-task handoff resets ownership to borrowed/retain and clears old authorization. If the new task already has explicit cleanup permission, a separate version-checked update must set both `cleanup_policy=auto_owned` and nonempty `cleanup_authorization` identifying its source; registry entries do not grant permission. Same-task handoff resets monitor status/mode to unknown and retains old schedule_handle/next_check_at for verification or disabling; a retained handle does not prove liveness. Time fields use UTC ISO 8601. A next_check_at alone is not scheduling; a real schedule_handle is required. `report` shows `monitor_mode` and `schedule_status`; inline never masquerades as scheduled. Only a real nonempty handle yields `schedule_status=scheduled`. `report --require-settled` returns nonzero for unsettled resources or zero matches; an empty report is not success.

The registry helper does not contact iTerm, send keys, exit CLIs, create background jobs, or prevent uncoordinated user/client input. Before terminal writes, still verify the latest registry and live state. Recorded state is neither a terminal lock nor authorization.

## Business completion still requires finalization

Record `execution_status`, `coordinator_phase`, and `cleanup_status` per Session. One completed flag must not hide remaining terminals.

1. A subtask may independently enter finalizing once its result is accepted, evidence is complete, and no downstream consumer needs its CLI context. It need not wait for parallel tasks. If reuse remains necessary, retain it with a purpose and recheck conditions.
2. Record business completed and coordinator finalizing, then stop and verify that target's business-writing monitor. The sole finalizer still owns [automatic cleanup](automatic-cleanup.md); this is not the end of coordination. Stopping the business monitor does not stop the current inline finalizer, which may wait with backoff and perform bounded read-only rechecks.
3. Mark explicitly user-retained or borrowed resources retained with retention_reason. A user retention reason needs the original wording/message source; reuse needs a concrete purpose. Do not infer “leave open” from “launch test.” If retention is time-limited, record retain_until; expiry triggers reassessment, not closure authorization.
4. For reclaimable task resources, normally exit the CLI, then verify and exit the idle shell. Verify and record resources already gone. For terminals that remain, refresh topology, dry-run, record intent, call close, and verify each outcome. Mark closed only with actual closure evidence. Explain retention; do not disguise blocked cleanup as retained.
5. Before reporting, run the task-filtered registry report and reconcile every registered resource with current observations. `--require-settled` checks recorded finalization, not actual terminal disappearance.

Failure, pause, cancellation, or waiting for the user does not automatically authorize closure. These states still need a resource disposition. Do not leave resources silently or force-close merely to pass a report.

## Bounded rechecks and unknown outcomes

Retain original targets and exact reasons when cleanup is blocked. Distinguish:

| Situation | Next action |
| --- | --- |
| Confirmed no side effects and a temporary condition | Inline finalizer may recheck with bounded backoff in this run; later checks require a recorded next check and real background schedule_handle |
| Only missing UUID, startup identity, or unverified history recovery | Record limitations and assess normal exit; if eligible, exit and reclaim. If the user requires recoverability, establish it first. Do not repeat identical failed preflights |
| Unknown ownership/process, identity conflict, or unclear work state | Retain and investigate; do not send exit or downgrade these to recovery warnings |
| Normal-exit outcome unknown | Read-only checks of the CLI/original Session; no resend, extra Enter, or signals; do not close before exit is confirmed |
| Lost close response, execution error, or closing/unknown state | Reconcile topology and the exact receipt read-only; no automatic resend or CLI recreation by old monitors |
| No scheduling capability or the run is about to end | Inline checks may continue with real waits while this execution remains active. Later checks require user permission, host capability, and a real background schedule_handle; otherwise report unscheduled, next action, and responsibility |

For the same unchanged finalization blocker, default to at most two rechecks and honor any longer service backoff. If unchanged after two, stop repeating attempts and record the blocker, next action, and owner. Do not mask unknown results or an unconfirmed first side effect with endless polling. This limit applies to repeated finalization attempts, not normal observation of healthy ongoing work. Rechecks only observe/finalize: do not restore business monitoring, expand to new Sessions, or escalate force. Any future checks must meet host-capability and authorization requirements and record actual scheduling results. `monitor_mode=background` or a timestamp alone is not a scheduled job.

## Final resource accounting

Alongside business results, report registered/observed resource counts and closed/retained/blocked/unknown totals with reasons. Separately state CLI/monitor status, recovery receipts and ledger links, next actions, and whether scheduling actually exists. Do not estimate memory savings without measuring. For multiple sessions, Tab IDs and nicknames help readability, while actual bindings retain exact IDs.

Every resource needs an explicit disposition before coordination ends. A real blocker may be handed off honestly to end the current turn. If accepted work still has blocked cleanup, preserve finalizing and cleanup blocked/unknown; pre-acceptance blockers retain their actual execution phase. Never claim full completion or scheduled actions that were not performed.

## Design tradeoffs

Markdown rules alone cannot detect an old coordinator overwriting a new task. A persistent cleanup daemon would add permissions and deployment burden. The lightweight registry therefore uses file locks and version checks, while Markdown retains human-readable process evidence and MCP protects actual operations. It targets a small number of concurrent local terminals. Use separate state directories across machines and explicit handoffs; local file locks are not distributed locks.

## Focused behavioral validation

| Scenario | Expected action |
| --- | --- |
| New Claude launch explicitly disables transcript saving | Fix the new launch before dispatch, not at closure |
| New empty conversation has no UUID | Record unknown and recheck after a real first response; no fabricated UUID/work |
| Prior task accepted, same Session begins new work | Handoff/new generation; old callbacks cannot close or overwrite the new task |
| Shared Window with one accepted subtask | Handle only that task's eligible Session/Tab, not the shared Window |
| Business completed, cleanup pending | Continue finalizing and expose unfinished resource accounting |
| Repeated identity preflight failure without new evidence | Stop repeating; assess normal exit only for missing chat identity, retain other identity blockers, and do not auto-force |
| Coordinator resumes after unknown close outcome | Reconcile read-only; do not close again based on timeout/pending |
| Retention expires while the user is using the resource | Retain and update records; expiry does not authorize closure |
| State-file update conflict or corruption | Stop new writes, investigate/restore records, and do not overwrite the original |
