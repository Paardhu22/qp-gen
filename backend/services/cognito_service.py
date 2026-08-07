import logging
import uuid
import jwt
import httpx
from django.core.cache import cache
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
import boto3

logger = logging.getLogger("[COGNITO_SERVICE]")

def get_cognito_client():
    return boto3.client(
        "cognito-idp",
        region_name=settings.AWS_COGNITO_REGION,
        aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
        aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
    )

class CognitoTokenValidator:
    def __init__(self):
        self.region = settings.AWS_COGNITO_REGION
        self.user_pool_id = settings.AWS_COGNITO_USER_POOL_ID
        self.client_id = settings.AWS_COGNITO_APP_CLIENT_ID
        self.iss = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
        self.jwks_url = f"{self.iss}/.well-known/jwks.json"

    def get_jwks(self) -> dict:
        cache_key = "cognito_jwks"
        jwks = cache.get(cache_key)
        if not jwks:
            try:
                # Use httpx which is in requirements.txt
                response = httpx.get(self.jwks_url, timeout=10.0)
                response.raise_for_status()
                jwks = response.json()
                cache.set(cache_key, jwks, timeout=86400) # Cache keys for 24 hours
            except Exception as e:
                logger.error("Failed to fetch JWKS from Cognito: %s", e)
                raise AuthenticationFailed(f"Failed to fetch JWKS from Cognito: {str(e)}")
        return jwks

    def validate_token(self, token: str) -> dict:
        try:
            # Decode header without verification to extract kid
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                raise AuthenticationFailed("Token is missing kid header.")

            # Find key in JWKS
            jwks = self.get_jwks()
            public_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    # Construct public key using cryptography RSA algorithm
                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                    break

            if not public_key:
                raise AuthenticationFailed("Public key not found in JWKS.")

            # Decode and verify token using the public key.
            # PyJWT will verify signature and expiration automatically.
            # We disable audience verification here so we can support both ID tokens and Access tokens manually.
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False},
                leeway=60
            )

            # Validate issuer
            if payload.get("iss") != self.iss:
                raise AuthenticationFailed("Token issuer is invalid.")

            # Validate token usage
            token_use = payload.get("token_use")
            if token_use not in ["access", "id"]:
                raise AuthenticationFailed("Token token_use claim must be 'access' or 'id'.")

            # Validate audience / client ID
            if token_use == "id":
                if payload.get("aud") != self.client_id:
                    raise AuthenticationFailed("ID Token audience is invalid.")
            else: # access token
                if payload.get("client_id") != self.client_id:
                    raise AuthenticationFailed("Access Token client_id is invalid.")

            return payload

        except jwt.ExpiredSignatureError as e:
            raise AuthenticationFailed("Token has expired.") from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed(f"Invalid token: {str(e)}") from e
        except Exception as e:
            raise AuthenticationFailed(f"Token verification failed: {str(e)}") from e

def get_user_info_from_cognito(access_token: str) -> dict:
    """
    Fetch user attributes (email, name) using the Cognito access token.
    """
    try:
        client = get_cognito_client()
        response = client.get_user(AccessToken=access_token)
        user_attrs = {}
        for attr in response.get("UserAttributes", []):
            user_attrs[attr["Name"]] = attr["Value"]
        return {
            "email": user_attrs.get("email"),
            "name": user_attrs.get("name") or user_attrs.get("given_name") or response.get("Username"),
        }
    except Exception as e:
        logger.error("Failed to fetch user info from Cognito: %s", e)
        raise AuthenticationFailed(f"Could not retrieve user details from Cognito: {str(e)}")

def add_user_to_group(username: str, group_name: str):
    client = get_cognito_client()
    try:
        client.admin_add_user_to_group(
            UserPoolId=settings.AWS_COGNITO_USER_POOL_ID,
            Username=username,
            GroupName=group_name
        )
    except Exception as e:
        logger.error("Failed to add user %s to group %s: %s", username, group_name, e)
        raise RuntimeError(f"Failed to add user to Cognito group: {str(e)}")

