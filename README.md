# Capix Ingevec Backend

Backend para trazabilidad de postventa, importación controlada del Excel y procesamiento asíncrono de informes PDF.

## Entornos

| Entorno | Base de aplicación | Servicios locales |
| --- | --- | --- |
| development | Neon de desarrollo | API, worker, NATS, Redis, SeaweedFS, Keycloak y Superset |
| production | Neon de producción | Los mismos servicios en el VPS |

La base de aplicación nunca vive en el VPS. Las credenciales de Neon y Gemini son distintas en cada entorno y se inyectan mediante archivos de entorno no versionados.

## Inicio de desarrollo

1. Copiar `config/development.env.example` a `.env.development` y completar secretos.
2. Crear la base o rama Neon de desarrollo y ejecutar las migraciones: `docker compose --env-file .env.development run --rm api alembic upgrade head`.
3. Iniciar: `docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml up --build`.

La API queda en `http://localhost:8000`; la documentación en `/docs`.
La UI administrativa queda en `http://localhost:5173` y redirige a Keycloak al abrirla.

### Caché del inicio

Redis es interno (sin puerto publicado) y se inicia junto con Compose. El endpoint
`GET /v1/dashboard/summary` guarda sus agregados durante cinco minutos y se
invalida al importar datos o cambiar documentos/asociaciones. Puede ajustarse con
`DASHBOARD_CACHE_TTL_SECONDS`; si Redis no responde, la API consulta Neon sin
interrumpir la UI.

### Superset local

Superset queda disponible en `http://localhost:8088`. Sus metadatos (usuarios,
dashboards y datasets) viven en el contenedor PostgreSQL local `superset-db`; no
usa la base de aplicación de Neon para ese fin.

Antes de iniciarlo, agregar estas variables protegidas a `.env.development`:

```bash
SUPERSET_DB_PASSWORD=<contraseña-local-robusta>
SUPERSET_ADMIN_USERNAME=admin
SUPERSET_ADMIN_PASSWORD=<contraseña-del-administrador>
SUPERSET_ADMIN_FIRSTNAME=Ingevec
SUPERSET_ADMIN_LASTNAME=Administrador
SUPERSET_ADMIN_EMAIL=<correo-administrador>
```

Luego iniciar y comprobar el servicio:

```bash
docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml up -d --build superset-db superset
docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml logs -f superset
```

Para crear o reconciliar la conexión analítica de solo lectura, ejecutar una vez:

```bash
docker compose --env-file .env.development -f compose.yaml -f compose.dev.yaml --profile provision run --rm superset-provisioner
```

El provisionador crea `superset_reader`, con permiso únicamente para consultar
`analytics.postventa_item_dashboard`, y registra esa vista como dataset. Superset
en ejecución no recibe la credencial propietaria de Neon. La integración OIDC con
Keycloak se configurará con un cliente dedicado y la URL de redirección de
Superset; no reutilizar el cliente de la UI administrativa.

### Acceso Superset con Keycloak

Crear el cliente confidencial `ingevec-superset` en el realm y guardar su secreto
en `SUPERSET_OIDC_CLIENT_SECRET`. El redirect URI es
`http://localhost:8088/oauth-authorized/keycloak` en desarrollo y
`https://bi.capix.cloud/oauth-authorized/keycloak` en producción. Los usuarios
reciben `superset_admin` (administración total) o `superset_viewer` (sólo
dashboards/gráficos). Para viewers, asignar además grupos con ruta completa:
`/superset/division/<id_division>` o `/superset/project/<numero_obra>`.
Los grupos se sincronizan en cada login; sin un grupo de alcance el viewer no ve
filas. SQL Lab y edición quedan reservados para `superset_admin`.

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

### UI administrativa

La aplicación React está en `apps/web/`. Con los servicios Docker en ejecución, abrir `http://localhost:5173`, iniciar sesión con un usuario que tenga el rol `admin` y seleccionar una obra para ver sus ítems de postventa.

Para ejecutar la UI fuera de Docker:

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

El proxy de Vite entrega las llamadas `/v1` al API local. No guardar tokens ni secretos de Keycloak en archivos del frontend.

## Producción

Copiar `config/production.env.example` a un archivo protegido del servidor. Ejecutar `docker compose --env-file /ruta/production.env -f compose.yaml -f compose.prod.yaml up -d --build`.

Antes de producción se debe configurar el reverse proxy y los registros Cloudflare para `api.capix.cloud`, `auth.capix.cloud` y `bi.capix.cloud`.

## Importación Excel

Sólo un administrador puede llamar `POST /v1/imports/excel` con el archivo `.xlsx`. En v1 se procesa exclusivamente la hoja `Año 2026`; las hojas históricas se preservan en el archivo original pero no se cargan. El proceso almacena el archivo original en SeaweedFS privado, conserva cada fila como JSON auditable y normaliza las filas válidas. Una carga con el mismo SHA-256 es idempotente y no duplica registros.

## Consultas para la UI administrativa

Estas rutas requieren un token de Keycloak con el rol `admin`. Todas son paginadas: `limit` acepta de 1 a 100 y `offset` permite avanzar por los resultados.

- `GET /v1/projects?search=712&limit=50&offset=0`: devuelve obra, nombre, tipología, ubicación, recepción municipal, supervisor, gerente y administrador de proyecto.
- `GET /v1/postventa-items?project_id=712&search=ventana&document_status=PENDING_REVIEW&limit=50&offset=0`: devuelve el ítem de postventa, proyecto, catálogos relacionados, causa de falla y el documento asociado si existe. Los filtros son opcionales.
- `GET /v1/dashboard/summary`: devuelve KPIs y agrupaciones para el Inicio administrativo.

Cada respuesta tiene la forma `{ "items": [...], "page": { "total": 0, "limit": 50, "offset": 0 } }`.
