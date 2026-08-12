import type { NextConfig } from "next";

/**
 * Static export, not a Node server.
 *
 * The console is a pure client of the FastAPI app - it has no server-side
 * data needs of its own - so exporting to static files keeps the deployment
 * story the same as before: one process (uvicorn) serving one URL. FastAPI
 * mounts ./out at /ui, which is why basePath is /ui here.
 *
 * Dev:  npm run dev   -> http://localhost:3000/ui  (talks to :8000 via NEXT_PUBLIC_API_BASE)
 * Prod: npm run build -> ./out, served by FastAPI at http://localhost:8000/ui
 */
const nextConfig: NextConfig = {
  output: "export",
  basePath: "/ui",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
