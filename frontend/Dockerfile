# syntax=docker/dockerfile:1

FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html ./
COPY public ./public
COPY src ./src
COPY vite.config.js ./

# Same-origin /api via nginx — do not bake a remote API URL into the image
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

USER root
RUN apk add --no-cache curl \
    && rm -rf /usr/share/nginx/html/*
USER 101

# Official nginx image envsubst: templates → /etc/nginx/conf.d/
# Compose: backend:8000 | Azure Container Apps: backend (ingress :80)
ENV BACKEND_UPSTREAM=backend:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
