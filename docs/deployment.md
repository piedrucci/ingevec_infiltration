# Despliegue de producción

## Separación obligatoria

Crear una base o rama Neon exclusiva para `production` y otra para `development`. Crear las credenciales de aplicación con privilegios mínimos; `superset_ro` obtiene sólo `USAGE` sobre `analytics` y `SELECT` sobre las vistas publicadas.

Los secretos se almacenan únicamente en el archivo de entorno protegido del VPS. No se suben al repositorio ni se copian entre entornos: `DATABASE_URL`, claves S3, `GEMINI_API_KEY`, contraseña de Keycloak y secreto de Superset son distintos por entorno.

## Cloudflare y TLS

Crear registros proxied para `api.capix.cloud`, `auth.capix.cloud` y `bi.capix.cloud`. Instalar un certificado Cloudflare Origin CA en `infra/caddy/certs/` del VPS (fuera del repositorio) y ajustar el Caddyfile para usarlo. Mantener Cloudflare en modo **Full (strict)**.

No publicar puertos de NATS, SeaweedFS, Keycloak DB ni la base de aplicación. Sólo 80 y 443 llegan al VPS y son atendidos por Caddy.

## Primer arranque

1. Crear el realm de Keycloak y los roles `viewer` y `admin`.
2. Configurar clientes OIDC para API y Superset, usando las URL públicas del dominio.
3. Crear bucket privado de SeaweedFS para documentos del entorno.
4. Ejecutar la migración Alembic contra Neon.
5. Crear el usuario `superset_ro` y conceder acceso sólo a `analytics`.
6. Levantar Compose y comprobar `/health` desde Cloudflare.

## Recuperación

Neon conserva su propia política de restauración. Además se debe respaldar diariamente el volumen de SeaweedFS y el volumen de Keycloak a almacenamiento externo. La restauración se prueba primero en desarrollo.

