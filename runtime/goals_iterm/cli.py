"""Finite local JSON dispatcher. No daemon, tool registration, or implicit sync."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import hashlib
import json
import sys
from pathlib import Path

from .contract import (CLOSE_OPERATIONS, MAX_REQUEST_BYTES, OPERATION_SCHEMAS,
                       RequestError, decode_json, exit_code, is_mutation, result,
                       validate_request)
from .observations import observation, verify_observation


def _fingerprint(request):
    body = {key: value for key, value in request.items() if key != "request_id"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


async def _dispatch(service, request):
    op, args = request["operation"], request["arguments"]
    if op in CLOSE_OPERATIONS:
        kind = "all" if op == "clean_all_sessions" else op.removeprefix("close_")
        return await service.invoke_close(kind, **args)
    if op == "list_sessions":
        rows = await service.invoke(service.catalogue)
        return {"sessions": rows, "observation": observation(rows)}
    method, positional = {
        "inspect_sessions": (service.inspect_sessions, (args.get("session_id"), args.get("nickname"))),
        "read_screen": (service.screen, (args.get("session_id"),)),
        "read_history": (service.history, (args.get("session_id"), args.get("lines", 100))),
        "send_text": (service.send, (args.get("session_id"), args.get("text"))),
        "send_keys": (service.send_key, (args.get("session_id"), args.get("key"))),
        "rename_session": (service.rename_session, (args.get("session_id"), args.get("name"))),
        "create_window": (service.create, ("window", None, args.get("command"))),
        "create_tab": (service.create, ("tab", args.get("window_id"), args.get("command"))),
    }[op]
    return await service.invoke(method, *positional)


def _close_result(request, data, began):
    status = data.get("status", "unknown")
    mapped = {"closed": "ok", "noop": "ok", "dry_run": "ok"}.get(status, status)
    if mapped not in {"ok", "refused", "partial", "unknown"}:
        mapped = "unknown"
    if mapped == "refused" and began:
        # A late refusal cannot erase an earlier write boundary. The detailed
        # close payload remains intact for per-session reconciliation.
        mapped = "unknown"
    effects = "unknown" if mapped in {"unknown", "partial"} else "confirmed" if began else "none"
    return result(request["request_id"], mapped, data.get("code") or "OK", data, side_effects=effects)


async def execute(request, *, state_dir=None, service_factory=None):
    """Run one validated request; injectable service enables transport-free tests."""
    from .operation_store import OperationStore
    from .policy import authorize, check_task_context, load_policy
    from .service import ItermTools
    from .closing_backend import ClosingBackend
    from .closing import RecoveryStore
    from .errors import DomainError

    request = validate_request(request)
    rid, op, args = request["request_id"], request["operation"], request["arguments"]
    mutation = is_mutation(request)
    store = OperationStore(state_dir=state_dir)
    service = None
    reserved = False
    began = False
    payload = None

    try:
        with store.operation_lock():
            policy = load_policy(state_dir)
            authorize(op, args, request, policy=policy)
            if mutation:
                reservation = store.reserve(rid, _fingerprint(request), op,
                                            task_context=request.get("task_context"),
                                            expected_observation=request.get("expected_observation"))
                if reservation.disposition == "completed":
                    return reservation.result
                if reservation.disposition == "unknown":
                    return result(rid, "unknown", "REQUEST_OUTCOME_UNKNOWN", side_effects="unknown",
                                  warnings=["This request was reserved previously. Reconcile with fresh reads; do not replay it."])
                reserved = True
            allowed = policy.session_ids
            service = service_factory() if service_factory else ItermTools(session_ids=allowed)
            if state_dir is not None and not service_factory:
                service._recovery_store = RecoveryStore(Path(state_dir) / "recovery")
            # An explicitly empty allowlist must not become the upstream
            # constructor's legacy falsy-list/unrestricted behavior.
            service.allowed = None if allowed is None else set(allowed)

            async def check_boundary(session_ids=None):
                nonlocal began
                try:
                    current_policy = load_policy(state_dir)
                    if session_ids is None:
                        rows = await service._all_rows()
                        visible = rows if allowed is None or op != "clean_all_sessions" else [r for r in rows if r["session_id"] in allowed]
                        selected = verify_observation(request, visible)
                        session_ids = [r["session_id"] for r in selected]
                    authorize(op, args, request, policy=current_policy, target_session_ids=session_ids)
                    context = request.get("task_context")
                    if context and "sessions" in context:
                        context = {**context, "sessions": {sid: value for sid, value in context["sessions"].items() if sid in session_ids}}
                    check_task_context(context, session_ids,
                                       registry_path=Path(state_dir) / "session-registry.json" if state_dir else None)
                except Exception as exc:
                    raise DomainError(getattr(exc, "code", "PRECONDITION_FAILED")) from exc
                began = True

            service.before_write = check_boundary
            if mutation:
                async with asyncio.timeout(15):
                    await service.backend.connect()
                    rows = await service._all_rows()
                    visible = rows if allowed is None or op != "clean_all_sessions" else [r for r in rows if r["session_id"] in allowed]
                    selected = verify_observation(request, visible)
                    ids = [r["session_id"] for r in selected]
                    authorize(op, args, request, policy=policy, target_session_ids=ids)
                    check_task_context(request.get("task_context"), ids,
                                       registry_path=Path(state_dir) / "session-registry.json" if state_dir else None)
                if op in CLOSE_OPERATIONS:
                    service._closing_backend = ClosingBackend(service.backend, allowed=service.allowed,
                                                              before_write=check_boundary)
            try:
                data = await _dispatch(service, request)
                payload = (_close_result(request, data, began) if op in CLOSE_OPERATIONS else
                           result(rid, "ok", "OK", data, side_effects="confirmed" if mutation else "none"))
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                    code = "CANCELLED"
                else:
                    code = getattr(exc, "code", "ITERM_API_ERROR")
                payload = result(rid, "unknown" if began else "refused", code,
                                 side_effects="unknown" if began else "none")
            finally:
                try:
                    await service.backend.close(timeout=2.0)
                except BaseException:
                    if payload is not None:
                        payload["warnings"].append("Helper connection cleanup could not be verified.")
                service = None
            if reserved:
                try:
                    store.finish(rid, payload)
                except Exception:
                    return result(rid, "unknown", "OPERATION_PERSISTENCE_FAILED", payload.get("data"),
                                  side_effects="unknown", warnings=["Outcome recording failed. Do not repeat this write."])
            return payload
    except BaseException as exc:
        code = "CANCELLED" if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)) else getattr(exc, "code", "RUNTIME_ERROR")
        payload = result(rid, "unknown" if began else "refused", code,
                         side_effects="unknown" if began else "none")
        if reserved:
            try:
                store.finish(rid, payload)
            except Exception:
                payload = result(rid, "unknown", "OPERATION_PERSISTENCE_FAILED", side_effects="unknown")
        return payload
    finally:
        if service is not None:
            try:
                await service.backend.close(timeout=2.0)
            except BaseException:
                pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RequestError(message)


def main(argv=None):
    parser = Parser(prog="itermctl")
    sub = parser.add_subparsers(dest="command", required=True)
    caps = sub.add_parser("capabilities")
    caps.add_argument("--json", action="store_true")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--live-api-check", action="store_true")
    invoke = sub.add_parser("invoke")
    invoke.add_argument("--request-file", default="-")
    status = sub.add_parser("operation-status")
    status.add_argument("--request-id", required=True)
    policy = sub.add_parser("policy")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    policy_sub.add_parser("show")
    configure = policy_sub.add_parser("configure")
    access = configure.add_mutually_exclusive_group(required=True)
    access.add_argument("--read-only", action="store_true")
    access.add_argument("--allow-writes", action="store_true")
    scope = configure.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all-sessions", action="store_true")
    scope.add_argument("--session-id", action="append")
    scope.add_argument("--no-sessions", action="store_true")
    try:
        options = parser.parse_args(argv)
        with redirect_stdout(sys.stderr):
            if options.command == "capabilities":
                payload = result(None, "ok", "OK", {"runtime_version": "0.4.0.dev0", "schema_versions": [1],
                    "operations": OPERATION_SCHEMAS, "required_mutation_preconditions": ["request_id", "expected_observation for existing resources", "task_context for registered sessions", "authorization_scope=all_sessions for clean_all_sessions"],
                    "exit_codes": {"0": "ok", "2": "refused", "3": "unknown_or_partial", "4": "request_or_runtime_error"}})
            elif options.command == "doctor":
                from .doctor import collect_doctor_report
                report = collect_doctor_report(live_api_check=options.live_api_check)
                payload = result(None, "refused" if report["status"] in {"blocked", "manual_action_required"} else "ok", "DOCTOR", report)
            elif options.command == "invoke":
                if options.request_file == "-":
                    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
                else:
                    with Path(options.request_file).open("rb") as stream:
                        raw = stream.read(MAX_REQUEST_BYTES + 1)
                payload = asyncio.run(execute(decode_json(raw)))
            elif options.command == "operation-status":
                from .operation_store import OperationStore
                record = OperationStore().status(options.request_id)
                payload = result(options.request_id, "ok", "OPERATION_STATUS", record)
            else:
                from .operation_store import OperationStore
                from .policy import load_policy, save_policy
                with OperationStore().operation_lock():
                    if options.policy_command == "configure":
                        ids = None if options.all_sessions else (options.session_id or [])
                        save_policy(read_only=options.read_only, session_ids=ids)
                    configured = load_policy()
                payload = result(None, "ok", "POLICY", {"schema_version": 1,
                    "read_only": configured.read_only, "session_ids": None if configured.session_ids is None else sorted(configured.session_ids)})
    except (Exception, KeyboardInterrupt) as exc:
        payload = result(None, "error", getattr(exc, "code", "RUNTIME_ERROR"))
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(main())
