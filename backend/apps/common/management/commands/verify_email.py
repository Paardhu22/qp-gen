"""Prove the configured mail provider will actually accept our messages.

Every notification in this codebase is best-effort by design — `_safe_send` in
services/email_service.py logs a failure and lets the request succeed, because
an SMTP outage must never leave a membership half-applied with the Cognito
group already moved. The cost of that choice is that a misconfigured provider
is invisible: approvals appear to work and no mail ever arrives.

This command is the antidote. It fails loudly, with the provider's own error
text, so the cause is named rather than guessed at.
"""

from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.core.management.base import BaseCommand, CommandError

#: Provider rejections that mean something specific and actionable. Brevo's
#: wording is matched loosely because the code (525/530) is the reliable part.
KNOWN_FAILURES = [
    (
        ("unauthorized ip", "5.7.1"),
        "Brevo is refusing this machine's IP address.\n"
        "    Fix: Brevo dashboard → SMTP & API → Authorized IPs. Add this host's\n"
        "    public IP, or turn IP restriction off. Every sender needs listing —\n"
        "    your laptop and the EC2 elastic IP are different addresses.",
    ),
    (
        ("authentication failed", "535"),
        "The login or SMTP key was rejected.\n"
        "    Fix: EMAIL_HOST_USER is the Brevo login (…@smtp-brevo.com), not the\n"
        "    from-address, and EMAIL_HOST_PASSWORD is the SMTP key (xsmtpsib-…),\n"
        "    which is NOT the REST API key.",
    ),
    (
        ("sender", "not valid", "unrecognized"),
        "The provider rejected the from-address.\n"
        f"    Fix: verify {settings.DEFAULT_FROM_EMAIL!r} as a sender with your\n"
        "    provider, or send from a domain you have authenticated with them.",
    ),
]


class Command(BaseCommand):
    help = "Check the mail configuration, and optionally send a real test message."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            help=(
                "Send a real test message to this address. Omit to only open and "
                "authenticate the connection, which delivers nothing."
            ),
        )

    def handle(self, *args, **options):
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f"backend : {backend}")
        self.stdout.write(f"host    : {settings.EMAIL_HOST}:{settings.EMAIL_PORT} (TLS={settings.EMAIL_USE_TLS})")
        self.stdout.write(f"login   : {settings.EMAIL_HOST_USER or '(none)'}")
        self.stdout.write(f"from    : {settings.DEFAULT_FROM_EMAIL}")

        if any(k in backend.lower() for k in ("console", "dummy", "locmem")):
            # Not an error — it is the right local default. But it is the single
            # most common reason "no email arrives", so say so plainly.
            self.stdout.write(
                self.style.WARNING(
                    "\nThis backend does not deliver anything. Messages print to the "
                    "server log instead.\nSet EMAIL_BACKEND to "
                    "django.core.mail.backends.smtp.EmailBackend to send for real."
                )
            )
            return

        try:
            connection = get_connection(fail_silently=False)
            connection.open()
            connection.close()
        except Exception as exc:
            raise CommandError(self._explain("Could not authenticate", exc)) from exc

        self.stdout.write(self.style.SUCCESS("\nSMTP authentication OK."))

        to = options.get("to")
        if not to:
            self.stdout.write("Nothing sent. Pass --to <address> to deliver a test message.")
            return

        try:
            send_mail(
                subject="qp-gen mail check",
                message=(
                    "This is a test message from qp-gen.\n\n"
                    "If you are reading it, invites, approvals, rejections and role "
                    "changes will reach their recipients too.\n\n— qp-gen\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(self._explain(f"Accepted the login but refused the message to {to}", exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Test message accepted for delivery to {to}."))

    @staticmethod
    def _explain(headline: str, exc: Exception) -> str:
        """Attach the actionable fix when the provider's error names a known cause."""
        raw = str(exc)
        text = f"{headline}: {raw}"
        haystack = raw.lower()
        for needles, advice in KNOWN_FAILURES:
            if any(needle in haystack for needle in needles):
                return f"{text}\n\n    {advice}"
        return text
