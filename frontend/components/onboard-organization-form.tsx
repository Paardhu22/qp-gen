"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { cn } from "@/lib/utils";
import { signUp, confirmSignUp, resendConfirmationCode, useSession } from "@/lib/auth-client";
import { getOrganizationInvite, acceptOrganizationInvite } from "@/lib/organizations-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff } from "lucide-react";

export function OnboardOrganizationForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const { refresh: refreshSession } = useSession();

  const [tokenChecking, setTokenChecking] = useState(true);
  const [tokenError, setTokenError] = useState("");

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState<"form" | "confirm">("form");
  const [code, setCode] = useState("");
  const [info, setInfo] = useState("");

  useEffect(() => {
    if (!token) {
      setTokenError("This invite link is missing its token.");
      setTokenChecking(false);
      return;
    }
    getOrganizationInvite(token)
      .then(({ email }) => setEmail(email))
      .catch((err: any) => setTokenError(err?.message || "This invite link is invalid or has expired."))
      .finally(() => setTokenChecking(false));
  }, [token]);

  const finishOnboarding = async () => {
    try {
      await acceptOrganizationInvite(token, organizationName);
      // The invite-accept call flips the user's status from "pending" to
      // "approved" server-side — the session cached during signUp still
      // holds the stale status, so it must be refreshed before navigating
      // or ProtectedLayout would show the pending-approval screen.
      await refreshSession();
      router.push("/dashboard");
    } catch (err: any) {
      setError(err?.message || "Failed to create your organization. Please try again.");
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!organizationName.trim()) {
      setError("Please enter your school's name.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    await signUp.email({
      name,
      email,
      password,
      fetchOptions: {
        onSuccess: () => finishOnboarding(),
        onConfirmationRequired: () => {
          setPhase("confirm");
          setInfo("We emailed you a verification code. Enter it below to finish.");
          setLoading(false);
        },
        onError: (ctx) => {
          setError(ctx.error.message);
          setLoading(false);
        },
      },
    });
  };

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);
    await confirmSignUp.email({
      email,
      code: code.trim(),
      password,
      fetchOptions: {
        onSuccess: () => finishOnboarding(),
        onError: (ctx) => {
          setError(ctx.error.message);
          setLoading(false);
        },
      },
    });
  };

  const handleResend = async () => {
    setError("");
    setInfo("");
    const result = await resendConfirmationCode(email);
    if (result.ok) setInfo(result.message);
    else setError(result.message);
  };

  if (tokenChecking) {
    return (
      <div className={cn("flex min-h-svh items-center justify-center p-4", className)} {...props}>
        <p className="text-sm text-muted-foreground">Checking your invite…</p>
      </div>
    );
  }

  if (tokenError) {
    return (
      <div className={cn("flex min-h-svh items-center justify-center p-4", className)} {...props}>
        <div className="w-full max-w-md rounded-2xl border border-white/30 bg-white/30 p-6 sm:p-8 shadow-xl backdrop-blur-md text-center space-y-4">
          <h1 className="text-xl font-semibold text-foreground">Invite not valid</h1>
          <p className="text-sm text-destructive">{tokenError}</p>
          <Link href="/login" className="block text-sm underline underline-offset-4 hover:text-foreground">
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex min-h-svh items-center justify-center p-4 px-safe py-safe", className)} {...props}>
      <div className="w-full max-w-md rounded-2xl border border-white/30 bg-white/30 p-6 sm:p-8 shadow-xl backdrop-blur-md">
        <div className="flex flex-col items-center gap-6">
          <div className="text-center">
            <h1 className="text-2xl font-semibold text-foreground">
              {phase === "confirm" ? "Verify your email" : "Set up your school"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {phase === "confirm"
                ? `Enter the code sent to ${email}`
                : "You'll be the admin for this organization."}
            </p>
          </div>

          {phase === "confirm" ? (
            <form onSubmit={handleConfirm} className="w-full space-y-4">
              <div className="space-y-2">
                <Label htmlFor="code">Verification code</Label>
                <Input
                  id="code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="123456"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                />
              </div>

              {info && <p className="text-sm text-muted-foreground">{info}</p>}
              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Verifying…" : "Verify & continue"}
              </Button>
              <button
                type="button"
                onClick={handleResend}
                className="w-full text-center text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
              >
                Didn&apos;t get a code? Resend
              </button>
            </form>
          ) : (
            <form onSubmit={handleSubmit} className="w-full space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" value={email} disabled />
              </div>

              <div className="space-y-2">
                <Label htmlFor="name">Your full name</Label>
                <Input
                  id="name"
                  type="text"
                  placeholder="Jane Smith"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoComplete="name"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="organizationName">School / organization name</Label>
                <Input
                  id="organizationName"
                  type="text"
                  placeholder="Sunrise Public School"
                  value={organizationName}
                  onChange={(e) => setOrganizationName(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="Create a password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    className="pr-10"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm Password</Label>
                <div className="relative">
                  <Input
                    id="confirm-password"
                    type={showConfirmPassword ? "text" : "password"}
                    placeholder="Repeat your password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    className="pr-10"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((v) => !v)}
                    aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Creating organization…" : "Create organization"}
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
