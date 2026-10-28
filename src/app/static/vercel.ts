import { deploymentEnv, routes, type VercelConfig } from "@vercel/config/v1";

const backendUrl = deploymentEnv("NGROK_URL");

export const config: VercelConfig = {
  "$schema": "https://openapi.vercel.sh/vercel.json",
  framework: null,
  buildCommand: "",
  outputDirectory: ".",
  trailingSlash: false,
  rewrites: [
    routes.rewrite("/api/:path*", `${backendUrl}/api/:path*`),
    routes.rewrite("/ws/:path*", `${backendUrl}/ws/:path*`),
    routes.rewrite("/static/:path*", "/:path*"),
  ],
};
