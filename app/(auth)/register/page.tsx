"use client";

import { useState } from "react";
import { signUp } from "@/lib/auth-client";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    await signUp.email({
      email,
      password,
      name,
      fetchOptions: {
        onSuccess: () => {
          router.push("/dashboard");
        },
        onError: (ctx) => {
          alert(ctx.error.message);
          setLoading(false);
        }
      }
    });
  };

  return (
    <Card className="w-full max-w-md bg-zinc-900 border-zinc-800">
      <CardHeader>
        <CardTitle className="text-2xl font-bold text-zinc-100">Create an account</CardTitle>
        <CardDescription className="text-zinc-400">Enter your details below to get started</CardDescription>
      </CardHeader>
      <form onSubmit={handleRegister}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name" className="text-zinc-300">Name</Label>
            <Input 
              id="name" 
              type="text" 
              placeholder="John Doe" 
              value={name}
              onChange={(e) => setName(e.target.value)}
              required 
              className="bg-zinc-800 border-zinc-700 text-zinc-100"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email" className="text-zinc-300">Email</Label>
            <Input 
              id="email" 
              type="email" 
              placeholder="you@example.com" 
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required 
              className="bg-zinc-800 border-zinc-700 text-zinc-100"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password" className="text-zinc-300">Password</Label>
            <Input 
              id="password" 
              type="password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required 
              className="bg-zinc-800 border-zinc-700 text-zinc-100"
            />
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-4">
          <Button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-700 text-white" disabled={loading}>
            {loading ? "Creating account..." : "Sign Up"}
          </Button>
          <div className="text-sm text-center text-zinc-400">
            Already have an account? <Link href="/login" className="text-indigo-400 hover:underline">Login</Link>
          </div>
        </CardFooter>
      </form>
    </Card>
  );
}
