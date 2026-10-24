const ngrokUrl = process.env.NGROK_URL;
if (!ngrokUrl) throw new Error("NGROK_URL is required to configure the API proxy");
const backendUrl = ngrokUrl.replace(/\/+$/, "");

export const config = {
  // Rebuild trigger: keep Vercel's proxy config in the deployment source root.
  "$schema": "https://openapi.vercel.sh/vercel.json",
  framework: null,
  buildCommand: "",
  installCommand: "",
  outputDirectory: ".",
  rewrites: [
    { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
    { source: "/ws/:path*", destination: `${backendUrl}/ws/:path*` },
    { source: "/static/:path*", destination: "/:path*" },
  ],
};
