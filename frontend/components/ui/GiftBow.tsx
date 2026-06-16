import type { CSSProperties } from "react";

interface GiftBowProps {
  className?: string;
  style?: CSSProperties;
}

export default function GiftBow({ className, style }: GiftBowProps) {
  return (
    <svg
      viewBox="0 0 480 420"
      className={className}
      style={style}
      role="img"
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        {/* Vermilion → burnt-orange satin: deep mahogany shadow to warm highlight */}
        <linearGradient id="bow-loop-l" x1="0.08" y1="0" x2="0.78" y2="1">
          <stop offset="0" stopColor="#F07840" />
          <stop offset="0.16" stopColor="#DC5A18" />
          <stop offset="0.5" stopColor="#B34000" />
          <stop offset="0.8" stopColor="#8F2E00" />
          <stop offset="1" stopColor="#6B1A00" />
        </linearGradient>
        <linearGradient id="bow-loop-r" x1="0.92" y1="0" x2="0.22" y2="1">
          <stop offset="0" stopColor="#F07840" />
          <stop offset="0.16" stopColor="#DC5A18" />
          <stop offset="0.5" stopColor="#B34000" />
          <stop offset="0.8" stopColor="#8F2E00" />
          <stop offset="1" stopColor="#6B1A00" />
        </linearGradient>
        <linearGradient id="bow-tail" x1="0.32" y1="0" x2="0.68" y2="1">
          <stop offset="0" stopColor="#D0581A" />
          <stop offset="0.42" stopColor="#B34000" />
          <stop offset="0.8" stopColor="#8F2E00" />
          <stop offset="1" stopColor="#6B1200" />
        </linearGradient>
        <radialGradient id="bow-knot" cx="0.42" cy="0.32" r="0.95">
          <stop offset="0" stopColor="#F59070" />
          <stop offset="0.45" stopColor="#DC5A18" />
          <stop offset="0.74" stopColor="#B34000" />
          <stop offset="1" stopColor="#6B1A00" />
        </radialGradient>
      </defs>

      {/* Tails hang behind the knot */}
      <path
        d="M222 198 C214 256 198 312 172 380 L196 366 L210 392 C230 320 240 258 248 200 Z"
        fill="url(#bow-tail)"
      />
      <path
        d="M258 198 C266 256 282 312 308 380 L284 366 L270 392 C250 320 240 258 232 200 Z"
        fill="url(#bow-tail)"
      />
      {/* Silk reflection running down each tail */}
      <path
        d="M236 212 C228 264 214 314 192 372"
        stroke="#F09060"
        strokeOpacity="0.42"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M244 212 C252 264 266 314 288 372"
        stroke="#F09060"
        strokeOpacity="0.42"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />

      {/* Loops */}
      <path
        d="M236 166 C188 92 70 88 36 150 C10 198 96 234 236 198 Z"
        fill="url(#bow-loop-l)"
      />
      <path
        d="M244 166 C292 92 410 88 444 150 C470 198 384 234 244 198 Z"
        fill="url(#bow-loop-r)"
      />

      {/* Deep fold shadows where the loops tuck under the knot */}
      <path
        d="M236 172 C176 170 108 188 66 214 C150 198 206 192 236 194 Z"
        fill="#3A0E00"
        fillOpacity="0.46"
      />
      <path
        d="M244 172 C304 170 372 188 414 214 C330 198 274 192 244 194 Z"
        fill="#3A0E00"
        fillOpacity="0.46"
      />

      {/* Soft satin sheen along the top of each loop */}
      <path
        d="M228 160 C176 106 88 108 52 148"
        stroke="#FFB090"
        strokeOpacity="0.52"
        strokeWidth="6"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M252 160 C304 106 392 108 428 148"
        stroke="#FFB090"
        strokeOpacity="0.52"
        strokeWidth="6"
        fill="none"
        strokeLinecap="round"
      />
      {/* Sharp glint riding the sheen */}
      <path
        d="M222 152 C182 118 122 118 90 140"
        stroke="#FFD4B0"
        strokeOpacity="0.72"
        strokeWidth="2.25"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M258 152 C298 118 358 118 390 140"
        stroke="#FFD4B0"
        strokeOpacity="0.72"
        strokeWidth="2.25"
        fill="none"
        strokeLinecap="round"
      />

      {/* Center knot */}
      <path
        d="M208 152 Q198 152 198 168 L198 184 Q198 200 208 200 L272 200 Q282 200 282 184 L282 168 Q282 152 272 152 Z"
        fill="url(#bow-knot)"
      />
      <path
        d="M226 154 C222 170 222 184 226 198"
        stroke="#3A0E00"
        strokeOpacity="0.38"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M254 154 C258 170 258 184 254 198"
        stroke="#3A0E00"
        strokeOpacity="0.38"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M212 160 C232 154 246 154 268 160"
        stroke="#FFD0A0"
        strokeOpacity="0.5"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
      <ellipse cx="224" cy="168" rx="12" ry="6" fill="#ffffff" opacity="0.16" />
    </svg>
  );
}
