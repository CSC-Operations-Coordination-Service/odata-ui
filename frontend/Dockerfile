FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Used by docker-compose.yml, with the source bind-mounted over /app.
FROM node:22-alpine AS dev
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
ENV NEXT_TELEMETRY_DISABLED=1
EXPOSE 3000
CMD ["npm", "run", "dev"]

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Next.js inlines NEXT_PUBLIC_* at build time, and this URL is resolved by the
# browser, not by the container - so it must be an address the user can reach.
# Pass "/" to build an environment-independent image whose requests are relative,
# for deployments that serve the UI and the API from one origin.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Sub-path the app is served under - see the comment in next.config.mjs. Baked in
# here because Next inlines it into every asset URL, link and rewrite.
#
# The two args are separate but MUST agree when a sub-path is used: BASE_PATH
# moves the server and its assets, NEXT_PUBLIC_API_URL moves the calls the browser
# makes with fetch(), which Next does not prefix for us. Set both to the ingress
# path, or neither.
ARG BASE_PATH=""
ENV BASE_PATH=$BASE_PATH

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

# Re-declared for the healthcheck below. The standalone server has basePath baked
# into its own bundle, so this value does NOT affect routing at runtime - it only
# tells the healthcheck which path actually answers.
ARG BASE_PATH=""
ENV BASE_PATH=$BASE_PATH

# Lets the reverse proxy wait for a frontend that can actually serve a request.
# Under a sub-path the root is a 404 - Next serves nothing outside basePath - so
# the probe has to ask for the prefix it was built with.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD wget -q -O /dev/null "http://127.0.0.1:3000${BASE_PATH}/" || exit 1

CMD ["node", "server.js"]
