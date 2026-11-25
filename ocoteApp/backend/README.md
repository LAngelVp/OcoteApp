# OCOTE Backend: Base Tecnica F1

Solo infraestructura: Python 3.12, FastAPI, SQLAlchemy 2.0 sincrono, psycopg 3 y Alembic. No autenticacion de usuarios, administracion ni modulos de negocio. Autoridad: [AGENTS](../AGENTS.md), [SDD](../docs/01-spec-driven-development.md), [arquitectura](../docs/02-arquitectura.md) y [protocolo de release](../docs/05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada). F1 cerrado solo para desarrollo local/sintetico con excepciones hasta 2026-12-24; evidencia, fallos/reintento, hashes y puertas en [acta F1](../docs/03-estado-actual-y-roadmap.md#7-cierre-formal-f1-local).

## Inventario

| Ruta                                                                                                                                                       | Responsabilidad                                                                                   |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| [pyproject.toml](pyproject.toml), [requirements.lock](requirements.lock)                                                                                   | Python >=3.12,<3.13; dependencias incluidas las de prueba fijadas con hashes                      |
| [app/main.py](app/main.py)                                                                                                                                 | Factory FastAPI y ciclo de vida, sin conexion/migracion al arrancar                               |
| [app/core/config.py](app/core/config.py)                                                                                                                   | Variables/.env mediante Pydantic Settings, validacion de DSN/base/rol/IANA y perfil TLS           |
| [app/core/errors.py](app/core/errors.py)                                                                                                                   | problem+json, request_id generado en servidor y logs sanitizados de estado/duracion               |
| [app/db/engine.py](app/db/engine.py), [app/db/session.py](app/db/session.py)                                                                               | Pool acotado, una Session por peticion, unidad de trabajo explicita con commit/rollback           |
| [app/routers/health.py](app/routers/health.py)                                                                                                             | Unicas rutas implementadas: live/ready                                                            |
| [alembic.ini](alembic.ini), [alembic/env.py](alembic/env.py), [alembic/script.py.mako](alembic/script.py.mako)                                             | Configuracion directa de migracion, NullPool y plantilla para revisiones futuras                  |
| [revision inicial](alembic/versions/20261124_0001_technical_foundation.py)                                                                                 | 20261124_0001, solo release_history; Alembic administra alembic_version                           |
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
backend/.venv/Scripts/python -m piptools compile --extra dev --generate-hashes --strip-extras --output-file backend/requirements.lock backend/pyproject.toml
```

## Configuracion Y Roles

Pydantic carga solo backend/.env como archivo, sin ejecutar Bash; las variables de entorno prevalecen. No se carga el .env de raiz ni se exporta todo su contenido. No sobrescribir una configuracion existente. DSN y token son SecretStr; los errores no imprimen entradas sensibles. Las variables requeridas estan en la plantilla, sin defaults de password.

- DATABASE_URL: postgresql+psycopg, base exacta ocoteAppDatabase y usuario ocote_runtime.
- MIGRATION_DATABASE_URL: igual base, usuario ocote_migrador; endpoint directo. La API no utiliza este DSN.
- HEALTH_TOKEN: secreto aleatorio del monitor de al menos 32 caracteres, solo servidor/monitor; no enviarlo a Angular ni en query strings.
- ORGANIZATION_TIMEZONE: requerida y validada IANA; America/Mexico_City es la zona oficial D01 ratificada el 2026-11-24. No hay configuracion operativa en BD todavia; F2 debera usarla solo para bootstrap y aplicar RN-07 sin override runtime.
- APP_ENV/DEPLOYMENT_MODE: desarrollo local solo loopback. Managed exige sslmode=verify-full, hostname y sslrootcert a CA legible en ambos DSN. Validacion de configuracion no demuestra TLS real ni homologa proveedor. Este perfil local rechaza produccion: su habilitacion requiere un perfil aprobado separado.
- Pool local por proceso: size=3, overflow=0, espera/conexion=3 s, statement=5 s, lock=2 s, idle-in-transaction=10 s y UTC. Son limites de desarrollo, no dimensionamiento productivo.

El backend sincrono usa endpoints/dependencias def, ejecutados por FastAPI en threadpool; el cierre del engine tambien sale del event loop. Una Session se cierra al finalizar la peticion, revirtiendo cualquier transaccion pendiente. unit_of_work abre una unica transaccion y confirma solo al salir sin errores; no hay commits automaticos del router ni operaciones de negocio.

Roles ya provisionados en este checkout: runtime CONNECT/USAGE y SELECT de las dos tablas tecnicas; migrador CONNECT y USAGE/CREATE en public, sin privilegios elevados en cluster. PUBLIC perdio CREATE/USAGE en public y permisos sobre la base; cada rol recibe lo necesario explicitamente. Runtime no tiene CREATE, TEMP, INSERT/UPDATE/DELETE/TRUNCATE de bitacora ni membresia del migrador. No hay grants DML automaticos para futuras tablas: cada migracion autorizada debe otorgar permisos minimos y preservar auditoria append-only. Migrador disponible solo durante operacion autorizada; no es una cuenta de la API.

El .env combinado generado es exclusivamente de desarrollo, con contrasenas aleatorias distintas y ACL privada. En despliegue, inyectar al proceso API solo su DSN/token y entregar el DSN migrador por canal operativo separado; no distribuir el .env local ni la credencial publica de preparacion. No existen JWT/usuarios de negocio aun.

## Salud Y Arranque

```bash
backend/.venv/Scripts/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

GET /api/v1/health/live es publico/minimo y no consulta BD. GET /api/v1/health/ready exige X-Health-Token y devuelve 200 solo con conectividad a la base exacta y la unica head del artefacto; revision ausente/desconocida/multiple o fallo de BD devuelve 503 sin detalles. Una marca backend/.local/maintenance.json mantiene ready en 503. Token ausente/incorrecto: 403 antes de acceder a BD. Cada respuesta incluye X-Request-ID; errores usan application/problem+json sin eco de entradas, SQL, credenciales ni trazas.

Swagger/OpenAPI HTTP no estan expuestos. El proxy futuro debe restringir ready al monitor, no reenviar logs de cabeceras/DSN/query ni exponer el servicio directamente; el token tecnico no es autenticacion RF-02. El ensayo HTTP local se cerro y no se dejo Uvicorn en ejecucion. El arranque NO ejecuta create_all, Alembic, seeds ni conexion a la BD; nunca se migra desde la API.

## Migracion Y Ensayo Local

La revision aplicada 20261124_0001 ya es inmutable. Crea solo release_history con checks/FK/indices y trigger de identidad/version/terminales protegidas; alembic_version es metadata de Alembic. No crear las otras 18 tablas por anticipado. Downgrade bloqueado por preservacion de bitacora: usar fix-forward o restore aislado aprobado, nunca stamp.

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

Solo para una comprobacion local expresamente autorizada, con API/escritores detenidos y PGPASSWORD introducida directamente en terminal y exportada como arriba:

```bash
bash scripts/init-dev.sh --check
backend/.venv/Scripts/python backend/tools/f1_local.py verify-existing --execute
unset PGPASSWORD
```

Exige identidad original, unica head tecnica, solo las dos tablas tecnicas y cero sesiones ajenas. Toma lock persistente/mantenimiento, nuevo backup con restore aislado bloqueante y dos upgrades no-op comparando snapshots; preserva las filas release_history existentes **sin mutaciones persistidas** (fixtures de constraints en transacciones revertidas). La comprobacion no es una release: deja su journal/manifests propios en database/backups/f1-closure-<UUID>/, no fabrica otra fila de despliegue. El dump de cierre incluye ambos intentos anteriores ya terminales. Exito limpia solo su destino temporal/marca; fallo conserva mantenimiento/evidencia, sin reset ni reintento automatico. No usar provision/rehearse/retry-verification para repetir este chequeo.

## Verificacion Y Limites

```bash
backend/.venv/Scripts/python -m pytest -q backend/tests
OCOTE_RUN_PG_TESTS=1 backend/.venv/Scripts/python -m pytest -q backend/tests
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m pip check
git diff --check
```

La primera invocacion omite 7 casos PostgreSQL; la segunda requiere configuracion local y revision ya aplicada. Casos reales usan runtime y migrador, sin superusuario, y fixtures transaccionales revertidas; no SQLite ni datos de negocio. Resultado del cierre: 33 passed, lint y pip check correctos; dos negativas nuevas cubren backup fallido antes del no-op y deteccion de mutacion de historia. Una advertencia de deprecacion TestClient/httpx queda registrada, sin cambiar dependencias solo para silenciarla.

D01 ratificada; politica D05 y objetivos/responsable D06 aprobados en [guia 05, seccion 3.1](../docs/05-paquetizacion-instalacion-y-actualizaciones.md#31-base-aprobada-de-privacidad-y-recuperacion-d05d06). Excepcion expresa sin suplente y excepciones separadas D07 por soporte Angular/61 alertas npm hasta 2026-12-24, solo desarrollo local F1/F2 con datos sinteticos; responsable LUIS ANGEL VALLEJO - DESARROLLADOR. Build/prototipo/peers pasaron, no remediacion de seguridad. Otro host/nube/TLS/capacidad, cifrado/copia off-host, programacion de backups, firma y homologacion cliente siguen pendientes; no SLA demostrado. El Python observado es 3.12.0 local: no certifica un nivel de parche productivo. btree_gist disponible no equivale a extension instalada/probada con exclusion GiST. No instalador/ocote-admin, login/JWT/CSRF, almacenamiento ni integraciones.

Siguiente paso: aprobar D02/D04 y custodia/bootstrap del primer admin y autorizar F2 (identidad, permisos, parametros/catalogos y administracion) con revisiones propias, sin exceder las excepciones locales ni su fecha. F2 no iniciado ni autorizado en este cierre.
