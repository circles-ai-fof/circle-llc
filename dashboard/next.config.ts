import type { NextConfig } from "next";

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
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  poweredByHeader: false,
};

export default nextConfig;
