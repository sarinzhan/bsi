# BSI web: the React app as static files, served by nginx, which also forwards /api to platform-api.
# Build from this folder:  docker build -t registry/bsi/web:<version> .

FROM node:22.20.0-alpine3.22 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# where the app is served, e.g. /bsi/ behind a shared nginx. Baked into the build.
ARG BSI_BASE_PATH=/
RUN BSI_BASE_PATH="$BSI_BASE_PATH" npm run build \
 && chmod -R a+rX dist nginx   # readable by nginx whatever the file modes were where the image was built

# unprivileged nginx: runs as a non-root user, listens on 8080
FROM nginxinc/nginx-unprivileged:1.28.0-alpine
COPY --from=build /app/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/nginx/locations.conf /app/nginx/security-headers.conf /etc/nginx/snippets/
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