def remove_user_from_group(username: str, group_name: str):
    client = get_cognito_client()
    try:
        client.admin_remove_user_from_group(
            UserPoolId=settings.AWS_COGNITO_USER_POOL_ID,
            Username=username,
            GroupName=group_name
        )
    except client.exceptions.UserNotFoundException:
        pass # ignore if user doesn't exist in group
    except Exception as e:
        logger.error("Failed to remove user %s from group %s: %s", username, group_name, e)
        raise RuntimeError(f"Failed to remove user from Cognito group: {str(e)}")


def ensure_cognito_group(group_name: str, description: str = ""):
    """Create a Cognito group if it doesn't already exist. Idempotent."""
    client = get_cognito_client()
    try:
        client.create_group(
            GroupName=group_name,
            UserPoolId=settings.AWS_COGNITO_USER_POOL_ID,
            Description=description,
        )
    except client.exceptions.GroupExistsException:
        pass
    except Exception as e:
        logger.error("Failed to ensure Cognito group %s: %s", group_name, e)
        raise RuntimeError(f"Failed to ensure Cognito group: {str(e)}")


def get_cognito_user_by_email(email: str) -> dict | None:
    """Return the Cognito user record for `email`, or None if it doesn't exist."""
    client = get_cognito_client()
    try:
        response = client.admin_get_user(
            UserPoolId=settings.AWS_COGNITO_USER_POOL_ID,
            Username=email,
        )
        return response
    except client.exceptions.UserNotFoundException:
        return None
    except Exception as e:
        logger.error("Failed to look up Cognito user %s: %s", email, e)
        raise RuntimeError(f"Failed to look up Cognito user: {str(e)}")


def _extract_sub(user_attributes: list[dict]) -> str | None:
    """Pull the `sub` claim out of a Cognito UserAttributes list."""
    for attr in user_attributes or []:
        if attr.get("Name") == "sub":
            return attr.get("Value")
    return None


def create_cognito_user(email: str, name: str, password: str) -> str:
    """
    Create a permanently-active Cognito user (no invite email, no forced
    first-login reset) and return the user's `sub`.

    The pool is configured with email as an ALIAS attribute, which makes
    `Username=<an email address>` illegal — admin_create_user rejects it with
    InvalidParameterException ("Username cannot be of email format, since user
    pool is configured for email alias"). So we mint an opaque UUID as the
    Username and carry the real address in the `email` attribute; the alias
    still lets the user sign in with their email.

    We return `sub`, not the Username we generated. Callers key their local
    User row off this (seed_superadmin), and authentication.py derives the same
    id from the token's `sub` claim — Cognito assigns `sub` independently of
    the Username, so returning the Username would leave the two out of sync.
    Admin APIs accept a `sub` in their `Username` parameter, so it stays usable
    for add_user_to_group and friends.
    """
    client = get_cognito_client()
    username = str(uuid.uuid4())
    try:
        create_response = client.admin_create_user(
            UserPoolId=settings.AWS_COGNITO_USER_POOL_ID,
            Username=username,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": name},
            ],
            MessageAction="SUPPRESS",
        )
    except client.exceptions.UsernameExistsException:
        # Either our UUID collided (vanishingly unlikely) or the email alias is
        # already taken by an existing user. Fall back to the lookup so a repeat
        # call behaves like the idempotent "already exists" path callers expect.
        existing = get_cognito_user_by_email(email)
        if existing:
            sub = _extract_sub(existing.get("UserAttributes", []))
            if sub:
                logger.info("Cognito user %s already exists; reusing sub %s", email, sub)
                return sub
        logger.error("Cognito reported %s as existing but it could not be looked up", email)
        raise RuntimeError(f"Failed to create Cognito user: {email} already exists")
    except Exception as e:
        logger.error("Failed to create Cognito user %s: %s", email, e)
        raise RuntimeError(f"Failed to create Cognito user: {str(e)}")

    sub = _extract_sub(create_response.get("User", {}).get("Attributes", []))
    if not sub:
        logger.error("Cognito did not return a sub for newly created user %s", email)
        raise RuntimeError("Failed to create Cognito user: no sub returned")

    try:
        client.admin_set_user_password(
            UserPoolId=settings.AWS_COGNITO_USER_POOL_ID,
            Username=username,
            Password=password,
            Permanent=True,
        )
    except Exception as e:
        logger.error("Failed to set password for Cognito user %s: %s", email, e)
        raise RuntimeError(f"Failed to set Cognito user password: {str(e)}")

    return sub
