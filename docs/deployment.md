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
5. Configura MIGRATION_DATABASE_URL con el endpoint directo y session-capable
   de Neon; el gate mantiene un advisory lock de PostgreSQL.
6. Valida los overlays Compose y realiza una primera actualización supervisada.
   El servicio migrate usa la misma imagen que API y worker, que esperan a que
   la migración finalice correctamente.
7. Comprueba public.alembic_version, las lecturas autenticadas afectadas y
   https://api.capix.cloud/health.

## Migraciones en cada despliegue

El Compose de producción define un servicio migrate de ejecución única. Antes
de que API o worker nuevos arranquen, el servicio toma un advisory lock de
PostgreSQL, vuelve a leer el historial, valida toda la cadena pendiente contra
apps/api/migrations/migration_policy.json y ejecuta sólo revisiones marcadas
auto_apply. La lista vacía actual es intencional: las revisiones no se aplican
automáticamente hasta que se revisen y clasifiquen. Agrega cada nueva revisión
al manifiesto sólo después de verificar que es compatible con la versión de
aplicación todavía activa.

MIGRATION_DATABASE_URL debe usar el endpoint de Neon que mantenga una sesión
PostgreSQL durante el advisory lock, con los mismos permisos y base que
DATABASE_URL. No imprimas ni confirmes la URL real. Una migración fallida,
historial desconocido, varias cabezas, revisión no clasificada o política
inconsistente bloquea el inicio de API y worker y falla el despliegue. El CLI no
hace stamp, downgrade, retry automático ni imports de JSON.

Usa despliegues Dokploy serializados: no debe comenzar una versión anterior
mientras otra actualización esté aplicando cambios o reemplazando contenedores.
Verifica en el Dokploy instalado que cada up vuelva a iniciar el servicio
migrate completado y que su salida distinta de cero marque el despliegue como
fallido. La documentación pública de Dokploy permite definir un comando Compose
personalizado que reemplaza el predeterminado; conserva el comando completo y
los argumentos de overlays, proyecto y redes si se cambia. El gate de Compose no
promete reemplazo atómico ni que los contenedores anteriores sigan disponibles
si la actualización falla.

Antes de activar el gate en producción, ensáyalo en un deployment separado con
una base desechable: primer arranque, redeploy sin cambios, nueva imagen,
migración fallida y rechazo de una revisión manual/no clasificada. Prueba
además las rutas autenticadas de lista/detalle de ítems, ítems por categoría,
dashboard y vistas analíticas; un /health exitoso no basta para demostrar que
las consultas funcionan.

Las revisiones 20261008_0023 y 20261008_0024 permanecen manuales. Sigue
docs/cause-category-split.md para preparar la revisión 0023. La revisión 0024
elimina catálogo y datos de item type; requiere un punto de recuperación Neon
verificado y una ventana coordinada con el código. Si el código antiguo aún
consulta esa columna, detén API y worker antes de aplicar la migración y vuelve
a iniciarlos sólo con una versión compatible. Nunca agregues una revisión de
preparación de datos al manifiesto automático.

Para aplicar manualmente la 0024 cuando producción esté exactamente en la
0023, detén API y worker desde Dokploy, crea el punto de recuperación Neon y
ejecuta desde la carpeta del proyecto en el VPS:

```bash
docker compose --env-file .env -f compose.yaml -f compose.prod.yaml stop api pdf-worker
docker compose --env-file .env -f compose.yaml -f compose.prod.yaml run --rm --no-deps migrate alembic upgrade 20261008_0024
docker compose --env-file .env -f compose.yaml -f compose.prod.yaml up -d api pdf-worker
```

Configura ENV_FILE=.env en el entorno de Dokploy. El segundo comando usa
MIGRATION_DATABASE_URL a través de Alembic y ejecuta sólo la revisión
solicitada; el tercer comando vuelve a pasar por el gate, que debe mostrar la
base en la revisión del release. Si la base no está exactamente en 0023 o el
comando falla, detente y revisa el historial y el runbook antes de continuar.

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
