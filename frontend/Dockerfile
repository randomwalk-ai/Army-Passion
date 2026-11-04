# The screens. Built and run by docker-compose.prod.yml.

# --- 1. install packages ---
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- 2. build ---
FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked in at build time. Empty = same address as the page (Caddy routes /api).
ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_USER_NAME="Demo User"
ARG NEXT_PUBLIC_USER_ROLE="Administrator"
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_USER_NAME=$NEXT_PUBLIC_USER_NAME \
    NEXT_PUBLIC_USER_ROLE=$NEXT_PUBLIC_USER_ROLE \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- 3. run: only the standalone server and its files ---
FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
