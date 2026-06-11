"use client";

const COGNITO_REGION = process.env.NEXT_PUBLIC_AWS_COGNITO_REGION || "ap-south-1";
// NO hard-coded fallback. The previous literal had an ℓ/1 typo
// ("…occdoLk7ivf" vs the console's "…occdo1k7ivf") that silently shipped a wrong
// client ID. This MUST be a *public* app client with NO client secret (Path A —
// a secret can't be protected in a browser); see FIX_REPORT.md → ACTION REQUIRED.
const COGNITO_CLIENT_ID = process.env.NEXT_PUBLIC_AWS_COGNITO_APP_CLIENT_ID || "";
const COGNITO_ENDPOINT = `https://cognito-idp.${COGNITO_REGION}.amazonaws.com/`;

async function callCognito(action: string, payload: Record<string, any>) {
  if (!COGNITO_CLIENT_ID) {
    throw new Error(
      "Auth is not configured: NEXT_PUBLIC_AWS_COGNITO_APP_CLIENT_ID is missing. " +
        "Set it to your public (no-secret) Cognito app client ID.",
    );
  }
  const response = await fetch(COGNITO_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": `AWSCognitoIdentityProviderService.${action}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const message = errorBody?.message || errorBody?.Message || `Cognito operation ${action} failed.`;
    throw new Error(message);
  }

  return response.json();
}

// The user pool enables BOTH "User name" and "Email" sign-in (email is an
// ALIAS), so a SignUp `Username` must NOT be in email format. Derive a
// deterministic, non-email username from the email. Determinism matters:
// ConfirmSignUp / ResendConfirmationCode run BEFORE the account is confirmed, and
// the email alias is only attached to the user AFTER confirmation — so those
// pre-confirmation calls must address the user by THIS generated username, not
// the email. Sign-in / ForgotPassword happen post-confirmation and use the email
// alias directly. trim+lowercase keeps the value identical across the signup→
// confirm→resend steps regardless of how the user typed their email.
function usernameFromEmail(email: string): string {
  return email.trim().toLowerCase().replace(/@/g, "_").replace(/\./g, "_");
}

export interface CognitoTokens {
  AccessToken: string;
  IdToken: string;
  RefreshToken?: string;
  ExpiresIn: number;
}

export async function cognitoSignIn(email: string, password: string): Promise<CognitoTokens> {
  const data = await callCognito("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: COGNITO_CLIENT_ID,
    AuthParameters: {
      // Users type their email; post-confirmation it's an active sign-in alias,
      // so pass it straight through as USERNAME (no transform).
      USERNAME: email,
      PASSWORD: password,
    },
  });

  if (!data.AuthenticationResult) {
    if (data.ChallengeName === "NEW_PASSWORD_REQUIRED") {
      throw new Error("Password reset or verification is required on your account.");
    }
    throw new Error("Invalid credentials or authentication challenge encountered.");
  }

  return data.AuthenticationResult;
}

export interface CognitoSignUpResult {
  UserConfirmed: boolean;
  UserSub: string;
  CodeDeliveryDetails?: {
    Destination?: string;
    DeliveryMedium?: string;
    AttributeName?: string;
  };
}

export async function cognitoSignUp(
  email: string,
  password: string,
  name: string,
): Promise<CognitoSignUpResult> {
  return callCognito("SignUp", {
    ClientId: COGNITO_CLIENT_ID,
    // Username can't be email-format (pool uses email as an alias). The email is
    // passed as an attribute and becomes the sign-in alias after confirmation.
    Username: usernameFromEmail(email),
    Password: password,
    UserAttributes: [
      { Name: "email", Value: email },
      { Name: "name", Value: name },
    ],
  });
}

// Confirm a freshly-signed-up account with the emailed verification code.
// Required whenever the pool has email verification ON (the Cognito default) —
// without it the new user stays UNCONFIRMED and InitiateAuth throws
// UserNotConfirmedException.
export async function cognitoConfirmSignUp(email: string, code: string): Promise<any> {
  return callCognito("ConfirmSignUp", {
    ClientId: COGNITO_CLIENT_ID,
    // Pre-confirmation: the email alias isn't attached yet, so address the user
    // by the same generated username SignUp created.
    Username: usernameFromEmail(email),
    ConfirmationCode: code,
  });
}

export async function cognitoResendConfirmationCode(email: string): Promise<any> {
  return callCognito("ResendConfirmationCode", {
    ClientId: COGNITO_CLIENT_ID,
    // Pre-confirmation too — use the generated username, not the email alias.
    Username: usernameFromEmail(email),
  });
}

export async function cognitoRefreshToken(refreshToken: string): Promise<CognitoTokens> {
  const data = await callCognito("InitiateAuth", {
    AuthFlow: "REFRESH_TOKEN_AUTH",
    ClientId: COGNITO_CLIENT_ID,
    AuthParameters: {
      REFRESH_TOKEN: refreshToken,
    },
  });

  if (!data.AuthenticationResult) {
    throw new Error("Failed to refresh token.");
  }

  return data.AuthenticationResult;
}

export async function cognitoForgotPassword(email: string): Promise<any> {
  return callCognito("ForgotPassword", {
    ClientId: COGNITO_CLIENT_ID,
    // Reset targets a CONFIRMED account, so the email alias resolves — use it
    // directly (don't convert to the generated username).
    Username: email,
  });
}

export async function cognitoConfirmForgotPassword(email: string, code: string, password: string): Promise<any> {
  return callCognito("ConfirmForgotPassword", {
    ClientId: COGNITO_CLIENT_ID,
    // Confirmed account → email alias resolves; use it directly.
    Username: email,
    ConfirmationCode: code,
    Password: password,
  });
}

export async function cognitoChangePassword(accessToken: string, oldPassword: string, newPassword: string): Promise<any> {
  return callCognito("ChangePassword", {
    AccessToken: accessToken,
    PreviousPassword: oldPassword,
    ProposedPassword: newPassword,
  });
}

export async function cognitoSignOut(accessToken: string): Promise<any> {
  try {
    return await callCognito("GlobalSignOut", {
      AccessToken: accessToken,
    });
  } catch (e) {
    console.warn("Cognito Global Sign Out warning:", e);
  }
}
