
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils.html import escape


class PasswordResetEmailTemplateTests(SimpleTestCase):
    def setUp(self):
        self.reset_url = (
            "http://localhost:5173/reset-password/"
            "?uid=123&token=test-token"
        )
        self.context = {
            "user": type(
                "User",
                (),
                {"first_name": "Brenda"},
            )(),
            "reset_url": self.reset_url,
        }

    def test_html_template_renders_branding_and_reset_link(self):
        html = render_to_string(
            "accounts/emails/password_reset.html",
            self.context,
        )

        self.assertIn("Pawdigree", html)
        self.assertIn("Reset my password", html)
        self.assertIn(escape(self.reset_url), html)
        self.assertIn("#216C68", html)
        self.assertIn("Brenda", html)

    def test_plain_text_template_renders_reset_link(self):
        text = render_to_string(
            "accounts/emails/password_reset.txt",
            self.context,
        )

        self.assertIn("Pawdigree", text)
        self.assertIn(self.reset_url, text)
        self.assertIn("Brenda", text)
        self.assertIn("do not share this link", text.lower())
