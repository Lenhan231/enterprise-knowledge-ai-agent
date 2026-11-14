import { deploymentEnv, routes, type VercelConfig } from "@vercel/config/v1";

const backendUrl = deploymentEnv("NGROK_URL");
const fallbackUrl = process.env.FALLBACK_URL ? deploymentEnv("FALLBACK_URL") : backendUrl;
const fallback2Url = process.env.FALLBACK_2_URL ? deploymentEnv("FALLBACK_2_URL") : fallbackUrl;

export const config: VercelConfig = {
  "$schema": "https://openapi.vercel.sh/vercel.json",
  framework: null,
  buildCommand: "",
  outputDirectory: ".",
  trailingSlash: false,
  rewrites: [
    routes.rewrite("/api/:path*", `${backendUrl}/api/:path*`),
    routes.rewrite("/api-fallback/:path*", `${fallbackUrl}/api/:path*`),
    routes.rewrite("/api-fallback-2/:path*", `${fallback2Url}/api/:path*`),
    routes.rewrite("/ws/:path*", `${backendUrl}/ws/:path*`),
    routes.rewrite("/static/:path*", "/:path*"),
  ],
};
