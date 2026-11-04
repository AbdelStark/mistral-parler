"""Offline admission tests: no audio IO, provider requests or paid SDK network."""

import unittest
from unittest.mock import Mock

from parler.hosted import HostedAccessError, run_hosted_pipeline

FEATURE = "11111111-1111-4111-8111-111111111111"


class HostedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.billing = Mock()
        self.billing.get_or_create_customer.return_value = {"customer": {"id": "customer"}}
        self.billing.check_entitlement.return_value = {"check": {"kind": "access", "allowed": True}}
        self.runner = Mock(return_value="completed")

    def run_hosted(self, **overrides):
        args = {
            "require_workspace": lambda: "verified-workspace",
            "billing": self.billing,
            "access_feature_id": FEATURE,
            "_runner": self.runner,
        }
        args.update(overrides)
        return run_hosted_pipeline("private-recording.wav", {"api_key": "never-send"}, **args)

    def test_authenticated_workspace_is_the_only_billing_identity(self):
        self.assertEqual(self.run_hosted(), "completed")
        self.billing.get_or_create_customer.assert_called_once_with(
            external_user_id="parler:workspace:verified-workspace"
        )
        self.billing.check_entitlement.assert_called_once_with(
            customer_id="customer", internal_feature_id=FEATURE, quantity="1"
        )
        self.runner.assert_called_once_with("private-recording.wav", {"api_key": "never-send"})

    def test_unauthenticated_host_never_touches_billing_or_audio(self):
        with self.assertRaises(HostedAccessError):
            self.run_hosted(require_workspace=lambda: "")
        self.billing.get_or_create_customer.assert_not_called()
        self.runner.assert_not_called()

    def test_auth_failure_propagates_without_initializing_pipeline(self):
        with self.assertRaises(PermissionError):
            self.run_hosted(require_workspace=Mock(side_effect=PermissionError("sign in")))
        self.billing.get_or_create_customer.assert_not_called()
        self.runner.assert_not_called()

    def test_revocation_is_observed_on_the_next_run(self):
        self.run_hosted()
        self.billing.check_entitlement.return_value = {
            "check": {"kind": "access", "allowed": False}
        }
        with self.assertRaises(HostedAccessError) as error:
            self.run_hosted()
        self.assertEqual(error.exception.code, "plan_required")
        self.assertEqual(self.runner.call_count, 1)

    def test_provider_errors_are_closed_and_sanitized(self):
        self.billing.check_entitlement.side_effect = RuntimeError("private-provider-key")
        with self.assertRaises(HostedAccessError) as error:
            self.run_hosted()
        self.assertEqual(error.exception.code, "billing_unavailable")
        self.assertNotIn("private-provider-key", str(error.exception))
        self.runner.assert_not_called()

    def test_a_credit_observation_is_not_a_spend_reservation(self):
        self.billing.check_entitlement.return_value = {"check": {"kind": "credit", "allowed": True}}
        with self.assertRaises(HostedAccessError):
            self.run_hosted()
        self.runner.assert_not_called()

    def test_incomplete_configuration_fails_before_billing(self):
        with self.assertRaises(HostedAccessError):
            self.run_hosted(access_feature_id="not-configured")
        self.billing.get_or_create_customer.assert_not_called()
        self.runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
