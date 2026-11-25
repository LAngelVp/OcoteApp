# OCOTE Backend: Identidad Y Administracion F2

Python 3.12, FastAPI, SQLAlchemy 2.0 sincrono, psycopg 3 y Alembic; F2 local/sintetico implementado y verificado, con bootstrap/configuracion del operador pendientes. No F3-F7 ni pantallas Angular. Autoridad: [AGENTS](../AGENTS.md), [SDD](../docs/01-spec-driven-development.md), [arquitectura](../docs/02-arquitectura.md) y [protocolo de release](../docs/05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada). Evidencia y limites en [F2](../docs/03-estado-actual-y-roadmap.md#8-identidad-y-administracion-f2-local); excepciones hasta 2026-12-24 en [acta F1 historica](../docs/03-estado-actual-y-roadmap.md#7-cierre-formal-f1-local).

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

El backend sincrono usa endpoints/dependencias def en threadpool. Una Session por peticion se cierra/revierte al terminar. La dependencia F2 toma lock compartido para lecturas/exclusivo para mutaciones, confirma antes de enviar respuesta y revierte errores; revocacion por reuso se confirma antes del 401. Sin commits del router ni cache de permisos/configuracion.

Roles provisionados en F1: runtime CONNECT/USAGE y SELECT de las dos tablas tecnicas; migrador CONNECT y USAGE/CREATE en public, sin privilegios elevados en cluster. F2 extiende DML especifico como se describe abajo. PUBLIC sin CREATE/USAGE en public; cada rol recibe permisos explicitos. Runtime no CREATE/TEMP/DML de bitacora ni membresia del migrador. No grants DML automaticos a futuras tablas: cada revision otorga minimos/preserva append-only. Migrador solo durante operacion autorizada, nunca API.

El .env combinado generado es exclusivamente de desarrollo, con contrasenas aleatorias distintas y ACL privada. En despliegue, inyectar al proceso API solo su DSN/token y entregar el DSN migrador por canal operativo separado; no distribuir el .env local ni la credencial publica. F2 agrega SELECT/INSERT/UPDATE en tablas mutables/refresh y solo SELECT/INSERT en audit_events; sin DELETE, DDL ni DML sobre ledger para runtime. Triggers protegen identidad/version/auditoria. No usuarios reales ni claves JWT inicializados en origen en esta entrega.

## Bootstrap Y Configuracion F2

Las once tablas existen en ocoteAppDatabase/head20261124_0002, pero las nueve F2 estan vacias intencionalmente. No defaults de negocio, seeds, demos o credencial admin. `ready` verifica infraestructura, NO que configuracion/bootstrap esten completos. Auth sin claves inicializadas devuelve 503, no genera secretos al arrancar.

Solo operador local autorizado, con custodia/canal definidos y preflight correcto. Elegir un origen HTTPS loopback real y confiable: el siguiente puerto es ejemplo de operador, no proxy/certificado instalado por esta tarea.

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/bootstrap.py init-auth --origin https://localhost:8443 --execute
backend/.venv/Scripts/python backend/tools/bootstrap.py bootstrap-admin --execute
```

`init-auth` crea RSA3072, secreto CSRF y auth.env en backend/.local con ACL privada/O_EXCL; no sobrescribe claves ni backend/.env. Variables generadas: AUTH_ORIGIN, JWT_PRIVATE_KEY_FILE, CSRF_SECRET_FILE. Issuer/audience tecnicos ocote-local/ocote-spa; cambiarlos exige revisar sesiones. No enviar claves a agentes. `bootstrap-admin` exige claves validas, cero usuarios y ausencia de mantenimiento; pide email/nombre y password dos veces con getpass, Argon2id/auditoria en una transaccion con lock. Nunca password por argumento/log ni reset por repeticion; si ya hay usuarios, usar recuperacion aprobada, no recrear admin.

Luego admin configura explicitamente por API autenticada: cuatro claves POST /api/v1/settings (organization_name, organization_timezone oficial America/Mexico_City, evidence_max_bytes 1..10485760, export_max_rows 1..10000); prioridades incluyendo normal activa; exactamente cinco codes annual/semiannual/quarterly/monthly/custom con custom activo. Etiquetas/posiciones/limites son decisiones del operador, no valores sembrados. POST /api/v1/workflow introduce grafo completo atomicamente: etapas con code/name/position/kind/is_initial/requisitos/reason, aristas por from_code/to_code/allowed_roles y motivo global; existentes exigen expected_version por fila, sin omitir/borrar registros. GET /api/v1/configuration-status reporta faltantes; instalacion vacia es valida pero no habilita F3.

Sesion: POST auth/login (origen exacto), GET auth/csrf con cookie/origen, POST auth/refresh y auth/logout con cookie/origen/X-CSRF-Token, GET auth/me con Bearer y POST auth/change-password con password actual/nueva. Rutas bajo /api/v1. Access solo memoria SPA futura; refresh nunca JSON/localStorage. RS256/claves controladas, 10min access/7dias absolutos refresh; revocar familia invalida access inmediatamente. Cookie Secure/HttpOnly/SameSite Strict/Path /api/v1/auth: no bajar Secure para usar HTTP. Uvicorn HTTP siguiente solo sirve smoke tecnico o upstream privado de proxy HTTPS autorizado; navegador con sesion requiere TLS configurado aparte.

Administracion: GET/POST y PATCH por id de departments/users/workflow-stages/workflow-transitions/priorities/horizon-types; POST users/{id}/reset-password; GET/POST settings, GET/PATCH settings/{key}; POST priorities/reorder y horizon-types/reorder con items id/position/expected_version y reason; workflow atomico, configuration-status, audit-events/releases solo lectura sanitizada. Releases tiene detalle por id y alias release-history; listas admin/auditoria/releases con limit1..100, cursor UUID y next_cursor, orden ascendente de UUID. Mutaciones con reason/version, 409 sin overwrite. Catalogos /catalogs por rol/departamento; sin permisos F3-F6 anunciados. Sin DELETE.

Argon2id local: memoria65536KiB, tiempo3, paralelismo2; no benchmark productivo. Login y refresh <=10/cuenta/min y <=50/cliente/min compartidos, hashing efimero de claves/cliente, memoria acotada por proceso; 429/Retry-After60. No limite distribuido ni soporte multiples workers homologado. JSON <=1MiB; logs sin cuerpos/passwords/tokens/DSN. HTTPS real, custodia, bootstrap y configuracion de origen siguen pendientes; las pruebas usan transporte HTTPS TestClient y secretos sinteticos aislados.

## Salud Y Arranque

```bash
backend/.venv/Scripts/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

GET /api/v1/health/live es publico/minimo y no consulta BD. GET /api/v1/health/ready exige X-Health-Token y devuelve 200 solo con conectividad a la base exacta y la unica head del artefacto; revision ausente/desconocida/multiple o fallo de BD devuelve 503 sin detalles. Una marca backend/.local/maintenance.json mantiene ready en 503. Token ausente/incorrecto: 403 antes de acceder a BD. Cada respuesta incluye X-Request-ID; errores usan application/problem+json sin eco de entradas, SQL, credenciales ni trazas.

Swagger/OpenAPI HTTP no estan expuestos. El proxy futuro debe restringir ready al monitor, no reenviar logs de cabeceras/DSN/query ni exponer el servicio directamente; el token tecnico no es autenticacion RF-02. El ensayo HTTP local se cerro y no se dejo Uvicorn en ejecucion. El arranque NO ejecuta create_all, Alembic, seeds ni conexion a la BD; nunca se migra desde la API.

## Migracion Y Ensayo Local

Ambas revisiones aplicadas 20261124_0001 y 20261124_0002 son inmutables. F1 crea release_history; F2 agrega nueve tablas sin seeds. Alembic_version es metadata tecnica: once tablas en total, no las 19 objetivo. Downgrade bloqueado por preservacion de bitacora: usar fix-forward o restore aislado aprobado, nunca stamp.

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

Procedimiento historico exclusivo de head0001 con dos tablas. **No ejecutarlo en el origen actual F2**: rechaza el nuevo inventario. No adaptar silenciosamente el helper F1 ni repetir provision/rehearse/retry-verification.

Solo para una comprobacion local expresamente autorizada, con API/escritores detenidos y PGPASSWORD introducida directamente en terminal y exportada como arriba:

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/f1_local.py verify-existing --execute
unset PGPASSWORD
```

Exige identidad original, unica head tecnica, solo las dos tablas tecnicas y cero sesiones ajenas. Toma lock persistente/mantenimiento, nuevo backup con restore aislado bloqueante y dos upgrades no-op comparando snapshots; preserva las filas release_history existentes **sin mutaciones persistidas** (fixtures de constraints en transacciones revertidas). La comprobacion no es una release: deja su journal/manifests propios en database/backups/f1-closure-<UUID>/, no fabrica otra fila de despliegue. El dump de cierre incluye ambos intentos anteriores ya terminales. Exito limpia solo su destino temporal/marca; fallo conserva mantenimiento/evidencia, sin reset ni reintento automatico. No usar provision/rehearse/retry-verification para repetir este chequeo.

### Migracion Local F2

[f2_local.py](tools/f2_local.py) ya ejecuto apply sobre origen0001 ->0002; intento y hashes en acta F2. Solo acepta ese origen una vez, cero sesiones ajenas, lock persistente/mantenimiento, backup/restore antes del upgrade, segundo no-op, restore posterior y del registro running, terminal y reapertura. Antes de crearse fila el journal externo es evidencia; si ya existe running intenta marcarla failed sin tocar terminales. Cualquier fallo conserva mantenimiento; diagnostico/fix-forward aprobado, no reaplicar/resetear ni editar revision instalada.

Para probar revision desde cero sin tocar origen, con credencial administrativa introducida/exportada directamente en terminal como arriba:

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/f2_local.py check-migration --execute
unset PGPASSWORD
```

Crea/elimina solo ocote_f2_test_<UUID>; restaura solo ocote_f2_restore_<UUID>. No es actualizador cliente ni una orden para repetir apply en origen. El restore usa --no-acl: comparar datos/esquema no prueba restauracion de grants; la suite verifica grants runtime aparte. recorded.dump captura running: reconciliar evento terminal del journal antes de reabrir un restore. Manifests locales no firmados/instantaneas del ensayo, no hash del checkout final, cifrado/copia off-host ni recovery de host.

## Verificacion Y Limites

```bash
backend/.venv/Scripts/python -m pytest -q backend/tests
OCOTE_RUN_PG_TESTS=1 backend/.venv/Scripts/python -m pytest -q backend/tests
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m pip check
git diff --check
```

La primera invocacion da **33 passed, 25 skipped**, sin conectar PostgreSQL; la segunda requiere PGPASSWORD administrativa local temporal, configuracion y head0002. F1 usa fixtures con rollback en origen; F2 crea bases UUID aisladas, migra con migrador y ejerce API con runtime/datos sinteticos, eliminandolas al terminar. Superusuario solo prepara/elimina destinos, nunca API. No SQLite ni identidades de prueba en origen. Resultado F2: **58 passed**, Ruff/pip check limpios; races/reuso, ultimo admin, scopes/errores, constraints, no-defaults, bootstrap, reordenamiento atomico y paginacion/proyeccion de releases. Deprecacion TestClient/httpx conocida; editor reporta diagnostico TS6 rootDir en tsconfig.json no modificado, fuera de F2. No build Angular reejecutado.

D01 ratificada; politica D05 y objetivos/responsable D06 aprobados en [guia 05, seccion 3.1](../docs/05-paquetizacion-instalacion-y-actualizaciones.md#31-base-aprobada-de-privacidad-y-recuperacion-d05d06). Excepcion sin suplente y excepciones separadas D07 soporte Angular/61 alertas hasta 2026-12-24, solo F1/F2 local/sintetico; responsable LUIS ANGEL VALLEJO - DESARROLLADOR. Otro host/nube/TLS/capacidad, cifrado/copia off-host, scheduler, firma/paquete y homologacion cliente pendientes; no SLA ni remediacion de seguridad. Python3.12.0 local no certifica parche productivo; btree_gist disponible no demuestra GiST probado. Sin almacenamiento ni integraciones. Build/tests Angular historicos F1 no se repitieron: frontend/lock intactos.

Siguiente paso: operador completa custodia/bootstrap y configuracion explicita como arriba. Despues solicitar aceptacion de ejemplos temporales/D03/D08 y reglas de F3, y autorizacion expresa de esa fase. **F3 no autorizado**; no crear planes/tareas/evaluaciones ni pantallas funcionales por anticipado. PostgreSQL queda activo, sin API/dev server persistente, sin bases temporales o mantenimiento pendiente.
