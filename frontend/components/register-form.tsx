"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { cn } from "@/lib/utils";
import { signUp, confirmSignUp, resendConfirmationCode } from "@/lib/auth-client";
import {
  acceptTeacherInvite,
  getOrganizationInvite,
  joinOrganization,
  listPublicOrganizations,
  type InvitePreview,
  type PublicOrganization,
} from "@/lib/organizations-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Eye, EyeOff } from "lucide-react";

export function RegisterForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const router = useRouter();
  // `?invite=` — a school admin's link. When present the school is already
  // decided and the address is fixed, so the picker comes off the form
  // entirely rather than sitting there inviting a contradiction.
  const inviteToken = useSearchParams().get("invite") ?? "";
  const [invite, setInvite] = useState<InvitePreview | null>(null);
  const [inviteError, setInviteError] = useState("");

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [organizations, setOrganizations] = useState<PublicOrganization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [orgsLoading, setOrgsLoading] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // Two-phase signup: "form" collects details; "confirm" collects the emailed
  // verification code (shown only when the Cognito pool requires verification).
  const [phase, setPhase] = useState<"form" | "confirm">("form");
  const [code, setCode] = useState("");
  const [info, setInfo] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [cursor, setCursor] = useState({ x: 0, y: 0 });
  const [eyePos, setEyePos] = useState({ x: 0, y: 0 });
  const [blink, setBlink] = useState(false);

  useEffect(() => {
    if (!inviteToken) return;
    let cancelled = false;
    getOrganizationInvite(inviteToken)
      .then((preview) => {
        if (cancelled) return;
        setInvite(preview);
        // The invite names the address it was issued to, and accepting checks
        // it. Pre-filling something else would only fail at the last step.
        setEmail(preview.email);
      })
      .catch((err: any) => {
        if (cancelled) return;
        setInviteError(
          err?.message || "That invite link is no longer valid. Sign up normally instead.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [inviteToken]);

  useEffect(() => {
    // An invited teacher never picks a school, so the list is not worth
    // fetching — and showing one would suggest the invite is negotiable.
    if (invite) {
      setOrgsLoading(false);
      return;
    }
    // Re-queried as the address is typed: the backend flags and promotes the
    // school claiming that email domain, which turns "find your school in this
    // list" into "confirm this is your school". Debounced because it runs per
    // keystroke, and settled at 400ms because that is roughly a pause in
    // typing rather than a gap between letters.
    let cancelled = false;
    const timer = setTimeout(() => {
      listPublicOrganizations(email)
        .then((orgs) => {
          if (cancelled) return;
          setOrganizations(orgs);
          // Auto-select the domain match, but never overwrite a choice the
          // teacher has already made — they may genuinely work somewhere other
          // than where their email says.
          setOrganizationId((current) => {
            if (current) return current;
            const matched = orgs.find((org) => org.matches_email_domain);
            return matched?.id ?? "";
          });
        })
        .catch(() => {
          if (!cancelled) setOrganizations([]);
        })
        .finally(() => {
          if (!cancelled) setOrgsLoading(false);
        });
    }, email.includes("@") ? 400 : 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [email, invite]);

  useEffect(() => {
    const handleMouse = (e: MouseEvent) =>
      setCursor({ x: e.clientX, y: e.clientY });
    window.addEventListener("mousemove", handleMouse);
    return () => window.removeEventListener("mousemove", handleMouse);
  }, []);

  useEffect(() => {
    const offsetX = (cursor.x / window.innerWidth - 0.5) * 40;
    const offsetY = (cursor.y / window.innerHeight - 0.5) * 20;
    setEyePos({ x: offsetX, y: offsetY });
  }, [cursor]);

  useEffect(() => {
    const interval = setInterval(() => {
      setBlink(true);
      setTimeout(() => setBlink(false), 200);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (!invite && organizations.length > 0 && !organizationId) {
      setError("Please select your school.");
      return;
    }

    setLoading(true);
    await signUp.email({
      name,
      email,
      password,
      fetchOptions: {
        onSuccess: () => finishSignup(),
        onConfirmationRequired: () => {
          // Pool requires email verification — switch to the code-entry step.
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

  // Runs once the user is authenticated for the first time (either the
  // auto-confirm signUp path or after confirmSignUp). Requests to join the
  // selected school before landing on the dashboard. If this fails, keep the
  // teacher here: otherwise their account has no membership request and no UI
  // to send one later.
  const finishSignup = async () => {
    if (invite) {
      try {
        // Accepting joins the school already approved — the admin who issued
        // the link is the person who would otherwise have approved it.
        await acceptTeacherInvite(inviteToken);
      } catch (err: any) {
        console.warn("Failed to accept the teacher invite after signup:", err);
        setError(
          err?.message ||
            "Your account was created, but we could not join you to the school. Try the invite link again.",
        );
        setLoading(false);
        return;
      }
      router.push("/dashboard");
      return;
    }
    if (organizationId) {
      try {
        await joinOrganization(organizationId);
      } catch (err) {
        console.warn("Failed to join organization after signup:", err);
        setError("Your account was created, but we could not send the school join request. Check your connection and try again.");
        setLoading(false);
        return;
      }
    }
    router.push("/dashboard");
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
        onSuccess: () => finishSignup(),
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
    if (result.ok) {
      setInfo(result.message);
    } else {
      setError(result.message);
    }
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
              {phase === "confirm" ? "Verify your email" : "Create an account"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {phase === "confirm"
                ? `Enter the code sent to ${email}`
                : invite?.organization_name
                  ? `You've been invited to join ${invite.organization_name}`
                  : "Enter your details to get started"}
            </p>
          </div>

          <div className="relative h-44 w-full max-w-[300px]">
            <img
              src="https://pub-940ccf6255b54fa799a9b01050e6c227.r2.dev/cloud.jpg"
              alt="Cloud background"
              className="h-full w-full rounded-xl object-cover"
            />

            {["left", "right"].map((side, idx) => (
              <div
                key={side}
                className="absolute flex items-end justify-center overflow-hidden"
                style={{
                  top: 60,
                  left: idx === 0 ? "26.7%" : "50%",
                  width: 28,
                  height: isTyping ? 4 : blink ? 6 : 40,
                  borderRadius: isTyping || blink ? "2px" : "50% / 60%",
                  backgroundColor: isTyping ? "black" : "white",
                  transition: "all 0.15s ease",
                }}
              >
                {!isTyping && (
                  <div
                    className="bg-black"
                    style={{
                      width: 16,
                      height: 16,
                      borderRadius: "50%",
                      marginBottom: 4,
                      transform: `translate(${eyePos.x}px, 0px)`,
                      transition: "all 0.1s ease",
                    }}
                  />
                )}
              </div>
            ))}
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
              <Label htmlFor="name">Full Name</Label>
              <Input
                id="name"
                type="text"
                placeholder="John Doe"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="m@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                // Fixed by the invite: accepting checks the address, so an
                // editable field here can only produce a failure at the end.
                readOnly={Boolean(invite)}
                required
              />
              {invite && (
                <p className="text-xs text-muted-foreground">
                  This invite was sent to {invite.email}.
                </p>
              )}
            </div>

            {invite ? (
              <div className="rounded-lg border border-border bg-muted/40 p-3">
                <p className="text-sm font-medium text-foreground">
                  {invite.organization_name}
                </p>
                <p className="text-xs text-muted-foreground">
                  You&apos;ll be added to this school straight away — nothing to wait for.
                </p>
              </div>
            ) : (
            <div className="space-y-2">
              <Label htmlFor="organization">School</Label>
              {orgsLoading ? (
                <p className="text-sm text-muted-foreground">Loading schools…</p>
              ) : organizations.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No schools have been set up yet. Ask your admin to invite your school first.
                </p>
              ) : (
                <Select value={organizationId} onValueChange={(v) => setOrganizationId(v ?? "")}>
                  <SelectTrigger id="organization" className="w-full">
                    <SelectValue placeholder="Select your school" />
                  </SelectTrigger>
                  <SelectContent>
                    {organizations.map((org) => (
                      <SelectItem key={org.id} value={org.id}>
                        {org.name}
                        {org.city ? ` — ${org.city}` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              {organizations.some((org) => org.matches_email_domain) && (
                <p className="text-xs text-muted-foreground">
                  Matched from your email address. Change it if that is not your school.
                </p>
              )}
            </div>
            )}

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
                  onFocus={() => setIsTyping(true)}
                  onBlur={() => setIsTyping(false)}
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
                  onFocus={() => setIsTyping(true)}
                  onBlur={() => setIsTyping(false)}
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

            {inviteError && <p className="text-sm text-destructive">{inviteError}</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Creating account…" : "Sign up"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link
                href="/login"
                className="underline underline-offset-4 hover:text-foreground"
              >
                Login
              </Link>
            </p>
          </form>
          )}
        </div>
      </div>
    </div>
  );
}
