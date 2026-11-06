# Exit the CLI normally, then reclaim the terminal

This is the preferred finalization path after acceptance, and also applies when the user has authorized closure and the CLI has stopped working. Normal exit uses the CLI's own supported exit command. Interrupting running work, sending signals, and guarded closure are separate operations governed by the standalone [runtime contract](runtime.md) and [closing and recovery](closing-and-recovery.md). They do not map simply to `force=false/true`.

## Before exiting

The sole finalizer verifies all of the following before recording exit intent:

- The original Session ID, task ownership, current CLI, and cleanup authorization remain valid. There is no retention request, takeover, or unknown shared member. Automatic finalization requires acceptance evidence; explicit closure requires corresponding authorization.
- Recent results and successive observations show that the CLI has finished its current work and is awaiting input, with no automatic retry, pending tools, unfinished subtasks, or background jobs that must be retained. The input contains no user draft, menu, or unresolved confirmation. A prompt, lack of output, or the CLI's own completion claim is not enough.
- The lifecycle state is finalizing/closing, the business-writing monitor has been stopped and verified, and the registry and ledger are writable. Exit is a finalizer action, not a new business dispatch; do not restart the monitor.
- The normal-exit method is confirmed by help for the current CLI version, verified launch information, an applicable command supplied by the user, or the interface itself. Prefer a confirmed `/quit` or `/exit`; use a shortcut only when verified. Do not assume every CLI supports the same command, or reopen menus merely to reconfirm reliable information. If unknown, perform necessary read-only checks first; do not send trial commands or natural-language requests such as “please exit” to the model.

First record known chat UUID, cwd, history, recovery parameters, and sources; leave unknown values explicitly empty. **Treat terminal ownership, process continuity, and conversation recovery identity separately.** A missing chat UUID, startup-only UUID, or unverified history recovery does not independently block normal exit when the conditions above hold. Record `recovery_status=degraded/unknown` and explain the limitation. If the user requires verified recoverability before closure, satisfy that requirement first.

If `inspect_sessions` or a closing dry run returns `CLI_IDENTITY_MISSING/CLI_IDENTITY_STARTUP_ONLY` solely because current chat identity is unavailable, independently evaluate normal exit under this protocol instead of repeating the same failed close call. If busy/unknown only reflects a live CLI process in the shell or a missing activity interface, record that limitation and use the actual work-completion evidence above. Do not rewrite runner results or claim its preflight passed. Real active work, unknown process binding, identity conflicts, scope/policy refusals, `SELF_PROTECTION`, initial receipt persistence failure, or an unresolved prior write outcome still block this path until investigated.

## Exit once; verify each outcome separately

1. Record exit eligibility, command source, recovery limitations, and original IDs in the ledger. Set `cleanup_status=closing` through a version-checked registry update. Reread the terminal before sending; stop if user input, activity, or identity has changed.
2. Use the runner's `send_text` operation for the verified single-line exit command without a newline, check the input, then use `send_keys` to send `enter` separately. A native exit command needs neither a decision file nor a model response. Observe exit only after delivery is confirmed. If the response is lost, reconcile by request ID and fresh read-only observation; do not resend or add Enter. Skip sending if the CLI has already exited.
3. Use a real host wait and read the result to confirm CLI exit. Evidence should include exit feedback or the returned shell interaction state, together with available process or shell-integration evidence that the original CLI ended. A shell-like prompt or API acknowledgment alone is insufficient. If the Session disappears automatically, verify the original ID and pre-exit evidence, record actual closure, and send nothing more.
4. If the CLI has exited but the Session remains, use “Normal exit of the remaining shell” below. Do not deliberately trigger a failed close just to obtain permission to exit. If shell normal-exit conditions are not met, select the exact target under [automatic cleanup](automatic-cleanup.md) and assess the guarded runtime close operation. Reclaim a parent Tab/Window only when both the original authorization and current exclusive ownership allow it. Do not quit the entire iTerm application.
5. Record CLI exit, Session/Tab/Window disappearance, and recoverability separately. Empty `cli_sessions[]` after exit is not evidence that the original conversation was saved. A later shell-closing receipt is not a pre-exit chat recovery receipt. Retain known recovery details for the original CLI in the ledger; never fabricate receipt paths or UUIDs.

The CLI-to-shell transition is expected during finalization; record it. Do not treat it as a new task, rebind it, clear acceptance, or restart the CLI. Original CLI/process fields in the registry now serve only as historical references, not fresh preflight evidence for the shell. Stop finalization and investigate unexpected process replacement or new user work under the lifecycle protocol.

When work is accepted, resources are actually closed, the business monitor is stopped, and nothing remains, set the coordinator phase to `settled`. Preserve and explain the real `recovery_status=degraded/unknown`; do not change it to ready merely to pass a resource report. If recoverability is an acceptance criterion, an unmet recovery requirement remains outstanding.

## Normal exit of the remaining shell

For a new task-owned Session subject to default cleanup, or a Session the user has explicitly authorized for cleanup, the finalizer may send the shell built-in `exit` through the runner's input operations when the following conditions hold. This reuses existing cleanup authorization; do not request separate approvals for exiting the CLI, exiting the shell, and closing the Tab. It does not apply when the user authorized only CLI exit or asked to retain the terminal.

