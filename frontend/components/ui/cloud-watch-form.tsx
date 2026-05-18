"use client"

import React, { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function CloudWatchForm() {
  const [isTyping, setIsTyping] = useState(false)
  const [cursor, setCursor] = useState({ x: 0, y: 0 })
  const [eyePos, setEyePos] = useState({ x: 0, y: 0 })
  const [blink, setBlink] = useState(false)

  useEffect(() => {
    const handleMouse = (e: MouseEvent) =>
      setCursor({ x: e.clientX, y: e.clientY })
    window.addEventListener("mousemove", handleMouse)
    return () => window.removeEventListener("mousemove", handleMouse)
  }, [])

  useEffect(() => {
    const offsetX = (cursor.x / window.innerWidth - 0.5) * 40
    const offsetY = (cursor.y / window.innerHeight - 0.5) * 20
    setEyePos({ x: offsetX, y: offsetY })
  }, [cursor])

  useEffect(() => {
    const interval = setInterval(() => {
      setBlink(true)
      setTimeout(() => setBlink(false), 200)
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="flex min-h-svh items-center justify-center p-4">
      <div className="flex w-full max-w-md flex-col items-center gap-6 rounded-2xl border border-white/30 bg-white/30 p-8 shadow-xl backdrop-blur-md">
        <div className="relative h-40 w-[280px]">
          <img
            src="https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=800&q=80"
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

        <div className="w-full space-y-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input placeholder="Your Name" />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input type="email" placeholder="Your Email" />
          </div>
          <div className="space-y-2">
            <Label>Username</Label>
            <Input placeholder="Username" />
          </div>
          <div className="space-y-2">
            <Label>Password</Label>
            <Input
              type="password"
              placeholder="Password"
              onFocus={() => setIsTyping(true)}
              onBlur={() => setIsTyping(false)}
            />
          </div>
          <Button className="mt-2 w-full">Submit</Button>
        </div>
      </div>
    </div>
  )
}
