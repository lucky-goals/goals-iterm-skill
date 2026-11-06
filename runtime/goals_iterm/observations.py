"""Reconnect-safe topology preconditions; broker epochs remain invocation-local."""
from __future__ import annotations

from .contract import RequestError


class ObservationError(ValueError):
    code = "TARGET_CHANGED"


def observation(rows):
    return {"sessions": [{key: row.get(key) for key in ("session_id", "tab_id", "window_id")} for row in rows]}


def selected_rows(operation, arguments, rows):
    if operation == "create_window":
        return []
    if operation == "clean_all_sessions":
        return rows
    if operation == "create_tab":
        return [r for r in rows if r.get("window_id") == arguments["window_id"]]
    selected = []
    for field in ("session_id", "nickname", "tab_id", "window_id"):
        value = arguments.get(field)
        if value is None:
            continue
        if field == "nickname":
            selected = [r for r in rows if r.get("name", "").strip().casefold() == value.strip().casefold()]
            if len(selected) != 1:
                raise ObservationError("nickname is absent or ambiguous")
        else:
            selected = [r for r in rows if r.get(field) == value]
        break
    if not selected:
        raise ObservationError("selected resource is absent")
    if operation in {"close_tab", "close_window"}:
        key = "tab_id" if operation == "close_tab" else "window_id"
        ids = {r.get(key) for r in selected}
        if len(ids) != 1 or None in ids:
            raise ObservationError("container identity is unknown")
        selected = [r for r in rows if r.get(key) in ids]
    return selected


def verify_observation(request, rows):
    """Require fresh known membership for writes to existing resources.

    Session IDs are iTerm's original IDs, never a persisted broker epoch. A
    CLI-to-shell transition has no impact on these topology preconditions.
    """
    operation = request["operation"]
    selected = selected_rows(operation, request["arguments"], rows)
    if operation == "create_window":
        return selected
    expected = request.get("expected_observation")
    if not isinstance(expected, dict) or set(expected) != {"sessions"} or not isinstance(expected["sessions"], list):
        raise RequestError("existing-resource writes require expected_observation from list_sessions")
    prior = {}
    for entry in expected["sessions"]:
        if not isinstance(entry, dict) or set(entry) != {"session_id", "tab_id", "window_id"}:
            raise RequestError("invalid observation entry")
        if any(not isinstance(entry[k], str) or not entry[k] for k in entry):
            raise ObservationError("observation has unknown identity")
        if entry["session_id"] in prior:
            raise RequestError("duplicate observed session")
        prior[entry["session_id"]] = entry
    for current in observation(selected)["sessions"]:
        if current != prior.get(current["session_id"]):
            raise ObservationError("selected session identity or membership changed")
    if operation in {"close_tab", "close_window", "create_tab", "clean_all_sessions"}:
        if operation == "clean_all_sessions":
            expected_ids = set(prior)
        else:
            key = "tab_id" if operation == "close_tab" else "window_id"
            container_id = request["arguments"].get(key) or (selected[0].get(key) if selected else None)
            expected_ids = {sid for sid, entry in prior.items() if entry[key] == container_id}
        if expected_ids != {r["session_id"] for r in selected}:
            raise ObservationError("container membership changed")
    return selected
