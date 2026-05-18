"use client";

import { useEffect, useState } from "react";
import { useSession } from "@/lib/auth-client";
import { fetchJson } from "@/lib/api-client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sun, Moon, Key, Cpu, RefreshCw, User } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const { data: session, isLoading, refresh } = useSession();
  const user = session?.user;

  // Theme preference state
  const [theme, setTheme] = useState<"light" | "dark">("light");

  // Change password form state
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [isRefreshingTokens, setIsRefreshingTokens] = useState(false);

  // Sync theme local state on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const isDark = document.documentElement.classList.contains("dark");
      setTheme(isDark ? "dark" : "light");
    }
  }, []);

  const handleThemeChange = (selectedTheme: "light" | "dark") => {
    setTheme(selectedTheme);
    localStorage.setItem("theme", selectedTheme);
    if (selectedTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    toast.success(`Theme preference updated to ${selectedTheme}.`);
  };

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

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!oldPassword || !newPassword || !confirmPassword) {
      toast.error("All password fields are required.");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("New password and confirm password do not match.");
      return;
    }

    setIsChangingPassword(true);
    try {
      await fetchJson("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ oldPassword, newPassword }),
      });
      toast.success("Password changed successfully.");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      toast.error(err.message || "Failed to change password. Please verify current password.");
    } finally {
      setIsChangingPassword(false);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8 bg-background min-h-full">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-foreground">Settings</h2>
        <p className="text-muted-foreground mt-2">Manage your account preferences, credentials, and API usage.</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Token Usage Metric Card */}
        <Card className="bg-card border-border flex flex-col justify-between">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg text-foreground flex items-center gap-2">
                <Cpu className="h-5 w-5 text-indigo-500" />
                API Token Usage
              </CardTitle>
              <Button
                variant="outline"
                size="icon"
                onClick={handleRefreshTokens}
                disabled={isRefreshingTokens}
                className="h-8 w-8 text-muted-foreground hover:text-foreground"
                title="Refresh stats"
              >
                <RefreshCw className={cn("h-4 w-4", isRefreshingTokens && "animate-spin")} />
              </Button>
            </div>
            <CardDescription className="text-muted-foreground">
              Total number of tokens consumed by this account for generating content.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {isLoading ? (
              <div className="py-6 flex items-center justify-center text-muted-foreground text-sm">
                Loading usage metrics...
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-6 bg-muted/20 border border-border rounded-xl">
                <span className="text-4xl font-extrabold tracking-tight text-foreground">
                  {((user as any)?.tokens_consumed || 0).toLocaleString()}
                </span>
                <span className="text-xs text-muted-foreground mt-2 uppercase tracking-wider font-semibold">
                  Tokens Consumed
                </span>
              </div>
            )}
            <p className="text-xs text-muted-foreground text-center">
              Token consumption depends on the length of input documents and complexity of questions generated.
            </p>
          </CardContent>
        </Card>

        {/* Theme Preference Card */}
        <Card className="bg-card border-border flex flex-col justify-between">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-foreground flex items-center gap-2">
              <Sun className="h-5 w-5 text-indigo-500" />
              Theme Preference
            </CardTitle>
            <CardDescription className="text-muted-foreground">
              Choose your interface color scheme preference.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => handleThemeChange("light")}
                className={cn(
                  "flex flex-col items-center justify-center p-6 rounded-xl border transition-all duration-200 cursor-pointer",
                  theme === "light"
                    ? "border-primary bg-primary/5 text-primary shadow-sm"
                    : "border-border bg-muted/20 text-muted-foreground hover:border-primary/50 hover:bg-muted/40"
                )}
              >
                <Sun className="h-6 w-6 mb-2" />
                <span className="text-sm font-semibold">Light Mode</span>
              </button>

              <button
                type="button"
                onClick={() => handleThemeChange("dark")}
                className={cn(
                  "flex flex-col items-center justify-center p-6 rounded-xl border transition-all duration-200 cursor-pointer",
                  theme === "dark"
                    ? "border-primary bg-primary/5 text-primary shadow-sm"
                    : "border-border bg-muted/20 text-muted-foreground hover:border-primary/50 hover:bg-muted/40"
                )}
              >
                <Moon className="h-6 w-6 mb-2" />
                <span className="text-sm font-semibold">Dark Mode</span>
              </button>
            </div>
            <p className="text-xs text-muted-foreground text-center">
              This setting will be stored locally and synced instantly across all active views.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Basic Details Card */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-foreground flex items-center gap-2">
              <User className="h-5 w-5 text-indigo-500" />
              Account Details
            </CardTitle>
            <CardDescription className="text-muted-foreground">
              Your profile information.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="text-muted-foreground text-sm py-4">Loading user profile...</div>
            ) : (
              <div className="space-y-4 text-sm">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <span className="text-muted-foreground font-medium">Name</span>
                  <span className="text-foreground font-semibold">{user?.name || "-"}</span>
                </div>
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <span className="text-muted-foreground font-medium">Email Address</span>
                  <span className="text-foreground font-semibold">{user?.email || "-"}</span>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <span className="text-muted-foreground font-medium">Verified User</span>
                  <span className="text-foreground font-semibold">
                    {user?.email_verified ? "Yes" : "No"}
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Change Password Card */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-foreground flex items-center gap-2">
              <Key className="h-5 w-5 text-indigo-500" />
              Change Password
            </CardTitle>
            <CardDescription className="text-muted-foreground">
              Update your account password credentials.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="old-password">Current Password</Label>
                <Input
                  id="old-password"
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  placeholder="Enter current password"
                  className="bg-background border-border text-foreground"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="new-password">New Password</Label>
                <Input
                  id="new-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password (min. 8 characters)"
                  className="bg-background border-border text-foreground"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm New Password</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  className="bg-background border-border text-foreground"
                  required
                />
              </div>

              <Button
                type="submit"
                disabled={isChangingPassword}
                className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold shadow-md mt-2"
              >
                {isChangingPassword ? "Updating Password..." : "Change Password"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
