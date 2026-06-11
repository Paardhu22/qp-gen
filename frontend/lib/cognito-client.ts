"use client";

const COGNITO_REGION = process.env.NEXT_PUBLIC_AWS_COGNITO_REGION || "ap-south-1";
const COGNITO_CLIENT_ID = process.env.NEXT_PUBLIC_AWS_COGNITO_APP_CLIENT_ID || "3haedrtub40tv44occdolk7ivf";
const COGNITO_ENDPOINT = `https://cognito-idp.${COGNITO_REGION}.amazonaws.com/`;

async function callCognito(action: string, payload: Record<string, any>) {
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

export async function cognitoSignUp(email: string, password: string, name: string): Promise<any> {
  return callCognito("SignUp", {
    ClientId: COGNITO_CLIENT_ID,
    Username: email,
    Password: password,
    UserAttributes: [
      { Name: "email", Value: email },
      { Name: "name", Value: name },
    ],
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
    Username: email,
  });
}

export async function cognitoConfirmForgotPassword(email: string, code: string, password: string): Promise<any> {
  return callCognito("ConfirmForgotPassword", {
    ClientId: COGNITO_CLIENT_ID,
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
