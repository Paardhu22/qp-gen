import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/editor/:path*",
    "/saved/:path*",
    "/settings/:path*",
    "/history/:path*",
    "/login",
    "/register",
  ],
};
