import logging
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.models import User
from services.cognito_service import CognitoTokenValidator, get_user_info_from_cognito

logger = logging.getLogger("[COGNITO_AUTHENTICATION]")

class CognitoJWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def __init__(self):
        super().__init__()
        self.validator = CognitoTokenValidator()

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth:
            return None

        if auth[0].decode().lower() != self.keyword.lower():
            return None

        if len(auth) != 2:
            raise AuthenticationFailed("Invalid Authorization header format. Must be Bearer <token>")

        token = auth[1].decode()

        # Validate token and extract claims
        payload = self.validator.validate_token(token)

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationFailed("Token is missing sub claim.")

        # Cognito sub is a 36-char UUID. Strip hyphens to fit local User.id (32 chars)
        user_id = sub.replace("-", "")

        # Extract groups to determine status: admin > approved > pending
        groups = payload.get("cognito:groups", [])
        if not isinstance(groups, list):
            groups = [groups]

        if "admin" in groups:
            status = "admin"
        elif "approved" in groups:
            status = "approved"
        else:
            status = "pending"

        is_superadmin = "superadmin" in groups

        try:
            user = User.objects.filter(id=user_id).first()
            if not user:
                # User does not exist locally. Retrieve details from token or query Cognito
                token_use = payload.get("token_use")
                email = payload.get("email")
                name = payload.get("name") or payload.get("given_name")

                if not email:
                    if token_use == "access":
                        # If it's an access token, fetch user info from Cognito user pool API
                        user_info = get_user_info_from_cognito(token)
                        email = user_info.get("email")
                        name = user_info.get("name")
                    else:
                        # Fallback if email is somehow missing from ID token
                        username = payload.get("cognito:username") or payload.get("username") or "user"
                        email = f"{username}@example.com"
                        name = username

                if not name:
                    name = email.split("@")[0] if email else "User"

                # Create the user profile locally
                user = User.objects.create(
                    id=user_id,
                    email=email,
                    name=name,
                    status=status,
                    is_superadmin=is_superadmin,
                )
                logger.info("Created local user profile for user %s (%s) with status %s", user.email, user.id, status)
            else:
                # User exists locally. Sync fields if they changed.
                email = payload.get("email")
                name = payload.get("name") or payload.get("given_name")
                
                # Check for updates from token claims
                updated_fields = []
                if email and user.email != email:
                    user.email = email
                    updated_fields.append("email")
                if name and user.name != name:
                    user.name = name
                    updated_fields.append("name")
                if user.status != status:
                    # Sync Cognito group status to local DB
                    user.status = status
                    updated_fields.append("status")
                if user.is_superadmin != is_superadmin:
                    user.is_superadmin = is_superadmin
                    updated_fields.append("is_superadmin")

                if updated_fields:
                    user.save(update_fields=updated_fields)
                    logger.info("Synchronized user %s (%s) fields: %s", user.email, user.id, updated_fields)

            return (user, None)

        except Exception as e:
            logger.error("Error creating/syncing user during auth: %s", e)
            raise AuthenticationFailed(f"User synchronization failed: {str(e)}")

    def authenticate_header(self, request) -> str:
        return self.keyword
