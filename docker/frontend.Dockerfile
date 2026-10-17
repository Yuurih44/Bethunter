FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build
FROM nginxinc/nginx-unprivileged:1.28-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/limits.conf /etc/nginx/conf.d/limits.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
