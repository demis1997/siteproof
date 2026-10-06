FROM node:22-bookworm-slim AS build
WORKDIR /app/apps/web
COPY apps/web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
COPY packages/contracts/ /app/packages/contracts/
RUN npm run build
FROM node:22-bookworm-slim
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build /app/apps/web/.next/standalone ./
COPY --from=build /app/apps/web/.next/static ./.next/static
COPY --from=build /app/apps/web/app/preview.css ./app/preview.css
USER node
EXPOSE 3000
CMD ["node", "server.js"]
