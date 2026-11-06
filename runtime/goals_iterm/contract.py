"""Versioned, dependency-free request validation for the local runner."""
from __future__ import annotations

import json
import re
from typing import Any

SCHEMA_VERSION = 1
MAX_REQUEST_BYTES = 262144
READ_OPERATIONS = frozenset({"list_sessions", "inspect_sessions", "read_screen", "read_history"})
CLOSE_OPERATIONS = frozenset({"close_session", "close_tab", "close_window", "clean_all_sessions"})
KEYS = ("enter", "tab", "escape", "backspace", "up", "down", "right", "left", "ctrl_c", "ctrl_d", "ctrl_u", "ctrl_l")


class RequestError(ValueError):
    code = "INVALID_REQUEST"


def _string(nullable=False):
    return {"type": ["string", "null"] if nullable else "string", "minLength": 1}


def _schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


SELECTORS = {key: _string(True) for key in ("session_id", "nickname", "tab_id", "window_id")}
CLOSE_FLAGS = {"force": {"type": "boolean", "default": False}, "dry_run": {"type": "boolean", "default": False}}
OPERATION_SCHEMAS = {
    "list_sessions": _schema({}),
    "inspect_sessions": _schema({key: SELECTORS[key] for key in ("session_id", "nickname")}),
    "read_screen": _schema({"session_id": _string()}, ("session_id",)),
    "read_history": _schema({"session_id": _string(), "lines": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 100}}, ("session_id",)),
    "send_text": _schema({"session_id": _string(), "text": _string()}, ("session_id", "text")),
    "send_keys": _schema({"session_id": _string(), "key": {"type": "string", "enum": list(KEYS)}}, ("session_id", "key")),
    "rename_session": _schema({"session_id": _string(), "name": _string(True)}, ("session_id",)),
    "create_window": _schema({"command": _string(True)}),
    "create_tab": _schema({"window_id": _string(), "command": _string(True)}, ("window_id",)),
    "close_session": _schema({**{key: SELECTORS[key] for key in ("session_id", "nickname")}, **CLOSE_FLAGS}),
    "close_tab": _schema({**{key: SELECTORS[key] for key in ("tab_id", "session_id", "nickname")}, **CLOSE_FLAGS}),
    "close_window": _schema({**{key: SELECTORS[key] for key in ("window_id", "session_id", "nickname")}, **CLOSE_FLAGS}),
    "clean_all_sessions": _schema(CLOSE_FLAGS),
}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RequestError("duplicate JSON key")
        result[key] = value
    return result


def decode_json(raw: bytes) -> Any:
    if len(raw) > MAX_REQUEST_BYTES:
        raise RequestError("request exceeds 262144 bytes")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(RequestError("non-finite number")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RequestError("invalid JSON request") from exc


def validate_request(value: Any) -> dict:
    fields = {"schema_version", "request_id", "operation", "arguments", "task_context", "expected_observation", "authorization_scope"}
    if not isinstance(value, dict) or set(value) - fields:
        raise RequestError("unknown request fields or non-object request")
    if type(value.get("schema_version")) is not int or value["schema_version"] != SCHEMA_VERSION:
        raise RequestError("unsupported schema_version")
    rid = value.get("request_id")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", rid):
        raise RequestError("request_id must be 1-128 ASCII identifier characters")
    op = value.get("operation")
    if not isinstance(op, str) or op not in OPERATION_SCHEMAS:
        raise RequestError("unknown operation")
    args = value.get("arguments", {})
    schema = OPERATION_SCHEMAS[op]
    if not isinstance(args, dict) or set(args) - schema["properties"].keys() or set(schema["required"]) - args.keys():
        raise RequestError("unknown or missing operation arguments")
    args = dict(args)
    for key, spec in schema["properties"].items():
        if key not in args:
            if "default" in spec:
                args[key] = spec["default"]
            continue
        v = args[key]
        types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        actual = "null" if v is None else "boolean" if type(v) is bool else "integer" if type(v) is int else "string" if isinstance(v, str) else "invalid"
        if actual not in types:
            raise RequestError(f"invalid type for {key}")
        if v is None:
            continue
        if isinstance(v, str):
            try:
                encoded = v.encode("utf-8")
            except UnicodeError as exc:
                raise RequestError(f"invalid Unicode for {key}") from exc
            if not v or (key not in {"text", "command"} and not v.strip()):
                raise RequestError(f"empty {key}")
            if key in {"text", "command"} and len(encoded) > 16384:
                raise RequestError(f"{key} exceeds 16384 UTF-8 bytes")
            if key.endswith("_id") and v in {"active", "all"}:
                raise RequestError("exact IDs required")
        if "enum" in spec and v not in spec["enum"]:
            raise RequestError(f"invalid {key}")
        if type(v) is int and (v < spec.get("minimum", v) or v > spec.get("maximum", v)):
            raise RequestError(f"invalid range for {key}")
    selectors = [key for key in SELECTORS if args.get(key) is not None]
    if op.startswith("close_") and len(selectors) != 1:
        raise RequestError("closing requires exactly one selector")
    if op == "inspect_sessions" and len(selectors) > 1:
        raise RequestError("inspection accepts at most one selector")
    if value.get("authorization_scope") not in (None, "all_sessions"):
        raise RequestError("invalid authorization_scope")
    for key in ("task_context", "expected_observation"):
        if key in value and not isinstance(value[key], dict):
            raise RequestError(f"{key} must be an object")
    return {**value, "arguments": args}


def is_mutation(request: dict) -> bool:
    return request["operation"] not in READ_OPERATIONS and not request["arguments"].get("dry_run", False)


def result(request_id, status, code, data=None, *, side_effects="none", warnings=None):
    return {"schema_version": SCHEMA_VERSION, "request_id": request_id, "status": status,
            "code": code, "data": data, "warnings": warnings or [], "side_effects": side_effects}


def exit_code(payload: dict) -> int:
    return {"ok": 0, "refused": 2, "unknown": 3, "partial": 3, "error": 4}.get(payload["status"], 4)
