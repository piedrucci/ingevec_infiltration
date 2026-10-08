# Despliegue de producción con Dokploy

## Arquitectura

GitHub es la fuente de verdad del código y Dokploy obtiene el repositorio y ejecuta
los overlays de Docker Compose. Dokploy/Traefik es el único reverse proxy público;
no se ejecuta Caddy en producción. En Dokploy configura estos destinos internos:

| Dominio | Servicio | Puerto |
| --- | --- | ---: |
| `app.capix.cloud` | `web` | 80 |
| `api.capix.cloud` | `api` | 8000 |
| `auth.capix.cloud` | `keycloak` | 8080 |
| `bi.capix.cloud` | `superset` | 8088 |

En Cloudflare crea registros proxied para los cuatro dominios y usa **Full
(strict)**. Permite que Dokploy gestione los certificados de origen mediante
Traefik/Let's Encrypt; no copies certificados de Caddy.

## Configuración inicial

Mantén una rama/base Neon y credenciales separadas para `production`. La cuenta
de lectura `superset_ro` debe tener sólo `USAGE` sobre `analytics` y `SELECT`
sobre las vistas publicadas.

1. En Dokploy crea un proyecto desde el repositorio de GitHub y selecciona
   `compose.yaml` con `compose.prod.yaml` como archivo adicional.
2. Configura `APP_ENV=production` y carga los valores secretos de
   `.env.production` directamente en Dokploy. Como Dokploy escribe ese entorno
   en `.env`, usa `ENV_FILE=.env` y
   `SEAWEEDFS_CONFIG_FILE=../files/seaweedfs/s3.json`. Nunca confirmes secretos
   en Git. Define también `VITE_KEYCLOAK_URL=https://auth.capix.cloud`,
   `VITE_KEYCLOAK_REALM=ingevec-production` y
   `VITE_KEYCLOAK_CLIENT_ID=ingevec-web`; Vite los incorpora durante el build.
3. En **Advanced → Mounts** crea un File Mount en
   `files/seaweedfs/s3.json`, usando como contenido la plantilla
   `infra/seaweedfs/s3.production.json.example` con credenciales nuevas, y crea
   el bucket privado `capix-documents-production`.
4. Configura volúmenes persistentes para `nats_data`, `redis_data`,
   `seaweedfs_data`, `keycloak_data`, `superset_db_data` y `superset_home`.
5. Ejecuta una tarea temporal de migración con `api`: `alembic upgrade head`.
6. Levanta el stack y verifica `https://api.capix.cloud/health`.

Keycloak importa `infra/keycloak/realm-production.json` en el primer arranque.
Después crea los usuarios y grupos de producción y asigna los roles `admin`,
`viewer`, `superset_admin` y `superset_viewer` según corresponda.

## Operación y recuperación

Alembic mantiene el historial en `public.alembic_version`, con
`version_table_schema="public"` configurado explícitamente en
`apps/api/migrations/env.py`. Esto permite ejecutar migraciones aunque la conexión
de la aplicación use `search_path=app`. Si Alembic intenta ejecutar la migración
inicial sobre una base existente, verifica el historial y la conexión antes de
reintentar; no uses `alembic stamp` para ocultar la discrepancia.

Usa redeploy desde Dokploy después de cada versión publicada. Antes de actualizar,
confirma que los volúmenes persistentes están incluidos en los snapshots de
Hostinger. Neon mantiene la recuperación de las bases de aplicación y Superset;
prueba la restauración de SeaweedFS y Keycloak primero en un entorno separado.

El worker PDF consume JetStream de forma bloqueante y no consulta Neon mientras
espera eventos. La API intenta publicar cada evento inmediatamente después de
confirmar la transacción; si NATS no está disponible, el registro persistente de
outbox queda pendiente para recuperación. No programes una tarea periódica de
reconciliación en Dokploy: cada ejecución consulta la base y puede reactivar el
compute de Neon. Así Neon puede suspender el compute cuando no hay actividad,
según la configuración del endpoint.

Ejecuta `python -m app.worker.reconcile` manualmente solo para recuperar eventos
de outbox que quedaron pendientes (por ejemplo, tras una interrupción de NATS).
El equivalente desde Docker Compose es:

```bash
docker compose -f compose.yaml -f compose.prod.yaml exec -T api python -m app.worker.reconcile
```

La carga normal de PDFs debe pasar siempre por la API. Si se copiaron objetos
directamente a `incoming/`, ejecuta excepcionalmente:

```bash
docker compose -f compose.yaml -f compose.prod.yaml exec -T api python -m app.worker.reconcile --scan-storage
```

## Importar asociaciones de causas

El comando `app.commands.import_category_causes` reemplaza todas las filas de
`app.failure_cause_category_link` usando un JSON que mapea códigos de categoría
a arrays de códigos de causa. Los códigos inexistentes se omiten, se reportan
como advertencias y no provocan un estado de salida distinto de cero.

Primero valida el archivo sin modificar la base:

```bash
docker compose --env-file .env.development \
  -f compose.yaml -f compose.dev.yaml \
  run --rm -v "$PWD/docs:/docs:ro" api \
  python -m app.commands.import_category_causes \
  /docs/category_and_causes.json --dry-run
```

Para aplicar el reemplazo en desarrollo, elimina `--dry-run`. En producción,
monta el archivo JSON como un volumen de solo lectura y ejecuta el mismo
comando con los archivos Compose de producción después de revisar el resumen.
