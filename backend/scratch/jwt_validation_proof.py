"""Standalone proof that CognitoTokenValidator verifies RS256 signatures and
rejects forged / expired / tampered / wrong-audience / wrong-issuer tokens.

Run:  ./venv/bin/python scratch/jwt_validation_proof.py
Generates a throwaway RSA key, feeds its public JWK to the validator (mocking
only the network JWKS fetch), and signs test tokens. No AWS, no DB.
"""
import os
import django
import json
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from services.cognito_service import CognitoTokenValidator

REGION = settings.AWS_COGNITO_REGION
POOL = settings.AWS_COGNITO_USER_POOL_ID
CLIENT_ID = "proof-client-id-123"
ISS = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}"
KID = "proof-kid"

# Pin the client_id the validator checks against (settings default is now empty).
settings.AWS_COGNITO_APP_CLIENT_ID = CLIENT_ID

# A legitimate key (the "pool" key) and an attacker key (forgery).
good_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
evil_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_jwks(private_key, kid=KID):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


# Validator that returns OUR JWKS (built from the good public key) — this is the
# only thing mocked; signature/iss/aud/exp logic is the real code under test.
validator = CognitoTokenValidator()
validator.get_jwks = lambda: public_jwks(good_key)


def sign(private_key, claims, kid=KID):
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


now = int(time.time())
base = {"sub": "abc-123", "iss": ISS, "token_use": "id", "aud": CLIENT_ID, "email": "a@b.com", "exp": now + 3600, "iat": now}

results = []


def check(name, fn, expect_ok):
    try:
        fn()
        results.append((name, "ACCEPTED", expect_ok is True))
    except (AuthenticationFailed, Exception) as e:
        results.append((name, f"REJECTED ({type(e).__name__})", expect_ok is False))


# 1. Valid ID token → accepted
check("valid ID token", lambda: validator.validate_token(sign(good_key, base)), True)
# 2. Valid access token (client_id claim) → accepted
acc = {**base, "token_use": "access", "client_id": CLIENT_ID}
acc.pop("aud")
check("valid access token", lambda: validator.validate_token(sign(good_key, acc)), True)
# 3. Expired token → rejected
check("expired token", lambda: validator.validate_token(sign(good_key, {**base, "exp": now - 10})), False)
# 4. Forged signature (attacker key, same kid) → rejected
check("forged (wrong signing key)", lambda: validator.validate_token(sign(evil_key, base)), False)
# 5. Tampered token (flip a char in the signature) → rejected
def tampered():
    t = sign(good_key, base)
    head, payload, sig = t.split(".")
    bad = sig[:-2] + ("aa" if sig[-2:] != "aa" else "bb")
    return validator.validate_token(f"{head}.{payload}.{bad}")
check("tampered signature", tampered, False)
# 6. Wrong issuer → rejected
check("wrong issuer", lambda: validator.validate_token(sign(good_key, {**base, "iss": "https://evil.example.com"})), False)
# 7. Wrong audience (other client) → rejected
check("wrong audience", lambda: validator.validate_token(sign(good_key, {**base, "aud": "some-other-client"})), False)
# 8. Garbage token → rejected
check("garbage token", lambda: validator.validate_token("not.a.jwt"), False)
# 9. alg=none / unsigned → rejected
def alg_none():
    t = jwt.encode(base, key="", algorithm="none")
    return validator.validate_token(t)
check("alg=none unsigned", alg_none, False)

print("\n=== JWT validation proof ===")
all_pass = True
for name, outcome, ok in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name:32} -> {outcome}")
    all_pass = all_pass and ok
print("=== " + ("ALL EXPECTATIONS MET" if all_pass else "SOME EXPECTATIONS FAILED") + " ===")
raise SystemExit(0 if all_pass else 1)
