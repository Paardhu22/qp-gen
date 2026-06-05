"use client";

import { useState } from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";
import { requestPasswordReset } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const GMAIL_REGEX = /^[a-zA-Z0-9._%+\-]+@gmail\.com$/;

export function ForgotPasswordForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!GMAIL_REGEX.test(email)) {
      setError("Please enter a valid Gmail address.");
      return;
    }
    setLoading(true);
    const result = await requestPasswordReset(email);
    setLoading(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setSubmitted(true);
  };

  return (
    <div
      className={cn(
        "flex min-h-svh items-center justify-center p-4",
        className,
      )}
      {...props}
    >
      <div className="w-full max-w-md rounded-2xl border border-white/30 bg-white/30 p-8 shadow-xl backdrop-blur-md">
        <div className="flex flex-col items-center gap-6">
          <div className="text-center">
            <h1 className="text-2xl font-semibold text-foreground">
              Forgot your password?
            </h1>
            <p className="text-sm text-muted-foreground">
              Enter the email you signed up with — we&apos;ll email a reset link.
            </p>
          </div>

          {submitted ? (
            <div className="w-full space-y-4 text-center">
              <p className="text-sm text-foreground">
                If an account with <strong>{email}</strong> exists, a password
                reset link has been sent. Check your inbox (and spam folder).
              </p>
              <p className="text-xs text-muted-foreground">
                The link expires in 60 minutes.
              </p>
              <Link
                href="/login"
                className="block underline underline-offset-4 hover:text-foreground"
              >
                Back to sign in
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

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Sending…" : "Send reset link"}
              </Button>
              <p className="text-center text-sm text-muted-foreground">
                Remembered it?{" "}
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
