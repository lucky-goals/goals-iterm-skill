# Task audit ledger template

> The index and daily-file sections below belong in separate files; do not copy the entire template into every day. Placeholders are not facts. Keep initial task facts unchanged; index pointers may be updated, while actual state comes from the latest events. Dates use the processing date in the task timezone.

## Index file: index.md

# Task audit ledger: <task name>

| Item | Content |
| --- | --- |
| Task ID | <unique task-id> |
| Goal | <required final outcome> |
| Decomposition and parallel plan | <single session with rationale, or parallel subtasks with per-session scope, non-overlap/Git-index guardrails, and integration order> |
| Working directory | <absolute path, or per-subtask paths> |
| Coordinator host | <client and available chat ID> |
| Executing CLI | <type and known version, or unknown> |
| Initial iTerm session | <nickname(s) and session_id(s); pending creation if not yet created> |
| CLI conversation identity | <chat UUID and source, unknown, or not applicable; never substitute iTerm ID> |
| Recovery record | <recovery_record_id, recovery_record_path, and receipt persistence result; none yet if unavailable> |
| Creation time and default timezone | <actual time with UTC offset; timezone name> |
| Initial resource ownership and policy | <per-resource owner_task_id, original IDs, origin, owned_container, cleanup_policy, and basis; append bindings after creation> |
| Authorization and constraints | <based on user instructions, without expanding permission> |
| Acceptance criteria | <individually verifiable conditions> |
| Registry and startup capabilities | <absolute registry path, coordinator_id/generation/revision; observed MCP/CLI/Skill versions, history persistence, identity/activity capabilities, degradation reasons> |
| Initial monitor state | <not established/taken over; monitor_mode=inline/background/none/unknown and actual handle if available; no fabricated inline handle> |
| Historical completeness | <recorded from task start/history before takeover incomplete> |
| Absolute index path | <stable index.md path or user-specified index file> |
| Current event file and latest event | <absolute YYYY-MM-DD.md path; latest E; update only from persisted facts> |
| Legacy single-file ledger | <historical-volume link, or none; do not move/rewrite old events> |

### Daily file index

| Processing date | Event file | Event range |
| --- | --- | --- |
| <YYYY-MM-DD> | <link to daily file; one row per date> | <persisted first and last E> |

## Daily file: YYYY-MM-DD.md

# Task events: <task name> · <processing date>

- **Task ID:** <same task-id as index>
- **Processing date and timezone:** <YYYY-MM-DD; timezone such as Asia/Shanghai>
- **Ledger index:** <absolute index path and link>
- **Previous event file:** <path and link, or none; may reference a legacy single-file ledger>
- **Inherited last event ID:** <previous volume's last E; none initially; never reset at rollover>

Round conventions: U is a logical user/coordinator round within the task; C is a per-session dispatch/reply round and does not increment for reads; E is a task event; D identifies a decision. Add native host-message mappings when available without pretending logical numbers are native IDs. Background wakeups reuse the latest U and name their trigger.

## Events, appended in order

### E<number> · <event title>

- **Recorded at:** <actual time with UTC offset>
- **Action/observation time:** <identify type; only observation time if source time is unavailable; note backfill>
- **Round:** U<number> / C<number, none, or unknown>; <available native-round mapping>
- **Trigger:** <user message/inline poll/background callback and available ID>
- **Session and generation:** <exact session_id; task generation>
- **Event type:** <dispatch intent/delivery result/CLI response/pending decision/decision/error/recovery/acceptance/monitor change/resource binding/startup check/handoff/registry conflict/finalization recheck/cleanup plan/closing intent/closing result/restoration verification/correction>
- **Related records:** <E and D IDs; add daily-file links across dates, or none>
- **User request / dispatched content:** <actual requirement or sent content; not applicable if appropriate>
- **File dispatch, if applicable:** <dispatch ID, immutable absolute path, summary, related C/D; actual single-line instruction; revision/supersession relationship; CLI reading state and evidence, or unobserved>
- **CLI response and evidence:** <excerpt or summary label, source tool, capture time/history position, truncation; none yet if unavailable>

> <Redacted and safely quoted CLI content; remove if not applicable>

- **Coordinator assessment:** <separate observed facts, inferences, and uncertainty>
- **Decision:** <pending/specific choice/no decision; D ID, self-contained question & affected objects, options, coordinator recommendation & rationale, decision maker, final rationale, and authorization source>
- **Actual action and delivery:** <pending/API acknowledged/delivery unknown/execution observed/no write; relevant tool result>
- **Outcome and task state:** <separate execution_status, coordinator_phase, and cleanup_status; known outcome of this event, not assumed later success>
- **Monitoring:** <monitor_mode, actual handle or none, monitor_status; next inline check or confirmed background scheduling; separate business-monitor stop from finalizer state>
- **Next step / verification limits:** <pending work, user decisions, unverified scope; acceptance entries give evidence/conclusions per criterion>

Add these for closing/restoration events as applicable; ordinary dispatch entries may omit them:

- **Cleanup basis and level:** <explicit request/automatic post-acceptance cleanup; acceptance evidence, creation/authorization source, ownership/retention policy, and rationale for container/Session selection>
- **Closing scope and parameters:** <original Session/Tab/Window IDs and affected panes; force, dry_run, authorization source>
- **Exit path and evidence:** <normal exit/MCP interruption and closure/already exited; command and version basis, pre-send completion evidence, actual submission/confirmation, separate CLI exit and terminal closure verification; degraded recovery and user requirements>
- **CLI recovery evidence:** <CLI type, chat UUID/source, cwd, resume.executable/argv, history persistence_status; separate from MCP receipt persistence>
- **Per-session results:** <result array, interruption/exit/closure_status and reasons; dry runs use would_close/would_skip, not actual closure>
- **Restoration verification:** <UUID identified/persisted/actually restored; relationship between new Session ID and original UUID, with evidence>
- **Retention and blockers:** <per-resource retention, borrowing, busy/unknown state, receipt/monitor issues; separate business completion and cleanup outcomes>

- **Resource accounting and handoff:** <registered/observed counts; closed/retained/blocked/unknown with reasons; responsibility, recheck conditions, real scheduler handle or unscheduled; report-check result>
