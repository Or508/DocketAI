# The Next.js app. Built from the repository root, because it uses the shared-types workspace:
#   docker build -f deploy/web.Dockerfile .
FROM node:22-alpine AS build
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json
RUN npm ci --workspaces --include-workspace-root
COPY packages/shared-types packages/shared-types
COPY apps/web apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build -w web

FROM node:22-alpine
WORKDIR /repo
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
COPY --from=build /repo /repo
USER node
EXPOSE 3000
# PORT: Render sets its own. API_INTERNAL_HOSTPORT: Render gives the private API as host:port, without http://.
CMD ["sh", "-c", "if [ -z \"$API_INTERNAL_URL\" ] && [ -n \"$API_INTERNAL_HOSTPORT\" ]; then export API_INTERNAL_URL=\"http://$API_INTERNAL_HOSTPORT\"; fi; exec npm run start -w web -- -p \"${PORT:-3000}\" -H 0.0.0.0"]
