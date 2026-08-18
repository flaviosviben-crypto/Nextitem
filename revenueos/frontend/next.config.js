/** @type {import('next').NextConfig} */
const API = process.env.API_URL || "http://127.0.0.1:8000";

module.exports = {
  reactStrictMode: true,
  // The browser always calls same-origin /api/*; Next proxies to FastAPI.
  // This keeps the API host (and any future auth header) out of the client bundle.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};
