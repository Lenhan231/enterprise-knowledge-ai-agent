export const config = {
  // Rebuild trigger: keep Vercel's proxy config in the deployment source root.
  "$schema": "https://openapi.vercel.sh/vercel.json",
  framework: null,
  buildCommand: "",
  installCommand: "",
  outputDirectory: ".",
  rewrites: [
    { source: "/api/:path*", destination: `${process.env.NGROK_URL}/api/:path*` },
    { source: "/ws/:path*", destination: `${process.env.NGROK_URL}/ws/:path*` },
    { source: "/static/:path*", destination: "/:path*" },
  ],
};
