"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useDropzone } from "react-dropzone";

import { cn } from "@/lib/utils";
import { signUp, confirmSignUp, resendConfirmationCode, useSession } from "@/lib/auth-client";
import {
  getOrganizationInvite,
  acceptOrganizationInvite,
  uploadOrganizationLogo,
  type OrganizationProfile,
} from "@/lib/organizations-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff, ImageIcon, Check, Loader2 } from "lucide-react";

/**
 * Onboarding runs as three steps plus an interstitial.
 *
 *   account  → the Cognito signup fields, all required
 *   details  → the institute profile, all optional (Skip is a first-class exit)
 *   confirm  → only when the pool returns UNCONFIRMED; not a step the user counts
 *   logo     → the crest, optional
 *
 * The order is forced by one fact: a logo upload needs an organization id, and
 * the organization does not exist until the invite is accepted. So details are
 * collected *before* the account is created (they ride along on the accept
 * call) while the crest is uploaded *after*.
 */
type Phase = "account" | "details" | "confirm" | "logo";

const STEPS: { phase: Phase; label: string }[] = [
  { phase: "account", label: "Account" },
  { phase: "details", label: "Institute" },
  { phase: "logo", label: "Logo" },
];

const EMPTY_PROFILE: OrganizationProfile = {
  email_domains: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  postal_code: "",
  country: "India",
  phone: "",
  website: "",
  gstin: "",
};

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

  const [profile, setProfile] = useState<OrganizationProfile>(EMPTY_PROFILE);
  const [organizationId, setOrganizationId] = useState("");
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState("");

  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState<Phase>("account");
  const [code, setCode] = useState("");

  useEffect(() => {
    if (!token) {
      setTokenError("This invite link is missing its token.");
      setTokenChecking(false);
      return;
    }
    getOrganizationInvite(token)
      .then((preview) => {
        // A teacher's invite joins an existing school; it has no organization
        // to set up. Landing here would walk them through creating one and
        // then quietly ignore everything they typed, so send them to the form
        // that actually matches their link.
        if (preview.role === "teacher") {
          router.replace(`/register?invite=${encodeURIComponent(token)}`);
          return;
        }
        setEmail(preview.email);
      })
      .catch((err: any) =>
        setTokenError(err?.message || "This invite link is invalid or has expired."),
      )
      .finally(() => setTokenChecking(false));
  }, [token, router]);

  // Object URLs are leaked unless revoked; the preview only ever holds one.
  useEffect(() => {
    if (!logoFile) {
      setLogoPreview("");
      return;
    }
    const url = URL.createObjectURL(logoFile);
    setLogoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [logoFile]);

  const setField = (key: keyof OrganizationProfile) => (value: string) =>
    setProfile((prev) => ({ ...prev, [key]: value }));

  /**
   * Create the organization, then hand off to the logo step.
   *
   * Accepting the invite flips the user's status from "pending" to "approved"
   * server-side. The session cached during signUp still holds the stale
   * status, so it must be refreshed before we navigate anywhere or
   * ProtectedLayout shows the pending-approval screen.
   */
  const createOrganization = useCallback(async () => {
    try {
      const org = await acceptOrganizationInvite(token, organizationName, profile);
      await refreshSession();
      setOrganizationId(org.id);
      setError("");
      setPhase("logo");
    } catch (err: any) {
      setError(err?.message || "Failed to create your organization. Please try again.");
      setPhase("details");
    } finally {
      setLoading(false);
    }
  }, [token, organizationName, profile, refreshSession]);

  /** Step 1 → step 2. Purely local validation; nothing is sent yet. */
  const handleAccountNext = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name.trim()) return setError("Please enter your name.");
    if (!organizationName.trim()) return setError("Please enter your school's name.");
    if (password !== confirmPassword) return setError("Passwords do not match.");

    setPhase("details");
  };

  /**
   * Step 2 → account creation. Reached by both "Continue" and "Skip"; the only
   * difference is whether `profile` still holds its blanks, which the backend
   * treats identically to omitting them.
   */
  const submitSignup = async () => {
    setError("");
    setLoading(true);
    await signUp.email({
      name,
      email,
      password,
      fetchOptions: {
        onSuccess: () => createOrganization(),
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
        onSuccess: () => createOrganization(),
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

  /**
   * Finish. A failed crest upload is deliberately not fatal: the organization
   * already exists at this point, and stranding an admin on the last step over
   * an image would be worse than letting them add it later in Settings.
   */
  const finish = async (withLogo: boolean) => {
    setError("");
    setLoading(true);
    if (withLogo && logoFile && organizationId) {
      try {
        await uploadOrganizationLogo(organizationId, logoFile);
      } catch (err: any) {
        setError(
          `${err?.message || "That logo could not be uploaded."} You can add it later in Settings.`,
        );
        setLoading(false);
        return;
      }
    }
    router.push("/dashboard");
  };

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) {
      setLogoFile(accepted[0]);
      setError("");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      // Mirrors ALLOWED_CONTENT_TYPES in services/brand_kit.py. SVG is absent
      // there deliberately (a script-bearing document that gets inlined into
      // exported pages), so it must stay absent here too.
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/webp": [".webp"],
      "image/gif": [".gif"],
    },
    maxSize: 4 * 1024 * 1024,
    multiple: false,
  });

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
          <Link
            href="/login"
            className="block text-sm underline underline-offset-4 hover:text-foreground"
          >
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  // "confirm" is an interruption of step 2, not a step of its own — the
  // indicator keeps showing Institute so the user does not feel sent backwards.
  const activeIndex = phase === "logo" ? 2 : phase === "account" ? 0 : 1;

  const heading =
    phase === "confirm"
      ? "Verify your email"
      : phase === "details"
        ? "About your institute"
        : phase === "logo"
          ? "Add your logo"
          : "Set up your school";

  const subheading =
    phase === "confirm"
      ? `Enter the code sent to ${email}`
      : phase === "details"
        ? "This appears on your papers. You can skip it and add it later."
        : phase === "logo"
          ? "It appears on every paper your school prints."
          : "You'll be the admin for this organization.";

  return (
    <div
      className={cn("flex min-h-svh items-center justify-center p-4 px-safe py-safe", className)}
      {...props}
    >
      <div className="w-full max-w-lg rounded-2xl border border-white/30 bg-white/30 p-6 sm:p-8 shadow-xl backdrop-blur-md">
        <div className="flex flex-col items-center gap-6">
          <div className="text-center">
            <h1 className="text-2xl font-semibold text-foreground">{heading}</h1>
            <p className="text-sm text-muted-foreground">{subheading}</p>
          </div>

          <ol className="flex w-full items-center gap-2" aria-label="Progress">
            {STEPS.map((step, i) => {
              const done = i < activeIndex;
              const active = i === activeIndex;
              return (
                <li key={step.phase} className="flex flex-1 items-center gap-2">
                  <span
                    aria-current={active ? "step" : undefined}
                    className={cn(
                      "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium transition-colors",
                      done && "bg-foreground text-background",
                      active && "bg-foreground text-background",
                      !done && !active && "bg-muted text-muted-foreground",
                    )}
                  >
                    {done ? <Check className="h-3.5 w-3.5" /> : i + 1}
                  </span>
                  <span
                    className={cn(
                      "text-xs",
                      active ? "font-medium text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {step.label}
                  </span>
                  {i < STEPS.length - 1 && <span className="h-px flex-1 bg-border" />}
                </li>
              );
            })}
          </ol>

          {phase === "account" && (
            <form onSubmit={handleAccountNext} className="w-full space-y-4">
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
                    {showConfirmPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" className="w-full">
                Continue
              </Button>
            </form>
          )}

          {phase === "details" && (
            <div className="w-full space-y-4">
              <div className="space-y-2">
                <Label htmlFor="address_line1">Address</Label>
                <Input
                  id="address_line1"
                  placeholder="12 Nehru Road"
                  value={profile.address_line1}
                  onChange={(e) => setField("address_line1")(e.target.value)}
                />
                <Input
                  aria-label="Address line 2"
                  placeholder="Near City Hospital (optional)"
                  value={profile.address_line2}
                  onChange={(e) => setField("address_line2")(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="city">City</Label>
                  <Input
                    id="city"
                    placeholder="Hyderabad"
                    value={profile.city}
                    onChange={(e) => setField("city")(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="state">State</Label>
                  <Input
                    id="state"
                    placeholder="Telangana"
                    value={profile.state}
                    onChange={(e) => setField("state")(e.target.value)}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="postal_code">PIN code</Label>
                  <Input
                    id="postal_code"
                    inputMode="numeric"
                    placeholder="500001"
                    value={profile.postal_code}
                    onChange={(e) => setField("postal_code")(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="phone">Phone</Label>
                  <Input
                    id="phone"
                    type="tel"
                    placeholder="+91 98765 43210"
                    value={profile.phone}
                    onChange={(e) => setField("phone")(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="website">Website</Label>
                <Input
                  id="website"
                  type="url"
                  placeholder="https://sunrisepublic.edu.in"
                  value={profile.website}
                  onChange={(e) => setField("website")(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email_domains">
                  Staff email domain{" "}
                  <span className="text-muted-foreground">(recommended)</span>
                </Label>
                <Input
                  id="email_domains"
                  placeholder="sunrisepublic.edu.in"
                  value={profile.email_domains}
                  onChange={(e) => setField("email_domains")(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Teachers signing up with an address at this domain will see your
                  school pre-selected instead of hunting for it in a list. Separate
                  several with commas. Public providers like gmail.com can&apos;t be
                  used — they would match everybody.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="gstin">
                  GSTIN <span className="text-muted-foreground">(if you have one)</span>
                </Label>
                <Input
                  id="gstin"
                  placeholder="29ABCDE1234F1Z5"
                  value={profile.gstin}
                  onChange={(e) => setField("gstin")(e.target.value.toUpperCase())}
                  maxLength={15}
                  className="font-mono"
                />
                <p className="text-xs text-muted-foreground">
                  15 characters. Leave blank if your institution is not registered.
                </p>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <div className="flex gap-3">
                <Button
                  type="button"
                  variant="outline"
                  className="flex-1"
                  disabled={loading}
                  onClick={() => {
                    setProfile(EMPTY_PROFILE);
                    void submitSignup();
                  }}
                >
                  Skip for now
                </Button>
                <Button
                  type="button"
                  className="flex-1"
                  disabled={loading}
                  onClick={() => void submitSignup()}
                >
                  {loading ? "Creating…" : "Continue"}
                </Button>
              </div>
              <button
                type="button"
                onClick={() => setPhase("account")}
                disabled={loading}
                className="w-full text-center text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground disabled:opacity-50"
              >
                Back
              </button>
            </div>
          )}

          {phase === "confirm" && (
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
          )}

          {phase === "logo" && (
            <div className="w-full space-y-4">
              <div
                {...getRootProps()}
                className={cn(
                  "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
                  isDragActive
                    ? "border-foreground bg-foreground/5"
                    : "border-border hover:border-foreground/40",
                )}
              >
                <input {...getInputProps()} />
                {logoPreview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={logoPreview}
                    alt="Logo preview"
                    className="max-h-28 max-w-full object-contain"
                  />
                ) : (
                  <ImageIcon className="h-8 w-8 text-muted-foreground" aria-hidden />
                )}
                <div className="space-y-1">
                  <p className="text-sm font-medium text-foreground">
                    {logoFile ? logoFile.name : "Drop your crest here, or click to choose"}
                  </p>
                  <p className="text-xs text-muted-foreground">PNG, JPEG, WebP or GIF, up to 4 MB</p>
                </div>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <div className="flex gap-3">
                <Button
                  type="button"
                  variant="outline"
                  className="flex-1"
                  disabled={loading}
                  onClick={() => void finish(false)}
                >
                  Skip for now
                </Button>
                <Button
                  type="button"
                  className="flex-1"
                  disabled={loading || !logoFile}
                  onClick={() => void finish(true)}
                >
                  {loading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Uploading…
                    </>
                  ) : (
                    "Finish"
                  )}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
