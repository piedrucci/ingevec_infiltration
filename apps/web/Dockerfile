FROM node:22-alpine

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm ci --include=optional \
    && sha256sum package-lock.json | cut -d ' ' -f 1 > node_modules/.ingevec-package-lock.sha256

COPY apps/web/ ./

EXPOSE 5173

CMD ["sh", "scripts/start-dev.sh"]
