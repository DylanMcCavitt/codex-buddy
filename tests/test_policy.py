import unittest

from codex_buddy_bridge.policy import (
    ApprovalPrompt,
    HardwareApprovalPolicy,
    PolicyConfig,
    PolicyOutcome,
    PromptKind,
)


class HardwareApprovalPolicyTests(unittest.TestCase):
    def test_deny_is_allowed_for_active_prompt_by_default(self):
        policy = HardwareApprovalPolicy()
        prompt = ApprovalPrompt(prompt_id="request-1", kind=PromptKind.COMMAND, command="rm -rf /tmp/x")

        result = policy.evaluate(prompt_id="request-1", decision="deny", active_prompt=prompt)

        self.assertEqual(result.outcome, PolicyOutcome.ALLOW_DENY)
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "deny_allowed_by_default")

    def test_approve_is_rejected_by_default_even_for_read_only_command(self):
        policy = HardwareApprovalPolicy()
        prompt = ApprovalPrompt(prompt_id="request-1", kind=PromptKind.COMMAND, command="git status --short")

        result = policy.evaluate(prompt_id="request-1", decision="accept", active_prompt=prompt)

        self.assertEqual(result.outcome, PolicyOutcome.REJECT_HARDWARE_APPROVE)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "hardware_approve_disabled")

    def test_approve_is_allowed_for_read_only_command_when_enabled(self):
        policy = HardwareApprovalPolicy(PolicyConfig(hardware_approve_enabled=True))
        prompt = ApprovalPrompt(prompt_id="request-1", kind=PromptKind.COMMAND, command="git status --short")

        result = policy.evaluate(prompt_id="request-1", decision="once", active_prompt=prompt)

        self.assertEqual(result.outcome, PolicyOutcome.ALLOW_APPROVE)
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "command_allowlisted")

    def test_configured_test_command_can_be_allowlisted(self):
        policy = HardwareApprovalPolicy(
            PolicyConfig(
                hardware_approve_enabled=True,
                allowed_command_prefixes=(("python3", "-m", "unittest"),),
            )
        )
        prompt = ApprovalPrompt(
            prompt_id="request-1",
            kind=PromptKind.COMMAND,
            command="python3 -m unittest discover -s tests -v",
        )

        result = policy.evaluate(prompt_id="request-1", decision="approve", active_prompt=prompt)

        self.assertEqual(result.outcome, PolicyOutcome.ALLOW_APPROVE)

    def test_high_risk_command_is_rejected_even_when_enabled(self):
        policy = HardwareApprovalPolicy(
            PolicyConfig(
                hardware_approve_enabled=True,
                allowed_command_prefixes=(("rm",), ("sed",), ("git", "status")),
            )
        )
        destructive = ApprovalPrompt(prompt_id="request-1", kind=PromptKind.COMMAND, command="rm -rf build")
        sed_in_place = ApprovalPrompt(prompt_id="request-2", kind=PromptKind.COMMAND, command="sed -i s/a/b/ file")

        result = policy.evaluate(prompt_id="request-1", decision="accept", active_prompt=destructive)
        sed_result = policy.evaluate(prompt_id="request-2", decision="accept", active_prompt=sed_in_place)

        self.assertEqual(result.outcome, PolicyOutcome.REJECT_HARDWARE_APPROVE)
        self.assertEqual(result.reason, "command_not_allowlisted")
        self.assertEqual(sed_result.outcome, PolicyOutcome.REJECT_HARDWARE_APPROVE)

    def test_stale_id_and_unknown_decision_are_ignored(self):
        policy = HardwareApprovalPolicy()
        prompt = ApprovalPrompt(prompt_id="request-1", kind=PromptKind.COMMAND, command="pwd")

        stale = policy.evaluate(prompt_id="old-request", decision="deny", active_prompt=prompt)
        unknown = policy.evaluate(prompt_id="request-1", decision="ship-it", active_prompt=prompt)

        self.assertEqual(stale.outcome, PolicyOutcome.IGNORE_STALE_OR_UNKNOWN_PROMPT)
        self.assertEqual(stale.reason, "stale_or_unknown_prompt")
        self.assertEqual(unknown.outcome, PolicyOutcome.IGNORE_STALE_OR_UNKNOWN_PROMPT)
        self.assertEqual(unknown.reason, "unknown_decision")

    def test_decision_log_is_sanitized(self):
        policy = HardwareApprovalPolicy(PolicyConfig(hardware_approve_enabled=True))
        prompt = ApprovalPrompt(
            prompt_id="secret-request-id",
            kind=PromptKind.COMMAND,
            command="git status --short /Users/dylanmccavitt/private",
        )

        result = policy.evaluate(prompt_id="secret-request-id", decision="accept", active_prompt=prompt)
        log_entry = result.log_entry.to_dict()

        self.assertIn("timestamp", log_entry)
        self.assertEqual(log_entry["prompt_kind"], "command")
        self.assertEqual(log_entry["decision"], "accept")
        self.assertNotIn("secret-request-id", str(log_entry))
        self.assertNotIn("/Users/dylanmccavitt/private", str(log_entry))
        self.assertNotIn("git status", str(log_entry))
        self.assertEqual(policy.decision_log.entries(), [log_entry])

    def test_env_config_enables_approve_and_extra_commands(self):
        config = PolicyConfig.from_env(
            {
                "CODEX_BUDDY_HARDWARE_APPROVE": "1",
                "CODEX_BUDDY_APPROVE_COMMANDS": "python3 -m unittest",
            }
        )
        policy = HardwareApprovalPolicy(config)
        prompt = ApprovalPrompt(
            prompt_id="request-1",
            kind=PromptKind.COMMAND,
            command="python3 -m unittest discover -s tests",
        )

        result = policy.evaluate(prompt_id="request-1", decision="accept", active_prompt=prompt)

        self.assertEqual(result.outcome, PolicyOutcome.ALLOW_APPROVE)


if __name__ == "__main__":
    unittest.main()
