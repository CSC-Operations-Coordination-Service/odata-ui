/** @type {import('next').NextConfig} */

// The sub-path this app is served under, e.g. /odata-ui/frontend behind the swarm
// Traefik ingress. Empty (the default) serves from the root, which is what
// development uses.
//
// This is a BUILD-time value: Next inlines it into every emitted asset URL, every
// <Link> and every rewrite, so it cannot be changed on a running container - it is
// passed as the BASE_PATH build arg and baked into the image, exactly like
// NEXT_PUBLIC_API_URL. It must match the ingress route, and the ingress must NOT
// strip the prefix: Next expects to receive the full path it was built for.
//
// Skipping this and only adding a proxy rule is the classic failure - the HTML
// loads, then the browser asks for /_next/static/... at the host root, which the
// router does not match, and the page renders with no CSS and no JS.
const basePath = (process.env.BASE_PATH || "").replace(/\/+$/, "");

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,

  basePath,

  // Proxies browser API calls through this server to the backend, so the backend
  // needs no published port and the browser never addresses it directly.
  //
  // Rewrites are resolved when the config is loaded: at build time for the
  // standalone production server, at startup for `next dev`. The default is
  // therefore the compose/stack service name, which is correct inside Docker;
  // set BACKEND_INTERNAL_URL for a bare `npm run dev` on the host.
  //
  // `source` is automatically prefixed with basePath, so under the ingress this
  // matches /odata-ui/frontend/api/*. `destination` is an absolute URL and is
  // left alone, so the backend keeps serving /api/* unprefixed - it knows nothing
  // about the sub-path. NEXT_PUBLIC_API_URL is what makes the browser ask for the
  // prefixed path in the first place; the two have to agree.
  async rewrites() {
    const backend = process.env.BACKEND_INTERNAL_URL || "http://backend:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
