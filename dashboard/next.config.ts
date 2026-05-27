import type { NextConfig } from "next";
import * as path from "path";

// CSP connect-src: allow the production API + the dev backend on any localhost
// port. NEXT_PUBLIC_API_URL must also be allowed since /cazar and /leads call
// it directly from the browser.
const isDev = process.env.NODE_ENV !== "production";
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
const connectSrcParts = [
  "'self'",
  "https://api.circles-ai.ai",
  "https://circle-llc-production.up.railway.app",
];
if (apiUrl) connectSrcParts.push(apiUrl);
if (isDev) {
  // Any localhost port + ws for HMR
  connectSrcParts.push("http://localhost:*", "ws://localhost:*", "http://127.0.0.1:*");
}
const connectSrc = Array.from(new Set(connectSrcParts)).join(" ");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "geolocation=(), microphone=(), camera=()",
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "font-src 'self' data:",
      `connect-src ${connectSrc}`,
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  // Force the workspace root to THIS dashboard directory.
  //
  // Without this, Next.js walks up looking for the nearest package-lock.json
  // and picks `D:\CM\IA_2026\ClaudeCode\package-lock.json` (a sibling project's
  // lockfile) as the workspace root. Module resolution then breaks at runtime
  // with "Internal Server Error" on SSR-rendered routes.
  //
  // path.resolve(__dirname, ...) doesn't work in ESM-style configs, but Next
  // injects __dirname when loading next.config.ts. As a safer alternative we
  // use process.cwd() — when you run `npm run dev` from dashboard/ this is
  // already the dashboard directory.
  outputFileTracingRoot: path.resolve(process.cwd()),

  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },

  // Permanent redirects for friendly URL variants.
  // The file-system route is /cazar/senales (no eñe) because Next.js handles
  // non-ASCII URLs poorly across browsers (historial autocomplete returns
  // percent-encoded /cazar/se%C3%B1ales and the SSR layer 500's instead of
  // 404'ing). Redirect catches those variants — and any external link that
  // used the eñe — back to the canonical path.
  async redirects() {
    return [
      { source: "/cazar/señales", destination: "/cazar/senales", permanent: true },
      { source: "/cazar/señales/:path*", destination: "/cazar/senales/:path*", permanent: true },
    ];
  },

  poweredByHeader: false,
};

export default nextConfig;
