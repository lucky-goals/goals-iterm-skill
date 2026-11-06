"""Focused tests for read-only macOS process inspection."""

from __future__ import annotations

import os
import signal
import unittest

from goals_iterm.process_inspection import MacOSProcessProvider, ProcessRecord


class ProcessInspectionTests(unittest.TestCase):
    def test_ps_runner_uses_argv_and_redacts_command_arguments(self):
        calls = []

        class Completed:
            stdout = "  12  1  12  12 ttys001 S+ Mon Oct 20 10:00:00 2026 /bin/zsh --secret=value\n"

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return Completed()

        provider = MacOSProcessProvider(runner=runner, enabled=True, own_pid=900)
        record = provider.get(12)
        self.assertIsNotNone(record)
        self.assertEqual(record.executable, "zsh")
        self.assertNotIn("secret", record.as_dict())
        self.assertEqual(calls[0][0][0:2], ["ps", "-ww"])
        self.assertNotIn("--secret=value", calls[0][0])
        self.assertFalse(calls[0][1].get("shell", True))

    def test_foreground_leaf_job_is_seen_when_job_pid_is_not_shell(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900)
        provider.list_processes = lambda: [
            ProcessRecord(10, 1, 10, 20, "ttys001", "S", "shell", "zsh"),
            ProcessRecord(20, 10, 20, 20, "ttys001", "R", "job", "python"),
        ]
        evidence = provider.inspect({"job_pid": 20, "tty": "ttys001"})
        self.assertEqual(evidence["identity"]["pid"], 20)
        self.assertEqual([item["pid"] for item in evidence["active_jobs"]], [20])
        self.assertTrue(evidence["foreground"])

    def test_shell_job_pid_binds_foreground_child_for_interruption(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900)
        provider.list_processes = lambda: [
            ProcessRecord(10, 1, 10, 20, "ttys001", "S", "shell", "zsh"),
            ProcessRecord(20, 10, 20, 20, "ttys001", "R", "job", "python"),
        ]
        evidence = provider.inspect({"job_pid": 10, "tty": "ttys001"})
        self.assertEqual(evidence["identity"]["pid"], 20)
        self.assertTrue(evidence["foreground"])

    def test_detached_descendant_remains_in_scoped_job_census(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900)
        provider.list_processes = lambda: [
            ProcessRecord(10, 1, 10, 20, "ttys001", "S", "shell", "zsh"),
            ProcessRecord(20, 10, 20, 20, "ttys001", "R", "job", "python"),
            ProcessRecord(21, 20, 21, 21, None, "R", "child", "worker"),
        ]
        evidence = provider.inspect({"job_pid": 20, "tty": "ttys001"})
        self.assertEqual(
            {item["pid"] for item in evidence["active_jobs"]},
            {20, 21},
        )

    def test_stale_foreground_pid_does_not_count_idle_shell_as_job(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900)
        provider.list_processes = lambda: [
            ProcessRecord(10, 1, 10, 10, "ttys001", "S", "shell", "zsh"),
        ]
        evidence = provider.inspect({"job_pid": 20, "tty": "ttys001"})
        self.assertEqual(evidence["active_jobs"], [])
        self.assertIsNone(evidence["identity"])

    def test_stable_same_tty_login_direct_parent_is_benign(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900)
        provider.list_processes = lambda: [
            ProcessRecord(5, 1, 5, 5, "ttys001", "S", "login-start", "login"),
            ProcessRecord(10, 5, 10, 10, "ttys001", "S", "shell-start", "zsh"),
        ]

        evidence = provider.inspect({"job_pid": 10, "tty": "ttys001"})

        self.assertEqual(evidence["active_jobs"], [])
        self.assertEqual(evidence["processes"], [])
        self.assertEqual(
            evidence["ignored_ancestors"],
            [
                {
                    "identity": {
                        "pid": 5,
                        "start_time": "login-start",
                        "start": "login-start",
                        "starttime": "login-start",
                        "tty": "ttys001",
                    },
                    "executable": "login",
                    "classification": "verified_login_ancestor",
                    "classification_reason": "stable_same_tty_direct_parent_of_shell",
                }
            ],
        )

    def test_login_name_alone_does_not_make_same_tty_process_benign(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900)
        provider.list_processes = lambda: [
            ProcessRecord(5, 1, 5, 5, "ttys001", "S", "login-start", "login"),
            ProcessRecord(10, 1, 10, 10, "ttys001", "S", "shell-start", "zsh"),
        ]

        evidence = provider.inspect({"job_pid": 10, "tty": "ttys001"})

        self.assertEqual([item["pid"] for item in evidence["active_jobs"]], [5])
        self.assertEqual(evidence["ignored_ancestors"], [])

    def test_login_parent_without_stable_identity_remains_a_blocking_job(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900)
        provider.list_processes = lambda: [
            ProcessRecord(5, 1, 5, 5, "ttys001", "S", None, "login"),
            ProcessRecord(10, 5, 10, 10, "ttys001", "S", "shell-start", "zsh"),
        ]

        evidence = provider.inspect({"job_pid": 10, "tty": "ttys001"})

        self.assertEqual([item["pid"] for item in evidence["active_jobs"]], [5])
        self.assertEqual(evidence["ignored_ancestors"], [])

    def test_interrupt_signals_exact_verified_foreground_group(self):
        signals = []
        provider = MacOSProcessProvider(
            enabled=True,
            own_pid=900,
            signaler=lambda pid, value: signals.append((pid, value)),
        )
        provider.list_processes = lambda: [
            ProcessRecord(900, 1, 900, 900, "ttys000", "S", "mcp", "python"),
            ProcessRecord(10, 1, 10, 20, "ttys001", "S", "shell", "zsh"),
            ProcessRecord(20, 10, 20, 20, "ttys001", "R", "job", "python"),
        ]
        result = provider.interrupt_foreground(
            {"pid": 20, "start": "job", "tty": "ttys001"},
            {"job_pid": 20, "tty": "ttys001"},
            {},
        )
        self.assertEqual(result["pid"], 20)
        self.assertEqual(signals, [(-20, signal.SIGINT)])

    def test_empty_process_table_does_not_prove_interrupt_completion(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900)
        provider.list_processes = lambda: []
        result = provider.verify_interrupt(
            {"pid": os.getpid(), "start": "unavailable"},
            {},
            {},
        )
        self.assertFalse(result["verified"])

    def test_surviving_observed_child_blocks_interrupt_completion(self):
        provider = MacOSProcessProvider(enabled=True, own_pid=900, verify_timeout=0.05)
        provider.list_processes = lambda: [
            ProcessRecord(21, 1, 21, 21, "none", "R", "child", "python"),
        ]
        result = provider.verify_interrupt(
            {"pid": 20, "start": "job", "tty": "ttys001"},
            {},
            {
                "process": {
                    "active_jobs": [
                        {"identity": {"pid": 20, "start": "job", "tty": "ttys001"}},
                        {"identity": {"pid": 21, "start": "child", "tty": "ttys001"}},
                    ],
                    "stopped_jobs": [],
                }
            },
        )
        self.assertFalse(result["verified"])


if __name__ == "__main__":
    unittest.main()
