const ngrokUrl = process.env.NGROK_URL;
if (!ngrokUrl) {
  throw new Error("Set NGROK_URL in Vercel project settings.");
}

const backendUrl = new URL(ngrokUrl);
// Optional second backend (e.g. the VPS while the home PC is primary). Unset, /api-fallback is the primary again.
const fallbackUrl = new URL(process.env.FALLBACK_URL || ngrokUrl);

if (backendUrl.protocol !== "https:" || backendUrl.username || backendUrl.password) {
  throw new Error("Set NGROK_URL to the HTTPS origin of the local backend tunnel in Vercel project settings.");
}
if (fallbackUrl.protocol !== "https:" || fallbackUrl.username || fallbackUrl.password) {
  throw new Error("Set FALLBACK_URL to an HTTPS origin, or leave it unset.");
}

export const config = {
  framework: null,
  buildCommand: null,
  installCommand: null,
  outputDirectory: "src/app/static",
  rewrites: [
    { source: "/api/:path*", destination: `${backendUrl.origin}/api/:path*` },
    { source: "/api-fallback/:path*", destination: `${fallbackUrl.origin}/api/:path*` },
    { source: "/static/:path*", destination: "/:path*" },
  ],
  headers: [
    ...["/api/:path*", "/api-fallback/:path*"].map((source) => ({
      source,
      headers: [{ key: "x-vercel-enable-rewrite-caching", value: "0" }],
    })),
  ],
};
