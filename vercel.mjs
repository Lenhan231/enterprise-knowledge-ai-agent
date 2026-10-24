const ngrokUrl = process.env.NGROK_URL;
if (!ngrokUrl) {
  throw new Error("Set NGROK_URL in Vercel project settings.");
}

const backendUrl = new URL(ngrokUrl);

if (backendUrl.protocol !== "https:" || backendUrl.username || backendUrl.password) {
  throw new Error("Set NGROK_URL to the HTTPS origin of the local backend tunnel in Vercel project settings.");
}

export const config = {
  outputDirectory: "src/app/static",
  rewrites: [
    { source: "/api/:path*", destination: `${backendUrl.origin}/api/:path*` },
    { source: "/static/:path*", destination: "/:path*" },
  ],
  headers: [
    {
      source: "/api/:path*",
      headers: [{ key: "x-vercel-enable-rewrite-caching", value: "0" }],
    },
  ],
};
