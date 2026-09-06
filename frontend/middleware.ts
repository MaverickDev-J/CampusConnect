import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes that don't require authentication
const publicPaths = ["/login", "/signup", "/"];
const authRedirectPaths = ["/login", "/signup"];

export function middleware(request: NextRequest) {
    try {
        const { pathname } = request.nextUrl;

        // Skip static files, Next.js internal paths, and landing
        if (
            pathname.startsWith("/_next") ||
            pathname.startsWith("/api") ||
            pathname.startsWith("/landing") ||
            pathname.includes(".") ||
            pathname === "/favicon.ico"
        ) {
            return NextResponse.next();
        }

        const token = request.cookies.get("neural-auth-token")?.value;

        // If user is on login/signup and has a valid token → redirect to dashboard
        if (authRedirectPaths.some((p) => pathname.startsWith(p)) && token) {
            const url = request.nextUrl.clone();
            url.pathname = "/";
            return NextResponse.redirect(url);
        }

        // If user is on a protected page and has no token → redirect to login
        if (!publicPaths.some((p) => pathname === p) && !token) {
            const url = request.nextUrl.clone();
            url.pathname = "/login";
            return NextResponse.redirect(url);
        }

        return NextResponse.next();
    } catch (err) {
        console.error("Middleware invocation error:", err);
        return NextResponse.next();
    }
}

export const config = {
    matcher: [
        "/((?!_next/static|_next/image|favicon.ico).*)",
    ],
};
