import { NextRequest, NextResponse } from "next/server";

/**
 * Edge middleware — runs before Next's route resolver.
 *
 * Job: redirect any variant of "/cazar/señales" → "/cazar/senales".
 *
 * We have to deal with FOUR wire formats the browser can produce for the eñe:
 *   - %C3%B1   (UTF-8, modern browsers — standard)
 *   - %F1      (ISO-8859-1 / Latin-1, some older Windows browsers, curl on
 *              non-UTF-8 shells)
 *   - ñ        (already decoded in some Next 15 paths via req.nextUrl.pathname)
 *   - señales  (literal in code-paths)
 *
 * Both percent-encoded forms cause Next 15 to throw an unhandled 500 inside
 * its route resolver instead of giving us a clean 404 (likely because the
 * decoded path no longer corresponds to a file-system route). So we match on
 * the RAW URL (req.url) before any decoding happens, and only fall back to
 * the decoded pathname for the literal-character cases.
 */
export function middleware(req: NextRequest) {
  // Look at the raw URL — req.url is the absolute URL string Next received.
  const rawUrl = req.url;

  // Strip protocol+host so we only see the path+query+hash portion.
  // We can't use `new URL(rawUrl)` here because Latin-1 percent-encoded paths
  // like /cazar/se%F1ales are invalid UTF-8 and URL() throws.
  const hostMatch = rawUrl.match(/^https?:\/\/[^/]+/);
  const pathAndQuery = hostMatch ? rawUrl.slice(hostMatch[0].length) : rawUrl;

  // Match any encoding variant of /cazar/señales (with or without trailing path).
  const senalesRegex =
    /^\/cazar\/(?:se%C3%B1ales|se%F1ales|señales)(\/.*)?(\?.*)?(#.*)?$/i;
  const m = pathAndQuery.match(senalesRegex);
  if (m) {
    const rest = m[1] || "";
    const query = m[2] || "";
    const hash = m[3] || "";
    const target = `/cazar/senales${rest}${query}${hash}`;
    // Build absolute URL for the redirect destination.
    const host = hostMatch ? hostMatch[0] : "";
    return NextResponse.redirect(`${host}${target}`, 308);
  }

  return NextResponse.next();
}

export const config = {
  // Run on every path except Next.js internals and static assets.
  // We cannot scope tightly to /cazar/* because path-to-regexp matchers can
  // misbehave on percent-encoded non-ASCII segments (e.g. /cazar/se%F1ales)
  // and skip the middleware entirely. A wide matcher + cheap regex check
  // inside is safer than missing a redirect.
  matcher: ["/((?!_next/|favicon.ico|api/).*)"],
};
