import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes that don't require authentication
const publicPaths = ["/login", "/signup", "/"];

// Routes that should redirect to dashboard when authenticated
const authRedirectPaths = ["/login", "/signup"];

export function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;
    const token = request.cookies.get("neural-auth-token")?.value;

    // If user is on login/signup and has a valid token → redirect to dashboard
    if (authRedirectPaths.some((p) => pathname.startsWith(p)) && token) {
        return NextResponse.redirect(new URL("/", request.url));
    }

    // If user is on a protected page and has no token → redirect to login
    if (!publicPaths.some((p) => pathname === p) && !token) {
        // Allow Next.js internals and static files through
        if (
            pathname.startsWith("/_next") ||
            pathname.startsWith("/api") ||
            pathname.startsWith("/landing") ||
            pathname.includes(".")
        ) {
            return NextResponse.next();
        }
        return NextResponse.redirect(new URL("/login", request.url));
    }

    return NextResponse.next();
}

export const config = {
    matcher: [
        /*
         * Match all request paths except:
         * - _next/static (static files)
         * - _next/image (image optimization)
         * - favicon.ico
         */
        "/((?!_next/static|_next/image|favicon.ico).*)",
    ],
};
