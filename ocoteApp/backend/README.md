# OCOTE Backend: Nucleo Operativo F3

Python3.12/FastAPI/SQLAlchemy2/psycopg3/Alembic; F3 local/sintetico implementado/verificado, sin F4-F7 ni UI. Bootstrap posterior del operador observado y preservado; configuracion pendiente. Autoridad: [AGENTS](../AGENTS.md), [SDD](../docs/01-spec-driven-development.md), [arquitectura](../docs/02-arquitectura.md), [protocolo](../docs/05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada). [Evidencia F3](../docs/03-estado-actual-y-roadmap.md#9-nucleo-operativo-f3-local); responsable/excepciones hasta2026-12-24 conservados, no produccion.

## Inventario

| Ruta                                                                                                                                                       | Responsabilidad                                                                                   |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| [pyproject.toml](pyproject.toml), [requirements.lock](requirements.lock)                                                                                   | Python >=3.12,<3.13; dependencias incluidas las de prueba fijadas con hashes                      |
| [app/main.py](app/main.py)                                                                                                                                 | Factory FastAPI y ciclo de vida, sin conexion/migracion al arrancar                               |
| [app/core/config.py](app/core/config.py)                                                                                                                   | Variables/.env mediante Pydantic Settings, validacion de DSN/base/rol/IANA y perfil TLS           |
| [app/core/errors.py](app/core/errors.py)                                                                                                                   | problem+json, request_id generado en servidor y logs sanitizados de estado/duracion               |
| [app/db/engine.py](app/db/engine.py), [app/db/session.py](app/db/session.py)                                                                               | Pool acotado, una Session por peticion, unidad de trabajo explicita con commit/rollback           |
| [app/routers/health.py](app/routers/health.py)                                                                                                             | Live/ready tecnicos, independientes del bootstrap de usuarios |
| [alembic.ini](alembic.ini), [alembic/env.py](alembic/env.py), [alembic/script.py.mako](alembic/script.py.mako)                                             | Configuracion directa de migracion, NullPool y plantilla para revisiones futuras                  |
| [revision inicial](alembic/versions/20261124_0001_technical_foundation.py)                                                                                 | 20261124_0001, solo release_history; Alembic administra alembic_version                           |
| [revision F2](alembic/versions/20261124_0002_identity.py), [modelos](app/models/identity.py) | Nueve tablas de identidad/configuracion, vacias por diseno; no seeds |
| [seguridad](app/core/security.py), [sesion](app/services/identity.py), [rutas auth](app/routers/auth.py) | Argon2id, RS256, CSRF, rotacion/revocacion y politicas centrales |
| [DTO](app/schemas/identity.py), [administracion](app/services/administration.py), [rutas](app/routers/administration.py) | CRUD/versiones, scopes, parametros, catalogos y workflow atomico |
| [bootstrap](tools/bootstrap.py), [actualizacion local F2](tools/f2_local.py), [pruebas F2](tests/test_identity.py) | CLI de uso unico, backup/migracion/no-op/restore y pruebas aisladas |
| [revision F3](alembic/versions/20261124_0003_operations.py), [modelos](app/models/operations.py), [DTO](app/schemas/operations.py) | Seis tablas sin seeds; originales/versiones/append-only y fechas civiles |
| [servicio](app/services/operations.py), [API](app/routers/operations.py), [tests](tests/test_operations.py), [protocolo F3](tools/f3_local.py) | Permisos/alcance, comandos/fechas/historia atomicos, formulas y migracion local |
| [.env.example](.env.example)                                                                                                                               | Nombres y ejemplos sin secretos reales; distinta de la plantilla del helper en raiz               |
| [tools/f1_local.py](tools/f1_local.py)                                                                                                                     | Aprovisionamiento y ensayo exclusivamente local/explicito; no ocote-admin ni actualizador cliente |
| [tests/test_foundation.py](tests/test_foundation.py), [tests/test_rehearsal.py](tests/test_rehearsal.py), [tests/test_postgres.py](tests/test_postgres.py) | Salud/config/errores, backup bloqueante y PostgreSQL opt-in con fixtures revertidas               |

backend/.venv, backend/.env, backend/.local y database/backups son locales ignorados, nunca contenido distribuible. No se modificaron la aplicacion Angular servida ni los tres helpers existentes; el prototipo frontend vive solo en una fixture de pruebas.

## Entorno Reproducible

Comandos desde la raiz del repositorio en Git Bash Windows. No recrear un entorno/base existente ni regenerar el lock en cada arranque.

```bash
bash scripts/init-dev.sh --check
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install --require-hashes -r backend/requirements.lock
backend/.venv/Scripts/python -m pip check
```

Crear .venv solo cuando no exista. En otro SO usar el Python 3.12 y ruta .venv/bin/python nativos y homologar sus wheels; este ensayo solo verifico Windows x64. No actualizar Python, Angular ni el lock automaticamente. El lock actual instala tambien las herramientas de pruebas; un paquete runtime minimo y su SBOM quedan para la entrega homologada.

Regeneracion deliberada/revisada del lock (pip-tools 7.5.2 esta fijado en dev):

```bash
backend/.venv/Scripts/python -m piptools compile --allow-unsafe --extra dev --generate-hashes --strip-extras --output-file backend/requirements.lock backend/pyproject.toml
```

## Configuracion Y Roles

Pydantic carga backend/.env sin ejecutar Bash; AuthSettings agrega backend/.local/auth.env para claves/origen. Las variables de entorno prevalecen. No se carga el .env de raiz ni se exporta todo su contenido. No sobrescribir configuracion existente. DSN y token son SecretStr; los errores no imprimen entradas sensibles. Las variables requeridas estan en la plantilla, sin defaults de password.

- DATABASE_URL: postgresql+psycopg, base exacta ocoteAppDatabase y usuario ocote_runtime.
- MIGRATION_DATABASE_URL: igual base, usuario ocote_migrador; endpoint directo. La API no utiliza este DSN.
- HEALTH_TOKEN: secreto aleatorio del monitor de al menos 32 caracteres, solo servidor/monitor; no enviarlo a Angular ni en query strings.
- ORGANIZATION_TIMEZONE: requerida y validada IANA; America/Mexico_City es zona oficial D01. Solo referencia/bootstrap, nunca override runtime de system_settings. F2 no la inserta automaticamente: el admin crea explicitamente la clave.
- APP_ENV/DEPLOYMENT_MODE: desarrollo local solo loopback. Managed exige sslmode=verify-full, hostname y sslrootcert a CA legible en ambos DSN. Validacion de configuracion no demuestra TLS real ni homologa proveedor. Este perfil local rechaza produccion: su habilitacion requiere un perfil aprobado separado.
- Pool local por proceso: size=3, overflow=0, espera/conexion=3 s, statement=5 s, lock=2 s, idle-in-transaction=10 s y UTC. Son limites de desarrollo, no dimensionamiento productivo.

Endpoints/dependencias def en threadpool, una Session por peticion sin autoflush y flush explicito. Configuracion compartida para lecturas/comandos F3, exclusiva para auth/admin. Orden de filas departamento -> usuarios UUID ordenados -> plan -> objetivo -> tarea -> subtarea -> solicitud; plan serializa altas/cambios/cierre. Dependencia confirma antes de responder, revierte errores; revocacion por reuso confirma antes del401. Sin commits de routers ni cache de permisos/configuracion.

Roles provisionados en F1: runtime CONNECT/USAGE y SELECT de las dos tablas tecnicas; migrador CONNECT y USAGE/CREATE en public, sin privilegios elevados en cluster. F2 extiende DML especifico como se describe abajo. PUBLIC sin CREATE/USAGE en public; cada rol recibe permisos explicitos. Runtime no CREATE/TEMP/DML de bitacora ni membresia del migrador. No grants DML automaticos a futuras tablas: cada revision otorga minimos/preserva append-only. Migrador solo durante operacion autorizada, nunca API.

El .env local tiene contrasenas aleatorias distintas/ACL privada; nunca distribuirlo ni reutilizar credencial publica. En despliegue API recibe solo su DSN/token y migrador por canal separado. F2/F3 otorgan SELECT/INSERT/UPDATE en mutables y solo SELECT/INSERT en audit_events/task_history; runtime sin DELETE/DDL/DML de ledger. Triggers protegen identidad/versiones/originales/cierre/auditoria. Esta tarea no inicializo claves/admin en origen; bootstrap posterior del operador observado se preserva.

## Bootstrap Y Configuracion F2

ocoteAppDatabase/head20261124_0003 tiene17 tablas/cuatro releases terminales; seis F3 vacias y configuracion pendiente. Sin defaults/seeds/demos ni admin inventado por desarrollo. Durante cierre se observo bootstrap del operador (auth.env,1 usuario/1audit_event); no repetir ni sobrescribir. `ready` solo infraestructura, no configuracion completa. Sin claves auth falla503, no las genera al arrancar; altas operativas sin configuracion409.

Solo operador local autorizado, con custodia/canal definidos y preflight correcto. Elegir un origen HTTPS loopback real y confiable: el siguiente puerto es ejemplo de operador, no proxy/certificado instalado por esta tarea.

El checkout actual ya presenta bootstrap: confirmar custodia/identidad por canal del operador y completar configuracion, **no ejecutar de nuevo init-auth/bootstrap-admin**. El bloque siguiente es exclusivamente referencia para una instalacion nueva autorizada, nunca para resetear claves/usuario existentes.

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/bootstrap.py init-auth --origin https://localhost:8443 --execute
backend/.venv/Scripts/python backend/tools/bootstrap.py bootstrap-admin --execute
```

`init-auth` crea RSA3072, secreto CSRF y auth.env en backend/.local con ACL privada/O_EXCL; no sobrescribe claves ni backend/.env. Variables generadas: AUTH_ORIGIN, JWT_PRIVATE_KEY_FILE, CSRF_SECRET_FILE. Issuer/audience tecnicos ocote-local/ocote-spa; cambiarlos exige revisar sesiones. No enviar claves a agentes. `bootstrap-admin` exige claves validas, cero usuarios y ausencia de mantenimiento; pide email/nombre y password dos veces con getpass, Argon2id/auditoria en una transaccion con lock. Nunca password por argumento/log ni reset por repeticion; si ya hay usuarios, usar recuperacion aprobada, no recrear admin.

Luego admin configura explicitamente por API autenticada: cuatro claves POST /api/v1/settings (organization_name, organization_timezone oficial America/Mexico_City, evidence_max_bytes 1..10485760, export_max_rows 1..10000); prioridades incluyendo normal activa; exactamente cinco codes annual/semiannual/quarterly/monthly/custom con custom activo. Etiquetas/posiciones/limites son decisiones del operador, no valores sembrados. POST /api/v1/workflow introduce grafo completo atomicamente: etapas con code/name/position/kind/is_initial/requisitos/reason, aristas por from_code/to_code/allowed_roles y motivo global; existentes exigen expected_version por fila, sin omitir/borrar registros. GET /api/v1/configuration-status reporta faltantes; instalacion vacia es valida pero no habilita F3.

Sesion: POST auth/login (origen exacto), GET auth/csrf con cookie/origen, POST auth/refresh y auth/logout con cookie/origen/X-CSRF-Token, GET auth/me con Bearer y POST auth/change-password con password actual/nueva. Rutas bajo /api/v1. Access solo memoria SPA futura; refresh nunca JSON/localStorage. RS256/claves controladas, 10min access/7dias absolutos refresh; revocar familia invalida access inmediatamente. Cookie Secure/HttpOnly/SameSite Strict/Path /api/v1/auth: no bajar Secure para usar HTTP. Uvicorn HTTP siguiente solo sirve smoke tecnico o upstream privado de proxy HTTPS autorizado; navegador con sesion requiere TLS configurado aparte.

Administracion: GET/POST y PATCH departments/users/workflow-stages/workflow-transitions/priorities/horizon-types; reset-password, settings, reorder, workflow atomico y configuration-status. Audit-events/releases sanitizados solo lectura, releases detalle y alias release-history; listas limit1..100/cursor UUID/next_cursor, UUID ascendente. Mutaciones reason/version,409 sin overwrite; catalogos por alcance y auth/me solo facultades F1-F3. Sin DELETE.

Argon2id local: memoria65536KiB, tiempo3, paralelismo2; no benchmark productivo. Login y refresh <=10/cuenta/min y <=50/cliente/min compartidos, hashing efimero de claves/cliente, memoria acotada por proceso; 429/Retry-After60. No limite distribuido ni soporte multiples workers homologado. JSON <=1MiB; logs sin cuerpos/passwords/tokens/DSN. HTTPS real, custodia, bootstrap y configuracion de origen siguen pendientes; las pruebas usan transporte HTTPS TestClient y secretos sinteticos aislados.

## API Operativa F3

Prefijo /api/v1: GET/POST annual-plans/objectives/tasks y GET/PATCH por id; period-changes en planes/objetivos y status-changes en planes. A/G planifican; A/L gestionan tareas; G solo lectura/fechas, no transiciones. Tareas: assignments/stage-transitions/due-date-changes/schedule-changes, GET/POST tasks/{id}/subtasks y GET/PATCH subtasks/{id} con completion/due-date-changes/schedule-changes. Child commands verifican expected_version y expected_task_version; alta child usa expected_version del padre. C solo asignadas/contexto minimo/ejecucion permitida, sin agregados ni planes/objetivos/solicitudes.

POST tasks/{id}/due-date-requests y subtasks/{id}/due-date-requests captura versiones sin mutar tarea. A/G/L solicitan por alcance; A/G approve/reject, approve nunca solicitante; cancel propio L o A/G. Pending unica por destino; versiones obsoletas/terminales/cerrados409. Validacion al solicitar y aprobar; fecha+historia+decision atomicas, original intacta. GET due-date-requests/detalle y tasks/{id}/history requieren alcance sobre tarea, no solo UUID.

Fechas ISO YYYY-MM-DD civiles estrictas, rangos inclusivos y timestamps UTC del servidor. Periodos/fechas/schedules/asignaciones/decisiones con reason; status-changes opcional. Progreso proporcional con subtareas;100 pendiente no cierra tarea. Dos puntualidades por zona BD. Originales/historia/cierre inmutables. Listas limit1..100/cursor/next_cursor y filtros plan/departamento/objetivo/asignado/etapa/prioridad/puntualidad antes de paginar; historia created_at/id y cursor de misma tarea. Evidencia requerida o IDs ficticios422 hasta F5. Sin DELETE/UI/evidencia/Kanban/Timeline/analytics/evaluaciones/exports.

## Salud Y Arranque

```bash
backend/.venv/Scripts/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

GET /api/v1/health/live es publico/minimo y no consulta BD. GET /api/v1/health/ready exige X-Health-Token y devuelve 200 solo con conectividad a la base exacta y la unica head del artefacto; revision ausente/desconocida/multiple o fallo de BD devuelve 503 sin detalles. Una marca backend/.local/maintenance.json mantiene ready en 503. Token ausente/incorrecto: 403 antes de acceder a BD. Cada respuesta incluye X-Request-ID; errores usan application/problem+json sin eco de entradas, SQL, credenciales ni trazas.

Swagger/OpenAPI HTTP no estan expuestos. El proxy futuro debe restringir ready al monitor, no reenviar logs de cabeceras/DSN/query ni exponer el servicio directamente; el token tecnico no es autenticacion RF-02. El ensayo HTTP local se cerro y no se dejo Uvicorn en ejecucion. El arranque NO ejecuta create_all, Alembic, seeds ni conexion a la BD; nunca se migra desde la API.

## Migracion Y Ensayo Local

Tres revisiones20261124_0001/0002/0003 inmutables. F1 crea release_history; F2 agrega nueve tablas y F3 seis, sin seeds:17 totales incluyendo alembic_version, no19 objetivo. Downgrade bloqueado: fix-forward o restore aislado aprobado, nunca stamp. Las instrucciones F1/F2 siguientes son historicas; no ejecutar sus comandos en origen F3 ni adaptar helpers.

Comandos de inspeccion, sin migrar:

```bash
backend/.venv/Scripts/python -m alembic -c backend/alembic.ini current
backend/.venv/Scripts/python -m alembic -c backend/alembic.ini heads
```

tools/f1_local.py NO es el protocolo cliente completo. Solo acepta el cluster Windows local ya existente, PG18, identidad de data y base exactas; credencial administrativa en PGPASSWORD sin fallback. No cambia cluster/HBA/PID ni crea/resetear bases de aplicacion. No invocar contra nube o cliente. Para una instalacion de desarrollo nueva/vacia y expresamente autorizada, el operador introduce la credencial directamente en su terminal:

```bash
read -r -s -p 'Credencial administrativa local autorizada: ' PGPASSWORD
printf '\n'
export PGPASSWORD
backend/.venv/Scripts/python backend/tools/f1_local.py provision --execute
backend/.venv/Scripts/python backend/tools/f1_local.py rehearse --execute
unset PGPASSWORD
```

NO repetir esos comandos en la base actual: provision exige roles/configuracion ausentes y base vacia, y rehearse exige origen virgen. No rota roles ni borra .env existentes. provision genera secretos con secrets, restringe ACL antes de escribirlos y verifica conexiones independientes; no guarda password administrativa.

rehearse exige cero conexiones ajenas; el operador debe detener/drenar escritores antes. Mantiene advisory lock de sesion en conexion directa, marca mantenimiento y bitacora fsync externa con attempt/request*id antes del DDL. Primero pg_dump custom y restore aislado bloqueante; luego upgrade y segundo upgrade con snapshot identico; incorpora intento desde bitacora, vuelve a respaldar/restaurar la revision y registra resultado. Cada destino lleva nombre ocote_f1_restore*<UUID>, usa --no-owner/--no-acl sin --clean y se elimina sin FORCE al terminar. No se desconectan procesos ajenos. El lock es cooperativo y no sustituye detener escritores ni un proxy de mantenimiento homologado.

Un fallo conserva mantenimiento, registros y dumps; no hay reset, downgrade, stamp ni reintento automatico. El fallo real de comparacion PG18 quedo failed y luego se ejecuto explicitamente retry-verification --execute: exige ese intento incompleto/revision ya aplicada, conserva sus timestamps, crea otra fila con retry_of_id, respalda/restaura de nuevo y comprueba dos upgrades no-op. No es una herramienta universal de reanudacion; otros estados requieren diagnostico/plan aprobado. No retirar la marca de mantenimiento para ocultar un fallo.

PG18 puede descompilar CHECK con casts ARRAY textualmente distintos tras restore. La comparacion corregida usa propiedades del catalogo, filas/revision, columnas/defaults/longitudes, indices, triggers/funcion y 17 fixtures invalidas mas transiciones protegidas en transacciones revertidas. No afirma equivalencia formal de SQL ni cobertura de un modelo de negocio inexistente.

Los artefactos quedan en database/backups/f1-<attempt>/ con ACL local: events.jsonl durable, dumps y manifests SHA-256. El manifest de artefacto es una instantanea del ensayo SIN firma, no una release distribuible ni el hash del checkout final. Los respaldos posteriores capturan el intento running; el evento terminal se produce despues y debe reconciliarse desde bitacora externa al restaurar, conservando request_id/timestamps y sin reabrir antes de validar. No contienen usuarios/tablas de negocio; no estan cifrados ni copiados fuera del host. Eso NO satisface operacion real, retencion, privacidad ni proteccion ante perdida del host.

### Verificar La Base Tecnica Existente

Procedimiento historico exclusivo head0001/dos tablas. **No ejecutarlo en origen actual F3**; rechaza inventario nuevo. No adaptar helper F1 ni repetir provision/rehearse/retry-verification.

Solo para una comprobacion local expresamente autorizada, con API/escritores detenidos y PGPASSWORD introducida directamente en terminal y exportada como arriba:

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/f1_local.py verify-existing --execute
unset PGPASSWORD
```

Exige identidad original, unica head tecnica, solo las dos tablas tecnicas y cero sesiones ajenas. Toma lock persistente/mantenimiento, nuevo backup con restore aislado bloqueante y dos upgrades no-op comparando snapshots; preserva las filas release_history existentes **sin mutaciones persistidas** (fixtures de constraints en transacciones revertidas). La comprobacion no es una release: deja su journal/manifests propios en database/backups/f1-closure-<UUID>/, no fabrica otra fila de despliegue. El dump de cierre incluye ambos intentos anteriores ya terminales. Exito limpia solo su destino temporal/marca; fallo conserva mantenimiento/evidencia, sin reset ni reintento automatico. No usar provision/rehearse/retry-verification para repetir este chequeo.

### Migracion Local F2

[f2_local.py](tools/f2_local.py) ya ejecuto apply sobre origen0001 ->0002; intento y hashes en acta F2. Solo acepta ese origen una vez, cero sesiones ajenas, lock persistente/mantenimiento, backup/restore antes del upgrade, segundo no-op, restore posterior y del registro running, terminal y reapertura. Antes de crearse fila el journal externo es evidencia; si ya existe running intenta marcarla failed sin tocar terminales. Cualquier fallo conserva mantenimiento; diagnostico/fix-forward aprobado, no reaplicar/resetear ni editar revision instalada.

### Migracion Local F3

[f3_local.py](tools/f3_local.py) ya ejecuto apply0002 ->0003: lock persistente/mantenimiento, before restaurado y migrado/no-op en UUID aislado antes de DDL origen, upgrade/no-op origen y cuatro restores before/after/recorded/terminal. Preserva F2/legacy/releases previas y verifica grants aparte. Fallo mantiene maintenance/journal, no reintentar apply en origen0003 ni retirar marca manualmente. Backups privados/hashes en roadmap9.

Para probar F3 desde cero sin tocar origen, con credencial administrativa introducida/exportada directamente en terminal como arriba:

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/f3_local.py check-migration --execute
unset PGPASSWORD
```

Crea/elimina solo ocote_f2_test_<UUID>/ocote_f2_restore_<UUID>, prefijo aprobado reutilizado sin alterar helpers F1/F2. No actualizador cliente ni orden para repetir apply. Restore --no-acl no prueba recuperar grants; suite/protocolo verifican runtime aparte. recorded contiene running/reconciliar journal; terminal incluye intento terminal. Manifest no firmado/instantanea, no checkout final, cifrado/copia off-host ni recovery de host.

## Verificacion Y Limites

```bash
backend/.venv/Scripts/python -m pytest -q backend/tests
OCOTE_RUN_PG_TESTS=1 backend/.venv/Scripts/python -m pytest -q backend/tests
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m pip check
git diff --check
```

Sin opt-in: **46 passed,44 skipped**, sin conectar PostgreSQL. Con OCOTE_RUN_PG_TESTS=1: **90 passed**, requiere PGPASSWORD administrativa temporal local/configuracion/head0003. F1 usa rollback en origen; F2/F3 bases UUID aisladas, migrador para Alembic y runtime para API/sinteticos, eliminadas al terminar. Superusuario solo prepara/elimina destinos, nunca API. Sin SQLite ni fixtures de negocio en origen. Ruff format/check(31 archivos) y pip check limpios. Incluye scopes/formulas/originales, carreras cierre-subtarea/aprobacion y periodo-alta, atomicidad/versiones y fallos antes de DDL. Deprecacion TestClient/httpx y TS6 rootDir ajeno al cambio permanecen; no build Angular repetido. [Resultados/hashes/limites](../docs/03-estado-actual-y-roadmap.md#9-nucleo-operativo-f3-local).

D01/formulas del nucleo ratificadas; D03/D08 gerenciales siguen F6. Base D05/objetivos D06 en [guia05](../docs/05-paquetizacion-instalacion-y-actualizaciones.md#31-base-aprobada-de-privacidad-y-recuperacion-d05d06). Excepciones sin suplente/D07 soporte/61 alertas conservadas por F3 hasta2026-12-24, solo local/sintetico; responsable LUIS ANGEL VALLEJO - DESARROLLADOR. Otro host/nube/TLS/capacidad, cifrado/copia off-host/scheduler/firma/homologacion pendientes, no SLA/remediacion. Python3.12.0 no certifica parche productivo; btree_gist disponible no demuestra GiST probado. Sin almacenamiento/integraciones. Frontend/lock/builds historicos intactos.

Siguiente paso: confirmar custodia/origen HTTPS/bootstrap ya observado sin repetir/sobrescribir; completar settings/catalogos/grafo explicitos y configuration-status. Despues solicitar autorizacion F4 y validar muestra accesible OCOTE/licencia tipografica/Material18.2. **F4-F7 no autorizados**; no pantallas/evidencia/evaluaciones/nube por anticipado. PostgreSQL queda activo, sin API/dev server iniciado ni temporales/mantenimiento.
