# The single-page app, built in one stage and served as static files from another.
# The runtime image holds only dist/: no Node, no node_modules, no source.

FROM node:22-alpine AS build
WORKDIR /app
# Lockfile first so a source edit does not reinstall; scripts off, as in CI.
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

# Starts as uid 101 on port 8080, so nothing here runs as root. A stable branch (even minor)
# keeps getting patch releases; the 1.29 mainline tag stopped updating in May.
FROM nginxinc/nginx-unprivileged:1.30-alpine
# Root only to apply security fixes published since the base was built, then back to the
# numeric uid: runAsNonRoot checks cannot verify a user name.
USER root
RUN apk upgrade --no-cache
USER 101
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
