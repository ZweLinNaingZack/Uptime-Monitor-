# The frontend as a container image, built in three stages. Each stage starts clean, and
# only what the last one copies ends up in the final image, which keeps it small.
# See node_modules/next/dist/docs/01-app/02-guides/self-hosting.md.

# 1. Install dependencies, exactly as package-lock.json lists them.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# 2. Build.
FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# The address your BROWSER uses to reach the backend. NEXT_PUBLIC_ values are written into
# the JavaScript during the build, so changing it means rebuilding the image.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_OUTPUT=standalone \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# 3. Run. The "standalone" build holds just the server and the packages it really uses.
FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The standalone server doesn't include the static files (JavaScript, CSS) by default, so
# they're copied next to it, where server.js looks for them.
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
# The node image comes with an ordinary user called "node". Use it instead of root.
USER node
EXPOSE 3000
CMD ["node", "server.js"]
