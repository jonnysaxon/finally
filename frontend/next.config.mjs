/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  // Static export: no Image Optimization server, so disable it.
  images: { unoptimized: true },
  // Backend serves the export from /app/static at the root; relative asset
  // paths keep us origin-agnostic.
  trailingSlash: false,
  reactStrictMode: true,
};

export default nextConfig;
