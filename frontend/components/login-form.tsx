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

export function LoginForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [cursor, setCursor] = useState({ x: 0, y: 0 });
  const [eyePos, setEyePos] = useState({ x: 0, y: 0 });
  const [blink, setBlink] = useState(false);

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
              Welcome back
            </h1>
            <p className="text-sm text-muted-foreground">Sign in to continue</p>
          </div>

          <div className="relative h-44 w-[300px]">
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
                  left: idx === 0 ? 80 : 150,
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
                <a
                  href="#"
                  className="text-xs text-muted-foreground underline-offset-4 hover:underline"
                >
                  Forgot your password?
                </a>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
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
