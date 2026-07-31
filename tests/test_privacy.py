import ast
import io
import json
import os
import re
import smtplib
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import notify


class NotificationPrivacyTests(unittest.TestCase):
    def test_success_log_does_not_disclose_credentials(self):
        address = "owner@example.invalid"
        app_password = "private-app-password"
        data = {
            "current": {},
            "assessment": {
                "riskScore": 50,
                "outlook7d": {"label": "neutral", "detail": "neutral"},
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "metrics.json"
            state_path = Path(temp_dir) / "notification-state.json"
            data_path.write_text(json.dumps(data), encoding="utf-8")
            output = io.StringIO()

            with ExitStack() as stack:
                stack.enter_context(patch.object(notify, "DATA_PATH", data_path))
                stack.enter_context(patch.object(notify, "STATE_PATH", state_path))
                stack.enter_context(
                    patch.object(sys, "argv", ["notify.py", "--mode", "test"])
                )
                stack.enter_context(
                    patch.dict(
                        os.environ,
                        {
                            "GMAIL_ADDRESS": address,
                            "GMAIL_APP_PASSWORD": app_password,
                        },
                        clear=False,
                    )
                )
                send_email = stack.enter_context(patch.object(notify, "send_email"))
                stack.enter_context(redirect_stdout(output))
                notify.main()

        send_email.assert_called_once()
        self.assertNotIn(address, output.getvalue())
        self.assertNotIn(app_password, output.getvalue())
        self.assertEqual(output.getvalue().strip(), "Sent test email")

    def test_smtp_failure_exposes_only_a_generic_error(self):
        address = "owner@example.invalid"
        app_password = "private-app-password"
        smtp = MagicMock()
        smtp.login.side_effect = smtplib.SMTPRecipientsRefused(
            {address: (550, b"recipient refused")}
        )
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp

        with patch.object(notify.smtplib, "SMTP_SSL", return_value=smtp_context):
            with self.assertRaises(RuntimeError) as raised:
                notify.send_email(address, app_password, "subject", "text", "<p>html</p>")

        message = str(raised.exception)
        self.assertEqual(
            message,
            "Email delivery failed; check the Gmail Actions secrets and account settings",
        )
        self.assertNotIn(address, message)
        self.assertNotIn(app_password, message)
        self.assertTrue(raised.exception.__suppress_context__)


class RepositoryPrivacyTests(unittest.TestCase):
    def test_repository_contains_only_documented_non_personal_addresses(self):
        email_pattern = re.compile(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            re.IGNORECASE,
        )
        allowed = {
            "lfcx-epoch-bot@users.noreply.github.com",
            "owner@example.invalid",
        }
        ignored_parts = {".git", "__pycache__"}

        for path in ROOT.rglob("*"):
            if not path.is_file() or ignored_parts.intersection(path.parts):
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            addresses = set(email_pattern.findall(content))
            self.assertFalse(addresses - allowed, str(path))

    def test_notification_code_never_prints_credential_variables(self):
        source = (ROOT / "scripts" / "notify.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        sensitive_names = {"address", "app_password"}

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "print":
                continue
            printed_names = {
                child.id for child in ast.walk(node) if isinstance(child, ast.Name)
            }
            self.assertFalse(sensitive_names.intersection(printed_names), node.lineno)

    def test_workflow_secrets_are_scoped_to_the_email_step(self):
        workflow = (ROOT / ".github" / "workflows" / "monitor.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(workflow.count("secrets.GMAIL_ADDRESS"), 1)
        self.assertEqual(workflow.count("secrets.GMAIL_APP_PASSWORD"), 1)
        self.assertNotIn("echo $GMAIL", workflow)
        self.assertNotIn("printenv", workflow)


if __name__ == "__main__":
    unittest.main()
