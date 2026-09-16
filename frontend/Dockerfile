# Production frontend image — multi-stage.
#
# Stage 1 builds the Vite bundle INSIDE the image (`npm ci` against the
# committed lockfile), so host dependencies and host build output are never
# involved. frontend/.dockerignore additionally guarantees node_modules/ and
# dist/ from the host can never be copied in.
#
# Stage 2 serves the static build with nginx and reverse-proxies /api/ to the
# backend service on the compose network.

FROM node:22-alpine AS build
WORKDIR /app

# Dependencies first: this layer is cached until the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Application sources + build config, then the production build.
COPY . .
RUN npm run build

FROM nginx:1.27-alpine

# Serve the built SPA and proxy /api to http://backend:8000.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# Nginx serves the application; no internet access required.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
