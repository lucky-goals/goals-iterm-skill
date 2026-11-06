# Automatic cleanup after acceptance

Use this workflow after the coordinator has verified every acceptance criterion. Reclaim dedicated terminals created for the task by default; explicit user retention takes precedence. Paused, failed, canceled, waiting-user, or budget-exhausted tasks, and tasks with only a CLI completion claim, do not trigger this workflow. Handle explicit closure/cancellation requests under [closing and recovery](closing-and-recovery.md).

## Establish ownership when resources are created

Use the shared registry helper under the [session lifecycle protocol](session-lifecycle.md) when creating, taking over, or restoring sessions. Keep resource records with task state and the [audit ledger](audit.md):

| Field | Meaning |
| --- | --- |
| owner_task_id | Owning task; mark unknown when ownership cannot be established |
| session_id / tab_id / window_id | Original tool-returned IDs, retaining identity/generation evidence; nicknames are not substitutes |
| origin | Created for this task, explicitly adopted with cleanup permission, borrowed, or unknown |
| owned_container | A Tab/Window whose task ownership is proven by creation results or explicit authorization; parent membership alone does not confer ownership |
| cleanup_policy | `auto_owned` or `retain`, with creation/authorization basis and any retention request |
| execution_status / cleanup_status | Independent business and cleanup states; cleanup may be pending/closing/closed/retained/blocked/unknown |

These are host task-record fields, not runtime request parameters. Bind real IDs after successful creation. If creation is uncertain, reconcile the operation request and fresh topology first; do not invent a cleanup target. Retain legacy resources without ownership evidence rather than fabricating their creation history.

- A new Window, initial Tab, and Session returned by `create_window` may be registered as task-owned.
- A new Tab and Session returned by `create_tab` may be registered; its preexisting Window remains borrowed by default.
- A CLI started in a user's existing Session, or work taken over in it, defaults to `retain`. Make it reclaimable only with existing explicit cleanup authorization. Authorization for a Session does not automatically cover its parent Tab/Window.
- When restoring into a new dedicated terminal, register the new resource and distinguish the original CLI chat UUID from new iTerm IDs. Retain borrowed restoration terminals.
- Briefly state the default post-completion cleanup policy at creation; no additional confirmation is needed. Record the scope of requests such as “keep the terminal” or “leave it open so I can inspect the results.” If ambiguous, retain the whole affected container. Do not automatically reclaim resources inside a retained container.
- Register new dedicated resources as `auto_owned`, including launch, model, or parameter tests. “Start a session” or “test whether it launches” does not by itself request retention after acceptance. Retain only for an explicit request to leave it available for interaction or an actual unfinished reuse need, recording the user's words/message source or concrete purpose. Never invent “the user asked to retain it.” Distinguish borrowed resources, unknown ownership, and explicit retention. A borrowed parent Window does not make a newly created Tab borrowed.

## Select the closing level from eligible Sessions

After acceptance and recording results and necessary feedback, refresh `list_sessions`. Use original IDs and the latest user instructions to verify ownership, task state, and container membership. Select only accepted, still task-owned Sessions that have not been retained or taken over. Retain targets with new user input, unfinished subtasks, background jobs, or identity changes. Main-task completion does not imply that every pane is finished.

Choose **nonoverlapping** targets:

1. **Exclusive Window:** use `close_window(window_id=...)` only when the Window itself was created for the task or explicitly authorized for cleanup, and every current Tab/Session is proven to belong to this task, be complete, and be reclaimable.
2. **Exclusive Tab:** otherwise, if the Tab itself is task-owned and all current panes qualify, use `close_tab(tab_id=...)`, retaining its Window and other Tabs.
3. **Individual Session:** for shared/borrowed containers, unknown members, or unproven exclusivity, use `close_session(session_id=...)` only for Sessions with complete ownership evidence.

A single visible Session/Tab, matching titles/nicknames, or idleness does not establish exclusive ownership. A session policy may hide sibling panes. Without complete membership evidence, do not elevate to container closure; use the verified Session. Container closing must still pass a fresh runtime preflight with the expected observation.

Do not separately close a Session already included in a chosen Window/Tab. Automatic finalization **does not call `clean_all_sessions`**; reserve global cleanup for explicit requests covering its scope. Record targets already gone; do not send a replacement close to a new object with the same nickname. Report the observed state of empty parents; do not guess or close a user's preexisting parent container merely to make everything disappear.

## Execution and stopping conditions

