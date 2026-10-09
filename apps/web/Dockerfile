FROM node:22-alpine

WORKDIR /app

COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN corepack enable \
    && corepack prepare pnpm@11.14.0 --activate \
    && pnpm install --frozen-lockfile \
    && sha256sum package.json pnpm-lock.yaml | sha256sum | cut -d ' ' -f 1 > node_modules/.ingevec-pnpm-lock.sha256

COPY apps/web/ ./

EXPOSE 5173

CMD ["sh", "scripts/start-dev.sh"]
