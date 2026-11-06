import json
import unittest

from goals_iterm.contract import OPERATION_SCHEMAS, RequestError, decode_json, validate_request
from goals_iterm.observations import ObservationError, observation, verify_observation


def request(operation, arguments=None, **extra):
    return {"schema_version": 1, "request_id": "request-1", "operation": operation,
            "arguments": arguments or {}, **extra}


class ContractTests(unittest.TestCase):
    def test_all_thirteen_operations_and_defaults(self):
        self.assertEqual(len(OPERATION_SCHEMAS), 13)
        self.assertEqual(validate_request(request("read_history", {"session_id": "s"}))["arguments"]["lines"], 100)
        self.assertFalse(validate_request(request("close_session", {"nickname": "name"}))["arguments"]["force"])

    def test_no_coercion_unknown_fields_or_selector_ambiguity(self):
        bad = [request("close_session", {"session_id": "s", "force": "false"}),
               request("close_session", {"session_id": "s", "nickname": "n"}),
               request("close_tab"), request("read_history", {"session_id": "s", "lines": True}),
               request("read_screen", {"session_id": "active"}), request("create_window", {"force": True}),
               request("send_keys", {"session_id": "s", "key": "ctrl_z"}),
               request("list_sessions", surprise=True), request("list_sessions", schema_version=True)]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(RequestError):
                validate_request(item)

    def test_unicode_bytes_and_exact_newlines(self):
        text = "雪\n" * 4096
        self.assertEqual(validate_request(request("send_text", {"session_id": "s", "text": text}))["arguments"]["text"], text)
        for invalid in [text + "x", "\ud800", ""]:
            with self.assertRaises(RequestError):
                validate_request(request("send_text", {"session_id": "s", "text": invalid}))

    def test_json_rejects_duplicate_keys_nonfinite_and_oversize(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b" " * 262145, b"\xff"]:
            with self.assertRaises(RequestError):
                decode_json(raw)
        self.assertEqual(decode_json(json.dumps(request("list_sessions")).encode())["operation"], "list_sessions")


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"session_id": "s1", "tab_id": "t", "window_id": "w", "name": "one"},
                     {"session_id": "s2", "tab_id": "t", "window_id": "w", "name": "two"}]

    def req(self, operation, arguments):
        return request(operation, arguments, expected_observation=observation(self.rows))

    def test_reconnect_epochs_and_cli_shell_transition_do_not_stale_ids(self):
        changed = [dict(row, target={"session_epoch": "new", "broker_epoch": "new"}, context_summary="shell") for row in self.rows]
        self.assertEqual(len(verify_observation(self.req("send_text", {"session_id": "s1"}), changed)), 1)

    def test_replaced_or_moved_target_and_unknown_identity_refused(self):
        for changed in [[dict(self.rows[0], session_id="replacement")], [dict(self.rows[0], tab_id="other")]]:
            with self.assertRaises(ObservationError):
                verify_observation(self.req("send_text", {"session_id": "s1"}), changed)
        invalid = self.req("send_text", {"session_id": "s1"})
        invalid["expected_observation"]["sessions"][0]["window_id"] = None
        with self.assertRaises(ObservationError):
            verify_observation(invalid, self.rows)

    def test_container_membership_add_remove_but_unrelated_is_ok(self):
        req = self.req("close_tab", {"tab_id": "t"})
        for changed in [self.rows[:1], self.rows + [dict(self.rows[0], session_id="new")]]:
            with self.assertRaises(ObservationError):
                verify_observation(req, changed)
        other = {"session_id": "other", "tab_id": "other-tab", "window_id": "other-window"}
        self.assertEqual(verify_observation(req, self.rows + [other]), self.rows)

    def test_missing_observation_refused_before_existing_resource_write(self):
        with self.assertRaises(RequestError):
            verify_observation(request("send_keys", {"session_id": "s1"}), self.rows)
        self.assertEqual(verify_observation(request("create_window"), self.rows), [])


if __name__ == "__main__":
    unittest.main()
