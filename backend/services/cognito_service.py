import logging
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
                options={"verify_aud": False}
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
