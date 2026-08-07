"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { cn } from "@/lib/utils";
import { signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff } from "lucide-react";
import { WelcomeScreen } from "@/components/ui/onboarding-welcome-screen";

export function LoginForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const router = useRouter();

  const [showOnboarding, setShowOnboarding] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const GMAIL_REGEX = /^[a-zA-Z0-9._%+\-]+@gmail\.com$/;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!GMAIL_REGEX.test(email)) {
      setError("Please enter a valid Gmail address (e.g. example@gmail.com).");
      return;
    }

    setLoading(true);
    await signIn.email({
      email,
      password,
      fetchOptions: {
        onSuccess: () => router.push("/dashboard"),
        onError: (ctx) => {
          setError(ctx.error.message);
          setLoading(false);
        },
      },
    });
  };

  if (showOnboarding) {
    return (
      <div
        className={cn(
          "flex min-h-svh items-center justify-center p-4 px-safe py-safe",
          className,
        )}
        {...props}
      >
        <div className="relative w-full max-w-sm h-[600px] overflow-hidden rounded-3xl border border-white/30 shadow-xl bg-white">
          <WelcomeScreen
            imageUrl="/IMG-20260514-WA0000.jpg-removebg-preview.png"
            title={
              <>
                Welcome to <span className="text-primary">HSAT</span>
              </>
            }
            description="Discover and build question papers effortlessly with your personalized AI assistant."
            buttonText="Login to your account"
            onButtonClick={() => setShowOnboarding(false)}
            secondaryActionText={
              <span>
                New here?{" "}
                <span className="font-semibold text-primary">Sign up</span>
              </span>
            }
            onSecondaryActionClick={() => router.push("/register")}
          />
        </div>
      </div>
    );
  }

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
              Welcome back
            </h1>
            <p className="text-sm text-muted-foreground">Sign in to continue</p>
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

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <Link
                  href="/forgot-password"
                  className="text-xs text-muted-foreground underline-offset-4 hover:underline hover:text-foreground"
                >
                  Forgot your password?
                </Link>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
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

            {error && <p className="text-sm text-destructive">{error}</p>}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Login"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              Don&apos;t have an account?{" "}
              <Link
                href="/register"
                className="underline underline-offset-4 hover:text-foreground"
              >
                Sign up
              </Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
