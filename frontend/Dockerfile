FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Proxy /api to the backend container (compose network).
RUN printf 'server { \
    listen 80; \
    location /api/ { proxy_pass http://backend:8000; proxy_set_header Host $host; } \
    location / { root /usr/share/nginx/html; try_files $uri /index.html; } \
  }\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80
