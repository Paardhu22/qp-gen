"""Live end-to-end verification of register → forgot → reset → login.

Run with `python manage.py shell -c "exec(open('scratch/verify_auth_e2e.py').read())"`
against the local dev server (must be listening on http://localhost:8000).

The test proves the auth-store trace: login reads `account.password`, reset
rotates `account.password`. Logging in with the NEW password after reset is
the only way to be sure those two flows touch the same column.

We can't observe the reset email from the running server's stdout, so we
capture the issued token via the service layer (which returns plaintext)
between the HTTP forgot-password call and the HTTP reset-password call.
Every other step uses HTTP.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from apps.accounts.models import Account, User
from services.password_reset_service import issue_reset_token

BASE = "http://localhost:8000"
TS = int(time.time())
EMAIL = f"e2e+{TS}@gmail.com"
INITIAL_PW = "initial-password-1"
NEW_PW = "new-password-after-reset-2"


def _post(path, body):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read() or b"{}")
        except Exception:
            payload = {"_raw": "<unparseable>"}
        return exc.code, payload


def banner(msg):
    print(f"\n=== {msg} ===")


# 1. Register a fresh user via HTTP.
banner("1. POST /api/auth/register")
status, body = _post(
    "/api/auth/register",
    {"name": "E2E Tester", "email": EMAIL, "password": INITIAL_PW},
)
print(f"status={status}")
assert status == 201, f"expected 201, got {status}: {body}"
print(f"user.id={body['user']['id']} email={body['user']['email']}")

# 2. Confirm we can log in with the ORIGINAL password.
banner("2. POST /api/auth/login (original password)")
status, body = _post(
    "/api/auth/login",
    {"email": EMAIL, "password": INITIAL_PW},
)
print(f"status={status}")
assert status == 200, f"expected 200, got {status}: {body}"
assert body["accessToken"], "no accessToken in body"
print("login OK with initial password")

# 3. Request a password reset via HTTP (account-enumeration resistant: always 200).
banner("3. POST /api/auth/forgot-password")
status, body = _post("/api/auth/forgot-password", {"email": EMAIL})
print(f"status={status} body={body}")
assert status == 200, f"expected 200, got {status}: {body}"

# 4. The HTTP response intentionally omits the token. Capture a fresh one via
#    the service layer (which is what the endpoint also uses internally — same
#    Verification row, same hash, same identifier). issue_reset_token deletes
#    any prior token for the same identifier, so the one we get here is the
#    only valid one going forward.
banner("4. capture plaintext reset token via service layer")
user = User.objects.get(email=EMAIL)
token = issue_reset_token(user)
print(f"len(token)={len(token)} (expected 64 hex chars)")
assert len(token) == 64 and all(c in "0123456789abcdef" for c in token)

# 5. Reset the password via HTTP.
banner("5. POST /api/auth/reset-password")
status, body = _post(
    "/api/auth/reset-password",
    {"token": token, "newPassword": NEW_PW},
)
print(f"status={status} body={body}")
assert status == 200, f"expected 200, got {status}: {body}"
assert body.get("success") is True

# 6. Old password must FAIL (this is the test that catches a wrong-store bug).
banner("6. POST /api/auth/login (original password — must FAIL after reset)")
status, body = _post(
    "/api/auth/login",
    {"email": EMAIL, "password": INITIAL_PW},
)
print(f"status={status}")
assert status in (400, 401, 403), (
    f"original password still works after reset! status={status} body={body} "
    "→ reset wrote to a different store than login reads"
)
print("OK: old password rejected after reset")

# 7. New password must WORK.
banner("7. POST /api/auth/login (NEW password — must succeed)")
status, body = _post(
    "/api/auth/login",
    {"email": EMAIL, "password": NEW_PW},
)
print(f"status={status}")
assert status == 200, (
    f"NEW password didn't log in! status={status} body={body} "
    "→ login store and reset store are DIFFERENT"
)
assert body["accessToken"], "no accessToken on second login"
print("OK: login works with new password — reset and login share the same store")

# 8. Sanity-check the storage row to confirm Django PBKDF2 hash format.
banner("8. DB sanity: account.password is a Django PBKDF2 hash")
acc = Account.objects.get(user=user, provider_id="email")
print(f"hash prefix: {acc.password[:35]}…")
assert acc.password.startswith("pbkdf2_sha256$"), (
    f"unexpected hash format: {acc.password[:40]} — Django auth normally writes "
    "pbkdf2_sha256$ from make_password(). If this is a different prefix, a "
    "different hasher (Better Auth, bcrypt, etc.) wrote this row, which would "
    "mean two systems share the column."
)
print("OK: Django PBKDF2 hash confirms make_password() / check_password() path")

# 9. Cleanup so the test is rerunnable.
banner("9. cleanup")
user.delete()  # cascades to Account + any Verification rows we left
print(f"deleted test user {EMAIL}")

print("\nALL ASSERTIONS PASSED — auth-store is unified.")
