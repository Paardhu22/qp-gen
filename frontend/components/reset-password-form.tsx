"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { cn } from "@/lib/utils";
import { resetPassword } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff } from "lucide-react";

const CODE_REGEX = /^\d{6}$/;
// Cognito pool policy: minimum 8 characters with at least one number. Mirror it
// client-side so the user gets instant feedback instead of a round-trip
// InvalidPasswordException.
const HAS_NUMBER_REGEX = /\d/;

// Map Cognito ConfirmForgotPassword exception types (surfaced as `error.name`
// → returned as `code`) to human-readable messages.
function friendlyError(code: string | undefined, fallback: string): string {
  switch (code) {
    case "CodeMismatchException":
      return "Incorrect code. Please check your email and try again.";
    case "ExpiredCodeException":
      return "This code has expired. Please request a new one.";
    case "InvalidPasswordException":
      return "Password doesn't meet requirements. Use at least 8 characters including a number.";
    case "LimitExceededException":
      return "Too many attempts. Please wait a few minutes and try again.";
    case "UserNotFoundException":
      return "No account found with this email.";
    default:
      return fallback || "Something went wrong. Please try again.";
  }
}

export function ResetPasswordForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");
  // When the code has expired, surface a shortcut back to /forgot-password so
  // the user can request a fresh one.
  const [codeExpired, setCodeExpired] = useState(false);

  // Pre-fill the email from ?email=... (the forgot-password page passes it),
  // but keep the field editable.
  useEffect(() => {
    const fromQuery = searchParams.get("email");
    if (fromQuery) setEmail(fromQuery);
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setCodeExpired(false);

    const trimmedEmail = email.trim();
    const trimmedCode = code.trim();

    if (!trimmedEmail || !trimmedCode || !password || !confirmPassword) {
      setError("Please fill in all fields.");
      return;
    }
    if (!CODE_REGEX.test(trimmedCode)) {
      setError("The verification code must be 6 digits.");
      return;
    }
    if (password.length < 8 || !HAS_NUMBER_REGEX.test(password)) {
      setError("Password must be at least 8 characters and include a number.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    const result = await resetPassword(trimmedEmail, trimmedCode, password);
    setLoading(false);

    if (!result.ok) {
      setError(friendlyError(result.code, result.message));
      if (result.code === "ExpiredCodeException") setCodeExpired(true);
      return;
    }

    setSuccess(true);
    // Brief beat so the user reads the success state, then to sign in.
    window.setTimeout(() => router.push("/login"), 2000);
  };

  return (
    <div
      className={cn(
        "flex min-h-svh items-center justify-center p-4 px-safe py-safe",
        className,
      )}
      {...props}
    >
      <div className="w-full max-w-md rounded-2xl border border-white/30 bg-white/30 p-6 sm:p-8 shadow-xl backdrop-blur-md">
        <div className="flex flex-col items-center gap-6">
          <div className="text-center">
            <h1 className="text-2xl font-semibold text-foreground">
              Choose a new password
            </h1>
            <p className="text-sm text-muted-foreground">
              Pick a password you don&apos;t use anywhere else.
            </p>
          </div>

          {success ? (
            <div className="w-full space-y-4 text-center">
              <p className="text-sm text-foreground">
                Password reset! Redirecting to sign in…
              </p>
              <Link
                href="/login"
                className="block underline underline-offset-4 hover:text-foreground"
              >
                Go to sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="w-full space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="m@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="code">
                  Enter the code we sent to your email
                </Label>
                <Input
                  id="code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="123456"
                  maxLength={6}
                  value={code}
                  onChange={(e) =>
                    setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                  }
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">New password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    className="pr-10"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm new password</Label>
                <Input
                  id="confirm-password"
                  type={showPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>

              {error && (
                <div className="space-y-1">
                  <p className="text-sm text-destructive">{error}</p>
                  {codeExpired && (
                    <Link
                      href="/forgot-password"
                      className="block text-sm underline underline-offset-4 hover:text-foreground"
                    >
                      Request a new code
                    </Link>
                  )}
                </div>
              )}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Updating…" : "Set new password"}
              </Button>
              <p className="text-center text-sm text-muted-foreground">
                <Link
                  href="/login"
                  className="underline underline-offset-4 hover:text-foreground"
                >
                  Back to sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
