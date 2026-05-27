import { NextRequest, NextResponse } from "next/server";

/**
 * Edge middleware — runs before the route resolver, sees the *decoded* pathname.
 *
 * Job 1: redirect /cazar/señales (with eñe, or its percent-encoded form
 *        /cazar/se%C3%B1ales) → /cazar/senales.
 *        The on-disk route is ASCII-only because Next.js 15 SSRs non-ASCII
 *        paths with `useSearchParams` as 500 instead of 404 — confusing.
 *        next.config.ts `redirects()` does NOT catch percent-encoded sources
 *        reliably, so we handle it here.
 */
export function middleware(req: NextRequest) {
  // req.nextUrl.pathname is already URL-decoded by Next, so an incoming
  // request for /cazar/se%C3%B1ales surfaces here as /cazar/señales.
  const pathname = req.nextUrl.pathname;

  if (pathname === "/cazar/señales" || pathname.startsWith("/cazar/señales/")) {
    const url = req.nextUrl.clone();
    url.pathname = pathname.replace("/cazar/señales", "/cazar/senales");
    return NextResponse.redirect(url, 308);
  }

  return NextResponse.next();
}

export const config = {
  // Only run on /cazar/* — avoid the cost of invoking middleware for assets,
  // _next/static, favicon, etc.
  matcher: ["/cazar/:path*"],
};
