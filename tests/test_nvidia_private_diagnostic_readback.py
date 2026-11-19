"""Synthetic-only regression of exact Cloudflare NVIDIA diagnostic readback.

Mocks the control plane. Never uses an account, token, secret or network.
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nvidia_private_diagnostic_gate_once as gate

STORE = "a" * 32
OTHER_STORE = "b" * 32

def settings(flag, store=STORE):
    return {
        "success": True,
        "result": {"bindings": [
            {"name": "NVIDIA_API_KEY", "type": "secrets_store_secret",
             "secret_name": "NVIDIA_API_KEY", "store_id": store},
            {"name": "CC_NVIDIA_DIAGNOSTIC_ENABLED", "type": "plain_text",
             "text": flag},
        ]},
    }

class ExactDiagnosticReadbackTests(unittest.TestCase):
    def invoke(self, *, target, states, patch_success=True):
        """states[0] is the pre-mutation GET, rest are readback GETs."""
        actions = []
        queue = iter(states)
        def fake_cf(_account, _token, method, relative, payload=None):
            actions.append((method, relative, payload))
            self.assertEqual(relative, "/workers/scripts/cc-shared-nvidia-inference/settings")
            if method == "GET":
                value = next(queue)
                return (503, {}) if value == "invalid" else (200, settings(*value))
            self.assertEqual(method, "PATCH")
            self.assertEqual(set(payload), {"bindings"})
            rows = payload["bindings"]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], {
                "name": "NVIDIA_API_KEY", "type": "secrets_store_secret",
                "secret_name": "NVIDIA_API_KEY", "store_id": STORE,
            })
            self.assertEqual(rows[1], {
                "name": "CC_NVIDIA_DIAGNOSTIC_ENABLED",
                "type": "plain_text", "text": target,
            })
            return (200, {"success": True}) if patch_success else (503, {"success": False})
        buff = io.StringIO()
        with patch.object(gate, "cf", side_effect=fake_cf), \
             patch.object(gate.time, "sleep") as sleep, \
             contextlib.redirect_stdout(buff):
            try:
                gate.set_switch("fictional-account", "fictional-token", target)
                error = None
            except RuntimeError as err:
                error = str(err)
        return actions, sleep, buff.getvalue(), error

    def test_initial_enable_exact_first_readback(self):
        actions, sleep, output, error = self.invoke(
            target="1", states=[("0", STORE), ("1", STORE)])
        self.assertIsNone(error)
        self.assertIn("NVIDIA_DIAGNOSTIC_FLAG_VERIFIED=1", output)
        self.assertIn("NVIDIA_DIAGNOSTIC_READBACK_ATTEMPTS=1", output)
        self.assertEqual(sum(a[0] == "PATCH" for a in actions), 1)
        sleep.assert_not_called()

    def test_enable_waits_for_consistent_state_without_repatch(self):
        actions, sleep, output, error = self.invoke(
            target="1", states=[("0", STORE), ("0", STORE), ("0", STORE), ("1", STORE)])
        self.assertIsNone(error)
        self.assertIn("NVIDIA_DIAGNOSTIC_READBACK_ATTEMPTS=3", output)
        self.assertEqual(sum(a[0] == "PATCH" for a in actions), 1)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_secret_reference_must_converge_to_original(self):
        actions, _, output, error = self.invoke(
            target="1", states=[("0", STORE), ("1", OTHER_STORE), ("1", STORE)])
        self.assertIsNone(error)
        self.assertIn("NVIDIA_ACCOUNT_SECRETS_STORE_BINDING_PRESERVED=1", output)
        self.assertEqual(sum(a[0] == "PATCH" for a in actions), 1)
        self.assertNotIn(OTHER_STORE, output)

    def test_control_plane_get_failure_is_bounded_and_rechecked(self):
        actions, _, output, error = self.invoke(
            target="1", states=[("0", STORE), "invalid", ("1", STORE)])
        self.assertIsNone(error)
        self.assertIn("NVIDIA_DIAGNOSTIC_READBACK_ATTEMPTS=2", output)
        self.assertEqual(sum(a[0] == "PATCH" for a in actions), 1)

    def test_restore_is_verified_even_after_stale_read(self):
        actions, _, output, error = self.invoke(
            target="0", states=[("1", STORE), ("1", STORE), ("0", STORE)])
        self.assertIsNone(error)
        self.assertIn("NVIDIA_DIAGNOSTIC_FLAG_VERIFIED=0", output)
        self.assertEqual(sum(a[0] == "PATCH" for a in actions), 1)

    def test_persistent_wrong_flag_fails_closed_and_does_not_retry_patch(self):
        states = [("0", STORE)] + [("0", STORE)] * 6
        actions, sleep, output, error = self.invoke(target="1", states=states)
        self.assertEqual(error, "EXACT_BINDING_OR_FLAG_READBACK_MISMATCH")
        self.assertIn("NVIDIA_DIAGNOSTIC_READBACK_HOLD_CLASS=diagnostic_flag_not_at_target", output)
        self.assertNotIn("NVIDIA_DIAGNOSTIC_FLAG_VERIFIED=1", output)
        self.assertEqual(sum(a[0] == "PATCH" for a in actions), 1)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2, 3, 5, 8])

    def test_persistent_wrong_secret_store_fails_closed(self):
        states = [("1", STORE)] + [("0", OTHER_STORE)] * 6
        actions, _, output, error = self.invoke(target="0", states=states)
        self.assertEqual(error, "EXACT_BINDING_OR_FLAG_READBACK_MISMATCH")
        self.assertIn("NVIDIA_DIAGNOSTIC_READBACK_HOLD_CLASS=secret_binding_reference_mismatch", output)
        self.assertNotIn(STORE, output)
        self.assertNotIn(OTHER_STORE, output)
        self.assertEqual(sum(a[0] == "PATCH" for a in actions), 1)

    def test_already_disabled_restore_is_read_only(self):
        actions, sleep, output, error = self.invoke(
            target="0", states=[("0", STORE)])
        self.assertIsNone(error)
        self.assertIn("NVIDIA_DIAGNOSTIC_RESTORE_ALREADY_DISABLED=1", output)
        self.assertEqual(sum(a[0] == "PATCH" for a in actions), 0)
        sleep.assert_not_called()

if __name__ == "__main__":
    unittest.main()
