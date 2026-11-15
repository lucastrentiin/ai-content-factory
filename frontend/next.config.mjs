/** API servida pelo backend FastAPI; o Next encaminha /api/* para manter cookies no mesmo domínio. */
const backend = process.env.BACKEND_URL || "http://localhost:8000";

export default {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
