const ngrokUrl = process.env.NGROK_URL;
if (!ngrokUrl || ngrokUrl === "[SENSITIVE]") {
  throw new Error("Set NGROK_URL in Vercel project settings to the public HTTPS backend URL.");
}
const backendUrl = new URL(ngrokUrl);
if (
  backendUrl.protocol !== "https:" || backendUrl.username || backendUrl.password
  || !/^\/+$/u.test(backendUrl.pathname) || backendUrl.search || backendUrl.hash
) {
  throw new Error("NGROK_URL must be the public HTTPS backend origin, with no path, query, or credentials.");
}
const backendOrigin = backendUrl.origin;

export const config = {
  // Rebuild trigger: keep Vercel's proxy config in the deployment source root.
  "$schema": "https://openapi.vercel.sh/vercel.json",
  framework: null,
  buildCommand: "",
  installCommand: "",
  outputDirectory: ".",
  rewrites: [
    { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` },
    { source: "/ws/:path*", destination: `${backendOrigin}/ws/:path*` },
    { source: "/static/:path*", destination: "/:path*" },
  ],
};
