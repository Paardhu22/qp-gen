import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  // Better Auth default cookie name is better-auth.session_token
  const sessionToken = request.cookies.get("better-auth.session_token");
  
  const isAuthPage = request.nextUrl.pathname.startsWith("/login") || 
                     request.nextUrl.pathname.startsWith("/register");
  
  const isDashboardPage = request.nextUrl.pathname.startsWith("/dashboard") ||
                          request.nextUrl.pathname.startsWith("/editor") ||
                          request.nextUrl.pathname.startsWith("/saved");

  if (isDashboardPage && !sessionToken) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (isAuthPage && sessionToken) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/editor/:path*",
    "/saved/:path*",
    "/login",
    "/register",
  ],
};
