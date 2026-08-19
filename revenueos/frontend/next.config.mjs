/** @type {import('next').NextConfig} */

// No API rewrite here on purpose. Rewrites are baked into the build artifact,
// which freezes the backend address at build time; the proxy in
// app/api/[...path]/route.ts resolves it per request instead.
const nextConfig = {
  reactStrictMode: true,
};
export default nextConfig;