1. Keep business `completed`, move the coordinator to `finalizing`, and mark cleanup `pending`. Persist finalizing and the new revision through a version-checked update, then stop and verify the targets' writing monitors. The sole finalizer remains responsible for closing and resource accounting, normally performing bounded read-only rechecks and real host waits within the current execution. This does not restart business dispatch or require fabricated background handles. Do not end coordination just because the business monitor stopped; late callbacks must not dispatch. If stopping the monitor or writing the ledger fails, mark cleanup `blocked`, retain resources, and report it.
2. For each Session, prefer [normal exit](natural-exit.md): verify conditions, save known recovery details, exit the CLI, then follow that same protocol to exit the verified idle remaining shell. Skip the CLI command if it already exited. A dedicated test shell that never launched a CLI may proceed directly to shell-exit checks. Reconcile unconfirmed exit read-only without closing the container. Record resources already gone and leave them alone. Missing chat UUID alone does not end finalization. If normal exit is ineligible, assess the guarded runner path under [closing and recovery](closing-and-recovery.md); idle appearance is not sufficient evidence.
3. If terminals remain after normal exit, or guarded close was selected, refresh retention requirements and topology, choose nonoverlapping closing levels again, and call `dry_run=true, force=false` on exact targets. Inspect membership and blockers. Before the mutation, take a fresh `list_sessions` observation, record closing intent, and include that `expected_observation` in the request. The runtime persists a recovery receipt for the current targets; a post-CLI shell receipt does not prove the original chat is recoverable. A dry run does not freeze membership; refresh the observation before execution. Do not split a refused container into smaller close attempts to evade its preflight.
4. After the call, record per-Session chat UUID, cwd, resume parameters, CLI history state, receipt path, request ID, and actual result under the [runtime contract](runtime.md), then enumerate to verify. Mark verified closure `closed`, user-retained/borrowed resources `retained`, definite blockers `blocked`, and lost responses or uncertain side effects `unknown`. Business completion and unfinished cleanup may coexist.
5. **Automatic cleanup does not escalate force, kill processes, or blindly send Ctrl-C/Ctrl-D.** For missing chat identity or activity diagnostics, use the normal-exit protocol to distinguish recovery limitations from actual work state; never rewrite runner preflight results. Investigate shell activity refusals as possible diagnostic limitations under that protocol. Do not request force merely because of an error code or assume idleness from a count. Retain and report real activity, unknown scope/processes, identity conflicts, initial receipt failure, or unresolved normal-exit eligibility. A post-action receipt update failure may already have side effects; verify actual outcomes. When explicit interruption/force authorization already exists, use the guarded runner operation without asking again.
6. Do not retry whole batches after timeouts or partial failure, restore closed terminals, or restart business monitors. After interrupted finalization, restore the ledger and verify targets first. Reconcile unknown last actions read-only; `pending` alone is not a reason to resend. Do not repeat confirmed closure. Follow lifecycle retry limits and backoff for checks within the current execution. Future checks after execution ends require an explicit user request for background work, real host scheduling, and authorization; never promise background cleanup without them.

Before ending, run the registry report under the [lifecycle protocol](session-lifecycle.md) and account for every resource. Blocked/unknown resources need specific reasons and next actions; do not relabel them retained. Report business results, monitor status, and cleanup separately: which Sessions/Tabs/Windows closed, which remain and why, outstanding work, chat UUID/recovery receipts, and ledger links. Not every retained resource is a failure, and business completion does not mean all terminals closed.

## Focused behavioral validation

| Scenario | Expected action |
| --- | --- |
| New task-owned exclusive Window; all subtasks accepted and preflight eligible | Stop monitors, dry-run and close the exact Window, record per-Session recovery details, and avoid duplicate child calls |
| Dedicated Tab created in a user's Window with other user Tabs | Reclaim only the new Tab; retain the original Window and other Tabs |
| Unknown pane added to a task-owned Tab | Do not close the whole Tab; handle only the original Session with complete evidence and no retention request |
| Launch-only CLI test accepted, with no retention request | Default the new dedicated Tab to auto_owned, enter finalizing, exit CLI and idle shell normally, then verify |
| User asks to start a session and leave it open for later interaction | Record the request and mark retained after acceptance; do not apply test cleanup defaults |
| Work completed in a preexisting user Session without cleanup permission | Retain the Session; record business completion and retained cleanup |
| User asks to keep the task Window for inspection | Retain that Window and its children; still stop the business monitor and record why |
| Main task claims completion but acceptance fails or subtasks remain | Do not trigger automatic cleanup |
| Accepted work but the runtime returns busy/unknown | Distinguish actual activity from missing diagnostic evidence; use normal exit only when fully eligible, otherwise retain without automatic force |
| Accepted work and normal-exit conditions satisfied, only chat UUID missing | Save limitations, exit and verify, then reclaim the terminal |
| Monitor stop fails or audit files are unwritable | Do not call close; record/report verifiable state |
| Allowlist exposes only one Session in a dedicated Window | Without complete exclusive ownership evidence, use only the exact Session; do not infer Window scope |
| Foreign pane or user takeover after dry run | Refresh ownership and targets; retain affected resources rather than reusing the old container plan |
| Close response lost and a late callback arrives | No business writes; reconcile read-only, without resend or recreation |
| Legacy task lacks creation/authorization records | Retain by default; do not invent ownership from nickname, cwd, or current appearance |
