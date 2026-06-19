"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
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
    if (!result.ok) {
      setLoading(false);
      setError(result.message);
      return;
    }
    // Cognito emailed a 6-digit code — send the user straight to the reset page
    // with their email pre-filled so they only need to enter the code + new
    // password. Keep `loading` true through the navigation.
    router.push(`/reset-password?email=${encodeURIComponent(email)}`);
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
              Forgot your password?
            </h1>
            <p className="text-sm text-muted-foreground">
              Enter the email you signed up with — we&apos;ll email you a 6-digit
              reset code.
            </p>
          </div>

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
                {loading ? "Sending…" : "Send reset code"}
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
        </div>
      </div>
    </div>
  );
}
