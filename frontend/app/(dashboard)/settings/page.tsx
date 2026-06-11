"use client";

import { useState } from "react";
import { useSession } from "@/lib/auth-client";
import { fetchJson } from "@/lib/api-client";
import { getCognitoAccessToken } from "@/lib/token-storage";
import { cognitoSignIn, cognitoChangePassword } from "@/lib/cognito-client";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Cpu,
  RefreshCw,
  User,
  Key,
  Eye,
  EyeOff,
  Check,
  ArrowRight,
  X,
  Paintbrush,
} from "lucide-react";
import { ThemeToggle } from "@/components/ui/curtain-theme-toggle";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/* ─── Change-Password Modal ─────────────────────────────────────── */

type ModalStep = "verify" | "new-password";

function ChangePasswordModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { data: session } = useSession();
  const user = session?.user;

  const [step, setStep] = useState<ModalStep>("verify");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const resetAndClose = () => {
    setStep("verify");
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setShowCurrent(false);
    setShowNew(false);
    setShowConfirm(false);
    onClose();
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPassword) {
      toast.error("Please enter your current password.");
      return;
    }
    setIsVerifying(true);
    try {
      const email = user?.email;
      if (!email) {
        throw new Error("User email not found in session.");
      }
      await cognitoSignIn(email, currentPassword);
      setStep("new-password");
    } catch (err: any) {
      toast.error(err.message || "Incorrect current password. Please try again.");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPassword || !confirmPassword) {
      toast.error("Please fill in all fields.");
      return;
    }
    if (newPassword === currentPassword) {
      toast.error(
        "Your new password cannot be the same as your current password.",
      );
      return;
    }
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }
    setIsSaving(true);
    try {
      const accessToken = getCognitoAccessToken();
      if (!accessToken) {
        throw new Error("No active Cognito session found. Please sign in again.");
      }
      await cognitoChangePassword(accessToken, currentPassword, newPassword);
      toast.success("Password changed successfully.");
      resetAndClose();
    } catch (err: any) {
      toast.error(err.message || "Failed to change password.");
    } finally {
      setIsSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={resetAndClose}
      />

      {/* Modal panel */}
      <div className="relative z-10 w-full max-w-md mx-4 bg-background rounded-2xl border border-border shadow-2xl p-6">
        {/* Close button */}
        <button
          type="button"
          onClick={resetAndClose}
          className="absolute top-4 right-4 p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Step indicator */}
        <div className="flex items-center gap-2 mb-6">
          <div
            className={cn(
              "flex items-center justify-center h-7 w-7 rounded-full text-xs font-bold transition-colors",
              step === "verify"
                ? "bg-indigo-600 text-white"
                : "bg-green-500 text-white",
            )}
          >
            {step === "verify" ? "1" : <Check className="h-3.5 w-3.5" />}
          </div>
          <div className="h-px flex-1 bg-border" />
          <div
            className={cn(
              "flex items-center justify-center h-7 w-7 rounded-full text-xs font-bold transition-colors",
              step === "new-password"
                ? "bg-indigo-600 text-white"
                : "bg-muted text-muted-foreground",
            )}
          >
            2
          </div>
        </div>

        {step === "verify" ? (
          <>
            <h2 className="text-lg font-semibold text-foreground mb-1">
              Verify your identity
            </h2>
            <p className="text-sm text-muted-foreground mb-6">
              Enter your current password to continue.
            </p>
            <form onSubmit={handleVerify} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="current-pwd">Current Password</Label>
                <div className="relative">
                  <Input
                    id="current-pwd"
                    type={showCurrent ? "text" : "password"}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="Enter your current password"
                    className="pr-10 [&::-ms-reveal]:hidden [&::-ms-clear]:hidden"
                    autoComplete="current-password"
                    autoFocus
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrent((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showCurrent ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
              <Button
                type="submit"
                disabled={isVerifying}
                className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold gap-2"
              >
                {isVerifying ? (
                  "Verifying…"
                ) : (
                  <>
                    Verify & Continue <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </form>
          </>
        ) : (
          <>
            <h2 className="text-lg font-semibold text-foreground mb-1">
              Set a new password
            </h2>
            <p className="text-sm text-muted-foreground mb-6">
              Choose a strong password with at least 8 characters.
            </p>
            <form onSubmit={handleSave} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="new-pwd">New Password</Label>
                <div className="relative">
                  <Input
                    id="new-pwd"
                    type={showNew ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Enter new password (min. 8 characters)"
                    className={cn(
                      "pr-10 [&::-ms-reveal]:hidden [&::-ms-clear]:hidden",
                      newPassword &&
                        newPassword === currentPassword &&
                        "border-destructive focus-visible:ring-destructive/30",
                    )}
                    autoComplete="new-password"
                    autoFocus
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowNew((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showNew ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
                {newPassword && newPassword === currentPassword && (
                  <p className="text-xs text-destructive">
                    New password cannot be the same as your current password.
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirm-pwd">Confirm New Password</Label>
                <div className="relative">
                  <Input
                    id="confirm-pwd"
                    type={showConfirm ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Re-enter new password"
                    className={cn(
                      "pr-10 [&::-ms-reveal]:hidden [&::-ms-clear]:hidden",
                      confirmPassword &&
                        newPassword &&
                        confirmPassword === newPassword &&
                        newPassword !== currentPassword
                        ? "border-green-500 focus-visible:ring-green-500/30"
                        : confirmPassword && confirmPassword !== newPassword
                          ? "border-destructive focus-visible:ring-destructive/30"
                          : "",
                    )}
                    autoComplete="new-password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirm((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showConfirm ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
                {confirmPassword && confirmPassword !== newPassword && (
                  <p className="text-xs text-destructive">
                    Passwords do not match.
                  </p>
                )}
              </div>
              <div className="flex gap-3 pt-1">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setStep("verify")}
                  className="flex-1"
                >
                  Back
                </Button>
                <Button
                  type="submit"
                  disabled={
                    isSaving ||
                    (!!newPassword && newPassword === currentPassword) ||
                    (!!confirmPassword && confirmPassword !== newPassword)
                  }
                  className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
                >
                  {isSaving ? "Saving…" : "Save Password"}
                </Button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Settings Page ─────────────────────────────────────────────── */

export default function SettingsPage() {
  const { data: session, isLoading, refresh } = useSession();
  const user = session?.user;

  const [modalOpen, setModalOpen] = useState(false);
  const [isRefreshingTokens, setIsRefreshingTokens] = useState(false);

  const handleRefreshTokens = async () => {
    setIsRefreshingTokens(true);
    try {
      await refresh();
      toast.success("Token consumption metric updated.");
    } catch {
      toast.error("Failed to refresh token usage.");
    } finally {
      setIsRefreshingTokens(false);
    }
  };

  return (
    <div className="p-8 max-w-3xl mx-auto space-y-6 bg-background min-h-full">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-foreground">
          Settings
        </h2>
        <p className="text-muted-foreground mt-1">
          Manage your account preferences, credentials, and API usage.
        </p>
      </div>

      {/* Row 1 — Account Details (full width) */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg text-foreground flex items-center gap-2">
                <User className="h-5 w-5 text-indigo-500" />
                Account Details
              </CardTitle>
              <CardDescription className="text-muted-foreground mt-1">
                Your profile information.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              onClick={() => setModalOpen(true)}
              className="gap-2 text-sm border-indigo-300 text-indigo-600 hover:bg-indigo-50 hover:text-indigo-700 dark:border-indigo-700 dark:text-indigo-400 dark:hover:bg-indigo-950"
            >
              <Key className="h-4 w-4" />
              Change Password
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-muted-foreground text-sm py-4">
              Loading user profile…
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-x-12 gap-y-4 text-sm">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
                  Name
                </p>
                <p className="text-foreground font-semibold text-base">
                  {user?.name || "—"}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
                  Email Address
                </p>
                <p className="text-foreground font-semibold text-base">
                  {user?.email || "—"}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Row 2 — API Token Usage (full width) */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg text-foreground flex items-center gap-2">
                <Cpu className="h-5 w-5 text-indigo-500" />
                API Token Usage
              </CardTitle>
              <CardDescription className="text-muted-foreground mt-1">
                Total tokens consumed by this account for generating content.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="icon"
              onClick={handleRefreshTokens}
              disabled={isRefreshingTokens}
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              title="Refresh stats"
            >
              <RefreshCw
                className={cn("h-4 w-4", isRefreshingTokens && "animate-spin")}
              />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="py-8 flex items-center justify-center text-muted-foreground text-sm">
              Loading usage metrics…
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 bg-muted/20 border border-border rounded-xl">
              <span className="text-5xl font-extrabold tracking-tight text-foreground">
                {((user as any)?.tokens_consumed || 0).toLocaleString()}
              </span>
              <span className="text-xs text-muted-foreground mt-2 uppercase tracking-widest font-semibold">
                Tokens Consumed
              </span>
            </div>
          )}
          <p className="text-xs text-muted-foreground text-center">
            Token consumption depends on the length of input documents and
            complexity of questions generated.
          </p>
        </CardContent>
      </Card>

      {/* Row 3 — Appearance (full width) */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg text-foreground flex items-center gap-2">
                <Paintbrush className="h-5 w-5 text-indigo-500" />
                Appearance
              </CardTitle>
              <CardDescription className="text-muted-foreground mt-1">
                Customize the look and feel of the application.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between p-4 bg-muted/20 border border-border rounded-xl">
            <div>
              <h3 className="text-sm font-medium text-foreground">Theme Preference</h3>
              <p className="text-xs text-muted-foreground mt-1">
                Switch between light and dark modes.
              </p>
            </div>
            <div className="flex items-center justify-center">
              <ThemeToggle variant="icon" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Change Password Modal */}
      <ChangePasswordModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
      />
    </div>
  );
}
