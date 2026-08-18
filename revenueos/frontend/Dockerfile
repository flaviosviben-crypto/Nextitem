FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev || npm install --omit=dev

FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
# next.config.js rewrites are baked into routes-manifest.json at build time, so
# the API host has to be known here — not only at container start. It defaults
# to the compose service name and can be overridden with --build-arg.
ARG API_URL=http://backend:8000
ENV API_URL=$API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ARG API_URL=http://backend:8000
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 API_URL=$API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.js ./next.config.js
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
