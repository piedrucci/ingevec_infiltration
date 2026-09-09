# Despliegue de producción

## Separación obligatoria

Crear una base o rama Neon exclusiva para `production` y otra para `development`. Crear las credenciales de aplicación con privilegios mínimos; `superset_ro` obtiene sólo `USAGE` sobre `analytics` y `SELECT` sobre las vistas publicadas.

Los secretos se almacenan únicamente en el archivo de entorno protegido del VPS. No se suben al repositorio ni se copian entre entornos: `DATABASE_URL`, claves S3, `GEMINI_API_KEY`, contraseña de Keycloak y secreto de Superset son distintos por entorno.

## Cloudflare y TLS

Crear registros proxied para `api.capix.cloud`, `auth.capix.cloud` y `bi.capix.cloud`. Instalar un certificado Cloudflare Origin CA en `infra/caddy/certs/` del VPS (fuera del repositorio) y ajustar el Caddyfile para usarlo. Mantener Cloudflare en modo **Full (strict)**.

No publicar puertos de NATS, SeaweedFS, Keycloak DB ni la base de aplicación. Sólo 80 y 443 llegan al VPS y son atendidos por Caddy.

## Primer arranque

1. Generar un certificado Cloudflare Origin CA para `*.capix.cloud` y copiarlo, fuera de Git, a `infra/caddy/certs/capix.cloud.crt` y `infra/caddy/certs/capix.cloud.key`.
2. Crear el realm `ingevec-production`; Compose importa la plantilla `infra/keycloak/realm-production.json` en el primer arranque.
3. Crear el usuario administrador y el usuario viewer con los valores `KEYCLOAK_INITIAL_*` del archivo de entorno protegido. Asignar `admin` al primero y `viewer` al segundo.
4. Crear los grupos `/superset/division/<division_id>` y `/superset/project/<project_id>` según las asignaciones de acceso. Asignar `superset_admin` al administrador y `superset_viewer` más sus grupos al viewer.
5. Copiar `infra/seaweedfs/s3.production.json.example` a `infra/seaweedfs/s3.json` en el VPS, reemplazar sus credenciales y mantener el archivo fuera de Git. Crear el bucket privado `capix-documents-production` con esas mismas credenciales.
6. Ejecutar la migración Alembic contra Neon.
7. Crear el usuario `superset_ro` y conceder acceso sólo a `analytics`.
8. Levantar Compose y comprobar `/health` desde Cloudflare.

## Recuperación

Neon conserva su propia política de restauración. Además se debe respaldar diariamente el volumen de SeaweedFS y el volumen de Keycloak a almacenamiento externo. La restauración se prueba primero en desarrollo.
