# Capix Ingevec Backend

Backend para trazabilidad de postventa, importación controlada del Excel y procesamiento asíncrono de informes PDF.

## Entornos

| Entorno | Base de aplicación | Servicios locales |
| --- | --- | --- |
| development | Neon de desarrollo | API, worker, NATS, SeaweedFS, Keycloak y Superset |
| production | Neon de producción | Los mismos servicios en el VPS |

La base de aplicación nunca vive en el VPS. Las credenciales de Neon y Gemini son distintas en cada entorno y se inyectan mediante archivos de entorno no versionados.

## Inicio de desarrollo

1. Copiar `config/development.env.example` a `.env.development` y completar secretos.
2. Crear la base o rama Neon de desarrollo y ejecutar las migraciones: `docker compose --env-file .env.development run --rm api alembic upgrade head`.
3. Iniciar: `docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml up --build`.

La API queda en `http://localhost:8000`; la documentación en `/docs`.

### Comandos para iniciar y comprobar la API

Desde la raíz del repositorio, iniciar todos los servicios de desarrollo en primer plano:

```bash
docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml up --build
```

Para dejarlos ejecutándose en segundo plano:

```bash
docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml up -d --build
```

Comprobar que la API está disponible:

```bash
curl http://localhost:8000/health
```

La respuesta esperada es `{"status":"ok","environment":"development"}`. Consultar el estado y los logs de la API con:

```bash
docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml ps
docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml logs -f api
```

Detener los servicios con `docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml down`. Si el inicio falla indicando que el puerto `8080` está ocupado, otro proceso ya usa el puerto de Keycloak; la API puede seguir disponible en el puerto `8000`.

## Producción

Copiar `config/production.env.example` a un archivo protegido del servidor. Ejecutar `docker compose --env-file /ruta/production.env -f compose.yaml -f compose.prod.yaml up -d --build`.

Antes de producción se debe configurar el reverse proxy y los registros Cloudflare para `api.capix.cloud`, `auth.capix.cloud` y `bi.capix.cloud`.

## Importación Excel

Sólo un administrador puede llamar `POST /v1/imports/excel` con el archivo `.xlsx`. En v1 se procesa exclusivamente la hoja `Año 2026`; las hojas históricas se preservan en el archivo original pero no se cargan. El proceso almacena el archivo original en SeaweedFS privado, conserva cada fila como JSON auditable y normaliza las filas válidas. Una carga con el mismo SHA-256 es idempotente y no duplica registros.