- It is still the original Session with unchanged ownership, generation, and cleanup scope. CLI exit has been verified, or this dedicated shell has not yet launched a CLI. The current interface is a known shell ready for input, without a draft, menu, or unresolved confirmation.
- The work has been accepted or its termination explicitly authorized, and the business monitor is stopped. There is no user takeover, new command, active/stopped job, or background service to retain. Prompt appearance, no output, and `active_job_count=1` cannot establish these facts on their own.
- Use fresh shell-integration or process/job evidence to establish idleness. A missing prompt does not mean busy; busy may also result from infrastructure processes being counted as jobs. To interpret busy/unknown as a diagnostic limitation, account for each observed process, such as the root shell and a `login` ancestor whose parent-child relationship has been verified. Do not infer a false positive from a process name, count, or historical example alone. If the runtime exposes only a count and real jobs cannot be ruled out, retain the resource and report the evidence gap.
- There is no scope/policy refusal, `SELF_PROTECTION`, identity conflict, initial receipt persistence failure, or unexplained write side effect. Normal exit does not waive these protections. Never interleave input with a close operation still in progress.

Procedure:

1. Save exit intent, idleness evidence, diagnostic limitations, and original IDs; recheck the latest registry and terminal state. Use the runner's `send_text` operation to send `exit` without a newline, verify it, then use `send_keys` to send `enter` separately. **CLI `/exit` and shell `exit` are different; do not send `/exit` to zsh/bash.** Do not blindly send Ctrl-D or follow with signals.
2. Submit normal exit once per layer. If the shell warns of stopped/running jobs, unsaved content, or an exit hook requiring confirmation, stop automatic input and investigate. Do not send `exit` again to force confirmation. Reconcile uncertain delivery or exit read-only; do not resend.
3. Enumerate to verify the original Session and Tab. Whether shell exit removes them depends on iTerm settings; mark closed only after disappearance. If the shell has ended but the terminal remains, use the runtime close operation on the exact remaining target with `dry_run=true, force=false`, then repeat the fresh preflight and send the mutation only if scope and membership still match. Record a refusal as a blocker; do not escalate force.
4. One pane exiting does not prove the whole Tab/Window was reclaimed. Report only resources that actually disappeared. Do not affect a borrowed Window, other panes, or retained resources merely to close a parent container.

After `ACTIVITY_BLOCKED/ACTIVITY_UNKNOWN`, distinguish real jobs from diagnostic limitations under the conditions above. If eligible, exit normally without requesting the same authorization again or pretending runner preflight passed. After `INTERRUPT_UNVERIFIED` or partial results, first reconcile the request ID, recovery receipt, current processes, and topology read-only. `interruption=not_attempted` is not proof that no signal was sent. Reevaluate normal exit only after the previous operation has ended and current state and remaining responsibility are known. Otherwise preserve unknown/blocked.

## When the outcome is uncertain

Submit each normal-exit command at most once. If exit is unconfirmed, perform [bounded rechecks](session-lifecycle.md#bounded-rechecks-and-unknown-outcomes) read-only. Do not add Ctrl-C/Ctrl-D, kill processes, or escalate force. Confirm an exit dialog only when its choices are clear, belong to this exit, and do not expand authorization. Stop and investigate if it involves discarding unsaved content, running work, or recovery requirements. Explain whether the blocker is an unsupported command, unconfirmed exit, or refused terminal closure. Missing UUID alone is not a reason to ask the user to run `/exit` manually.

## Focused behavioral validation

| Evidence | Expected action |
| --- | --- |
| Accepted task, CLI stopped, verified exit command, only chat UUID missing | Save recovery limitations, exit once, verify, then reclaim the shell |
| Same missing UUID, but CLI is running tools or automatically retrying | Do not send exit; wait or follow existing explicit interruption authorization |
| User requires recoverability before closure, with no recovery evidence | Retain, obtain evidence, or hand off; do not use default degraded recovery |
| User draft, identity conflict, or another task takes over | Stop writing; do not clear the draft or exit |
| Exit delivery times out and the screen is unclear | Reconcile read-only; do not resend exit/Enter or restore the CLI |
| Normal exit automatically removes the Session | Verify the original ID disappeared, record closed, and do not call close again |
| Shell closing preflight passes after normal exit | Close the exact remainder with force=false; report exit and closure separately |
| CLI exited, dedicated shell verified idle, cleanup already authorized | Send shell `exit` once through the bundled runner and verify Session/Tab disappearance without another approval |
| Prompt missing; fresh evidence identifies the sole counted job as the shell's login ancestor | Record the diagnostic limitation; send shell `exit` if all other conditions hold, without automatic force |
| active_job_count=1 but no job identity details | Do not assume shell/login; obtain evidence or retain |
| CLI exited but shell has a background service or stopped job | Retain and check existing authorization; do not automatically exit or repeat confirmation |
| Shell exit warns about jobs, or delivery is unknown | Stop additional input and reconcile read-only; do not repeat exit/Ctrl-D |
| Shell ended but iTerm retains the ended Session | Preflight and normally close the exact target; do not record closed before disappearance |
| Forced exit verification failed and current state remains unclear | Reconcile side effects read-only; do not immediately send exit |
| Initial recovery-receipt failure or SELF_PROTECTION | Retain and address the original blocker; do not switch to normal exit to evade it |
