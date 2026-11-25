# OCOTE Backend: Nucleo Operativo y Evidencia F5

Python3.12/FastAPI/SQLAlchemy2/psycopg3/Alembic; F5 autorizada/implementada/verificada tecnicamente local/sintetico, cierre operativo pendiente. Bootstrap preservado; configuracion/aceptacion funcional y almacenamiento/ClamAV reales pendientes, cargas cerradas. F6-F7 no autorizados. Autoridad: [AGENTS](../AGENTS.md), [SDD](../docs/01-spec-driven-development.md), [arquitectura](../docs/02-arquitectura.md), [protocolo](../docs/05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada). [Evidencia F5](../docs/03-estado-actual-y-roadmap.md#11-kanban-timeline-y-evidencias-f5-local); responsable/excepciones hasta2026-12-24 conservados, no produccion.

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

backend/.venv, backend/.env, backend/.local y database/backups son locales ignorados, nunca contenido distribuible. F5 agrega [revision0004](alembic/versions/20261124_0004_evidence.py), [almacen/ClamAV](app/core/evidence.py), [servicio](app/services/evidence.py), [API de vistas/evidencia](app/routers/execution.py), [pruebas](tests/test_execution.py) y [protocolo separado](tools/f5_local.py). Revisiones0001/0002/0003, helpers F1-F3 y configuracion auth permanecen intactos.

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

ocoteAppDatabase/head20261124_0004 tiene18 tablas/cinco releases terminales; seis F3/evidence_files vacias y configuracion pendiente. Sin defaults/seeds/demos ni admin inventado por desarrollo. Bootstrap del operador preservado; no repetir ni sobrescribir. `ready` solo infraestructura, no configuracion completa ni disponibilidad del antivirus. Sin claves auth falla503, no las genera al arrancar; altas operativas sin configuracion409.

Solo operador local autorizado, con custodia/canal definidos y preflight correcto. En este checkout el origen HTTPS loopback ya observado es https://localhost:8443: preservarlo. Proxy de desarrollo F4 descrito en guia04, certificado autofirmado no homologado como TLS cliente.

El checkout actual ya presenta bootstrap: confirmar custodia/identidad por canal del operador y completar configuracion, **no ejecutar de nuevo init-auth/bootstrap-admin**. El bloque siguiente es exclusivamente referencia para una instalacion nueva autorizada, nunca para resetear claves/usuario existentes.

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/bootstrap.py init-auth --origin https://localhost:8443 --execute
backend/.venv/Scripts/python backend/tools/bootstrap.py bootstrap-admin --execute
```

`init-auth` crea RSA3072, secreto CSRF y auth.env en backend/.local con ACL privada/O_EXCL; no sobrescribe claves ni backend/.env. Variables generadas: AUTH_ORIGIN, JWT_PRIVATE_KEY_FILE, CSRF_SECRET_FILE. Issuer/audience tecnicos ocote-local/ocote-spa; cambiarlos exige revisar sesiones. No enviar claves a agentes. `bootstrap-admin` exige claves validas, cero usuarios y ausencia de mantenimiento; pide email/nombre y password dos veces con getpass, Argon2id/auditoria en una transaccion con lock. Nunca password por argumento/log ni reset por repeticion; si ya hay usuarios, usar recuperacion aprobada, no recrear admin.

Luego admin configura explicitamente por UI F4 o API autenticada: cuatro claves POST /api/v1/settings (organization_name, organization_timezone oficial America/Mexico_City, evidence_max_bytes 1..10485760, export_max_rows 1..10000); prioridades incluyendo normal activa; exactamente cinco codes annual/semiannual/quarterly/monthly/custom con custom activo. Etiquetas/posiciones/limites son decisiones del operador, no valores sembrados. POST /api/v1/workflow introduce grafo completo atomicamente: etapas con code/name/position/kind/is_initial/requisitos/reason, aristas por from_code/to_code/allowed_roles y motivo global; existentes exigen expected_version por fila, sin omitir/borrar registros. GET /api/v1/configuration-status reporta faltantes; instalacion vacia es valida pero no habilita F3. Visitar UI no crea datos ni repite bootstrap.

Etapas y Transiciones tienen modales separados, con POST /workflow-stages y POST /workflow-transitions respectivamente. Antes de la primera tarea/evaluacion se pueden guardar por pasos: primero la inicial open/activa/sin requisitos, otras etapas y despues sus aristas. No se precargan filas. `workflow_valid`/`complete` permanecen false y los comandos operativos fallan cerrados hasta completar el grafo. Con tareas/evaluaciones existentes se protege la validez completa; el editor atomico se ofrece solo en Configuracion. Nunca se retiran FK, unicidad ni protecciones de inicial/terminal/ocupacion. [Evidencia de correccion](../docs/03-estado-actual-y-roadmap.md#14-separacion-de-etapas-y-transiciones-y-secretos-exactos-2026-11-25).

Contrasenas de alta, login, cambio y reset conservan exactamente todos sus caracteres, incluidos espacios extremos. Los DTO secretos evitan `str_strip_whitespace` sin quitar limites (12..128 para nueva,1..128 para actual/login); nombres/codigos/motivos siguen normalizados. La edicion ordinaria de usuario no admite password. No se reescribieron hashes ni credenciales existentes: si una alta/reset historico ya recorto una password, el titular debe usar su valor efectivo o el restablecimiento autorizado, no se puede recuperar lo descartado ni se intenta adivinarlo.

Sesion: POST auth/login (origen exacto), GET auth/csrf con cookie/origen, POST auth/refresh y auth/logout con cookie/origen/X-CSRF-Token, GET auth/me con Bearer y POST auth/change-password con password actual/nueva. Rutas bajo /api/v1. Access/CSRF solo memoria SPA F4; refresh nunca JSON/localStorage. RS256/claves controladas,10min access/7dias absolutos refresh; revocar familia invalida access inmediatamente. Cookie Secure/HttpOnly/SameSite Strict/Path /api/v1/auth: no bajar Secure para usar HTTP. Web Locks serializan login/refresh/logout entre pestanas; sin soporte falla cerrado. Origin POST/Referer GET generados por navegador, proxy conserva origen. Uvicorn HTTP siguiente solo smoke/upstream privado, no origen de login del navegador.

Administracion: GET/POST y PATCH departments/users/workflow-stages/workflow-transitions/priorities/horizon-types; reset-password, settings, reorder, workflow atomico y configuration-status. Audit-events/releases sanitizados solo lectura, releases detalle y alias release-history; listas limit1..100/cursor UUID/next_cursor, UUID ascendente. Mutaciones reason/version,409 sin overwrite; catalogos por alcance y auth/me solo facultades F1-F3. Sin DELETE.

Argon2id local: memoria65536KiB, tiempo3, paralelismo2; no benchmark productivo. Login y refresh <=10/cuenta/min y <=50/cliente/min compartidos, hashing efimero de claves/cliente, memoria acotada por proceso;429/Retry-After60. No limite distribuido ni soporte multiples workers homologado. JSON <=1MiB; logs sin cuerpos/passwords/tokens/DSN. Bootstrap existente preservado, custodia/configuracion/aceptacion del operador pendientes. Backend usa HTTPS TestClient/secretos aislados; navegador F4 mocks y HTTPS loopback autofirmado, no E2E autenticado real ni TLS productivo.

### Diagnostico De Configuracion Incompleta

GET `/configuration-status` conserva los faltantes y agrega `workflow_error`: codigo de validacion del grafo o null cuando es valido. La UI administrativa muestra el mensaje seguro y enlaces a Etapas/Transiciones. Si no faltan settings/horizontes y normal esta activa, `WORKFLOW_HAS_NO_TERMINAL_PATH` significa que alguna etapa activa no puede llegar a la terminal; no basta con capturar etapas ni cambiar su orden visual. El operador debe guardar las aristas y roles decididos, con motivo/version cuando corresponda, y recargar Configuracion. Nunca se inventan transiciones ni se deshabilita el bloqueo para facilitar un alta.

[Diagnostico local y verificacion de operaciones](../docs/03-estado-actual-y-roadmap.md#15-diagnostico-de-habilitacion-operativa-2026-11-25): grafo pendiente de decision/captura del titular; configuracion de origen preservada por solicitud expresa. Una terminal con evidencia obligatoria sigue requiriendo almacenamiento/ClamAV reales y evidencia valida, incluso despues de completar el grafo. Con configuracion completa: crear plan borrador -> objetivo/departamento y rango contenido -> activar plan -> tareas/subtareas. Kanban no mueve tarjetas ante error; Timeline no edita fechas; solicitudes conservan versiones/alcance y aprobador distinto del solicitante. La aceptacion del operador no se sustituye con fixtures aislados.

## API Operativa F3

Prefijo /api/v1: GET/POST annual-plans/objectives/tasks y GET/PATCH por id; period-changes en planes/objetivos y status-changes en planes. A/G planifican; A/L gestionan tareas; G solo lectura/fechas, no transiciones. Tareas: assignments/stage-transitions/due-date-changes/schedule-changes, GET/POST tasks/{id}/subtasks y GET/PATCH subtasks/{id} con completion/due-date-changes/schedule-changes. Child commands verifican expected_version y expected_task_version; alta child usa expected_version del padre. C solo asignadas/contexto minimo/ejecucion permitida, sin agregados ni planes/objetivos/solicitudes.

POST tasks/{id}/due-date-requests y subtasks/{id}/due-date-requests captura versiones sin mutar tarea. A/G/L solicitan por alcance; A/G approve/reject, approve nunca solicitante; cancel propio L o A/G. Pending unica por destino; versiones obsoletas/terminales/cerrados409. Validacion al solicitar y aprobar; fecha+historia+decision atomicas, original intacta. GET due-date-requests/detalle y tasks/{id}/history requieren alcance sobre tarea, no solo UUID.

Fechas ISO YYYY-MM-DD civiles estrictas, rangos inclusivos y timestamps UTC del servidor. Periodos/fechas/schedules/asignaciones/decisiones con reason; status-changes opcional. Progreso proporcional con subtareas;100 pendiente no cierra tarea. Dos puntualidades por zona BD. Originales/historia/cierre inmutables. Listas limit1..100/cursor/next_cursor y filtros plan/departamento/objetivo/asignado/etapa/prioridad/puntualidad antes de paginar; historia created_at/id y cursor de misma tarea. F5 valida evidence_ids reales de la misma tarea: faltantes422/ajenos404, versiones obsoletas409. Sin DELETE/analytics/evaluaciones/exports.

## Evidencias Y Vistas F5

GET /api/v1/kanban devuelve columns con stage/count/items/next_cursor; filtros operativos antes del conteo, limit1..100 y lane_id/cursor por columna. Conserva etapas activas vacias ordenadas. C recibe solo sus tareas/conteos propios; G no transiciona. GET /api/v1/timeline exige kind=plan/objective/task/subtask y devuelve items/next_cursor/organization_timezone; C solo task/subtask. La zona procede de BD; fechas civiles inclusivas, cierre UTC convertido a zona organizacional. UI no mueve fechas por drag.

GET /tasks/{id}/evidence pagina metadata sin storage_key/rutas ni detalle del scanner; informa upload_limit_bytes y uploads_configured (presencia, no garantia de salud). POST binario requiere expected_version en query, X-File-Name codificado con encodeURIComponent y Content-Type PDF/PNG/JPEG concordante con extension/firma. A/L/C por alcance, plan/tarea abiertos; G solo lectura. Limite duro10MiB del middleware y evidence_max_bytes vigente BD. Archivo en cuarentena privada, fsync, ClamAV y rename atomico; solo resultado limpio publica y crea fila+version+historia/auditoria. Fallo de commit conocido compensa solo archivo nuevo; commit incierto conserva para reconciliacion, nunca borra evidencias historicas. No job de reconciliacion ni purga automaticos implementados.

GET /evidence/{id}/content autoriza alcance y verifica tamano/hash antes de attachment/nosniff/no-store. Registra solicitud de descarga en audit_events con command=evidence_download_requested, sin contenido/ruta. evidence_files es append-only incluso para migrador; runtime solo SELECT/INSERT. Etapa que exige evidencia verifica existencia/pertenencia/integridad y registra IDs/reglas/versiones en historia. Sin DELETE, tampoco por admin; gestion significa adjuntar/listar/descargar y conservar RN-04/D05.

Configuracion tecnica **explicita del operador**, no sembrada ni escrita por esta tarea:

- EVIDENCE_STORAGE_ROOT: directorio absoluto existente **fuera del checkout/webroot/releases**, con subdirectorios quarantine y objects existentes en el mismo volumen. ACL solo identidad de API/SYSTEM/Administradores en Windows; POSIX sin permisos grupo/otros. Rechaza enlaces/junctions y claves no generadas por servidor. API nunca crea esa configuracion. ACL Windows se valida con APIs nativas, no exige PowerShell (bloqueado por politica1260 en este equipo); la politica no se modifica.
- EVIDENCE_CLAMAV_PORT: puerto elegido/configurado por el operador de un clamd mantenido en127.0.0.1. VERSION e INSTREAM por socket con timeout, respuesta acotada y resultado limpio exacto. VERSION/fecha de definiciones comprobable en UTC, antiguedad maxima24h y tolerancia futura5min; verificar reloj/configuracion UTC del scanner durante homologacion real. Nunca exponer clamd a red compartida.
- EVIDENCE_SCAN_TIMEOUT: limite tecnico5s por intercambio por defecto, rango1..8; no setting empresarial. Error/ausencia/timeout/resultado desconocido/definiciones caducadas503; malware422, tipo415, tamano413. Sin fallback permisivo ni archivo descargable rechazado.

Actualmente ambas opciones obligatorias estan ausentes. No se instalo/configuro antivirus ni se certifico motor/definiciones reales; cargas operativas deshabilitadas. Pruebas inyectan scanner sintetico identificado, no demuestran antimalware real. Antes de habilitar cargas: operador configura ACL/servicio y verifica limpio, muestra de deteccion autorizada, definiciones viejas/servicio caido/timeout, autorizacion y restauracion coherente BD+archivos. No introducir archivos no confiables ni datos reales bajo la excepcion vigente.

## Salud Y Arranque

```bash
backend/.venv/Scripts/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

GET /api/v1/health/live es publico/minimo y no consulta BD. GET /api/v1/health/ready exige X-Health-Token y devuelve 200 solo con conectividad a la base exacta y la unica head del artefacto; revision ausente/desconocida/multiple o fallo de BD devuelve 503 sin detalles. Una marca backend/.local/maintenance.json mantiene ready en 503. Token ausente/incorrecto: 403 antes de acceder a BD. Cada respuesta incluye X-Request-ID; errores usan application/problem+json sin eco de entradas, SQL, credenciales ni trazas.

Swagger/OpenAPI HTTP no estan expuestos. Proxy cliente futuro restringira ready al monitor, sin logs de cabeceras/DSN/query ni exposicion directa; token tecnico no es autenticacion RF-02. Ensayo HTTP F1 se cerro entonces; en F4 ya existia API local activa y se preservo, Angular proxy loopback no es paquete cliente. El arranque NO ejecuta create_all, Alembic, seeds ni conexion a la BD; nunca se migra desde la API.

## Migracion Y Ensayo Local

Cuatro revisiones20261124_0001/0002/0003/0004 inmutables. F1 crea release_history; F2 agrega nueve tablas, F3 seis y F5 evidence_files, sin seeds:18 totales incluyendo alembic_version, no19 objetivo. Downgrade bloqueado: fix-forward o restore aislado aprobado, nunca stamp. Instrucciones F1-F3 siguientes son historicas; no ejecutar sus comandos contra origen F5 ni adaptar helpers.

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

El siguiente comando F3 es historico: su helper se preserva y no se adapta al head F5. Para el checkout vigente usar check-migration F5 de la seccion siguiente:

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/f3_local.py check-migration --execute
unset PGPASSWORD
```

Crea/elimina solo ocote_f2_test_<UUID>/ocote_f2_restore_<UUID>, prefijo aprobado reutilizado sin alterar helpers F1/F2. No actualizador cliente ni orden para repetir apply. Restore --no-acl no prueba recuperar grants; suite/protocolo verifican runtime aparte. recorded contiene running/reconciliar journal; terminal incluye intento terminal. Manifest no firmado/instantanea, no checkout final, cifrado/copia off-host ni recovery de host.

### Migracion Local F5

[f5_local.py](tools/f5_local.py) aplico0003 ->0004 una vez, intento f81efebb-718d-4899-bfec-c34eca858caf, F5_LOCAL_VERIFIED/version2. Operador confirmo API/escritores detenidos y herramienta exigio cero sesiones ajenas. Lock persistente/mantenimiento, before restaurado y migrado/no-op aislado, upgrade/no-op origen y cuatro backups/restores before/after/recorded/terminal (cinco restores contando ensayo de upgrade). Datos/bootstrap/configuracion/legacy y cuatro releases previas identicos; runtime evidencia SELECT/INSERT comprobado. Terminal capturado antes de reapertura; fallo conserva mantenimiento y solo avanza el intento running propio, nunca terminales historicas.

No repetir apply en origen0004, ni aplicar helpers historicos. Con autorizacion PG y credencial administrativa temporal introducida/exportada por el operador, solo ensayo aislado vigente:

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/f5_local.py check-migration --execute
unset PGPASSWORD
```

Solo crea/elimina destinos ocote_f2_test_<UUID>/ocote_f2_restore_<UUID>. Backups/journal protegidos en database/backups/f5-<attempt>/, no Git ni copia de host recuperable. Before F5 no habia tabla/archivos de evidencia; ningun archivo de negocio fue creado por el ensayo. Con archivos operativos futuros, backup/restore coherente BD+archivos es puerta adicional obligatoria, no cubierta por este dump vacio. Manifest es instantanea tecnica sin firma, no hash del checkout final ni actualizador cliente.

## Verificacion Y Limites

```bash
backend/.venv/Scripts/python -m pytest -q backend/tests
OCOTE_RUN_PG_TESTS=1 backend/.venv/Scripts/python -m pytest -q backend/tests
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m pip check
git diff --check
```

F5 sin opt-in: **56 passed,49 skipped**, sin conectar PostgreSQL. Con OCOTE_RUN_PG_TESTS=1: **105 passed,1 warning conocido**,146.69s; requiere PGPASSWORD administrativa temporal local/configuracion/head0004. F1 rollback en origen; F2/F3/F5 UUID aisladas, migrador para Alembic y runtime para API/sinteticos, eliminadas al terminar. Superusuario solo prepara/elimina destinos, nunca API. Sin SQLite ni fixtures de negocio en origen. Ruff/pip check limpios; ACL nativa Windows positiva/Everyone negativa probadas en temporal. Incluye archivo ajeno/invalido/excesivo/malware sintetico/servicio ausente/tamper/fallo commit/409, historia/append-only y filtros/vistas. Deprecacion TestClient/httpx y diagnostico TS6 rootDir ajeno permanecen. Angular59 ChromeHeadless/build392.40kB iniciales98.05kB estimados, chunk lazy de vistas639.74kB, sin ampliar budgets/dependencias. [Resultados/limites](../docs/03-estado-actual-y-roadmap.md#11-kanban-timeline-y-evidencias-f5-local).

D01/formulas del nucleo ratificadas; D03/D08 gerenciales siguen F6. Base D05/objetivos D06 en [guia05](../docs/05-paquetizacion-instalacion-y-actualizaciones.md#31-base-aprobada-de-privacidad-y-recuperacion-d05d06). Excepciones sin suplente/D07 soporte/61 alertas conservadas por F5 hasta2026-12-24, solo local/sintetico; responsable LUIS ANGEL VALLEJO - DESARROLLADOR. Otro host/nube/TLS productivo/capacidad, cifrado/copia off-host/scheduler/firma/homologacion pendientes, no SLA/remediacion. Python3.12.0 no certifica parche productivo; btree_gist disponible no demuestra GiST probado. Adaptador de almacenamiento implementado, configuracion/ClamAV reales e integraciones externas pendientes. Revisiones0001/0002/0003 y package-lock conservan SHA-256 de actas; helpers historicos sin diff.

Siguiente paso: confirmar custodia/bootstrap sin repetir/sobrescribir, completar settings/catalogos/grafo por UI/API y configuration-status, configurar/probar almacenamiento/ClamAV reales y aceptar F4/F5 con sesion del operador. Cierre operativo F5 pendiente; **F6 exige nueva autorizacion y D03/D08**, F7 no iniciado. PostgreSQL queda activo; API F5 iniciada en127.0.0.1:8000 tras parada confirmada por el operador; Angular en127.0.0.1:8443, abrir https://localhost:8443/login. AUTH_ORIGIN/Secure intactos. Sin seeds/configuracion de negocio, reset ni restore sobre origen.
