# OCOTE: instrucciones para agentes y desarrolladores

## Autorizacion vigente F7 (2026-11-25)

Ajuste vigente del titular: completar0006/boveda AES-256-GCM, configuracion BD de almacenamiento privado local/ClamAV fail-closed, custodia cliente titular/suplente y salud administrativa, endpoints /api/v1 y formularios Angular, suites PG0/PG1, Ruff/pip, ChromeHeadless/build/visual1280 y360 CSS, release preservando datos y reinicio API. Setup Wizard e instalador/empaquetador in-house quedan diferidos al cierre final despues de branding/F8..F12; esas fases siguen sin autorizacion. Ensayos y release usan relevo administrativo temporal DPAPI introducido en tarea visible, descifrado solo en proceso local/exportacion temporal PGPASSWORD y revocado al acabar PG. No imprimirlo ni usarlo en runtime. Estado verificable y limites en acta19; no confundir implementacion del incremento con homologacion cliente.

**Resultado vigente:** [incremento F7 acotado completado](docs/03-estado-actual-y-roadmap.md#cierre-del-incremento-f7-acotado), head20261125_0006/26 tablas/siete releases, datos previos preservados. Desde su aplicacion0006 tambien es inmutable; proximos cambios de esquema requieren0007 o posterior, nunca repetir apply F7 ni inicializar otra raiz. PG0:105/73 omitidas, PG1:178 aprobadas, Angular171/171/build/visual1280-360 CSS, Ruff/pip limpios. API activa127.0.0.1:8000/live y ready200; relevo administrativo eliminado. Consola /administracion/infraestructura y API /api/v1/admin disponibles; custodia incompleta, sin proveedores configurados/cargas cerradas. No inventar contactos, ruta ni antivirus disponible. Wizard y empaquetado siguen diferidos al cierre final posterior a F8..F12 no autorizadas. Las referencias F6/doc-only que siguen son historicas en lo sustituido por esta acta, no autorizaciones de revertir estado ni de omitir invariantes.

F7 esta autorizada y en curso segun [acta19](docs/03-estado-actual-y-roadmap.md#19-f7-autorizada-ejecucion-en-curso), no cerrada; F8..F12 siguen bloqueadas. Esta orden sustituye exclusivamente las restricciones de la tarea documental previa y los bloqueos de inicio F7 citados mas abajo; conserva invariantes, puertas de liberacion y evidencias historicas. Angular21 LTS reemplaza la linea18.2 del inventario historico: migraciones oficiales/build/164 pruebas aprobados, audit0 criticas/altas y21 moderadas, no auditoria limpia. Se autorizan package.json/package-lock.json y ajustes Angular necesarios; backend/requirements.lock sigue intocable, cryptography50.0.2 disponible. No editar0001..0005, scripts, tools/f1_local.py..f6_local.py/f6_visual.cjs ni alterar datos previos. Nueva0006/herramientas F7 requieren ensayo aislado bloqueante antes del origen.

D06: LUIS ANGEL VALLEJO - DESARROLLADOR es autor unico de ingenieria/artefactos locales, sin suplente interno ficticio ni bloqueo de desarrollo por esa modalidad. La custodia cliente titular/suplente independiente ya tiene BD/API/UI versionadas/auditadas, pero sus nombres/contactos no se precargan: completar contactos no acredita capacitacion, recuperacion ni aceptacion operativa. Sin nueva entrada administrativa privada del operador no ejecutar mas ensayos UUID ni migraciones; el relevo de esta sesion fue eliminado. Nunca pedir secretos por chat, reutilizar runtime como administrador o modificar helpers historicos. Consultar acta19 antes de retomar.

Este archivo es el punto de entrada independiente de editor/agente. Leerlo al retomar un clon nuevo; no depender de chats, memoria privada del agente o rutas personales. Si tu herramienta no lo descubre automaticamente, cargarlo explicitamente antes de actuar. El adaptador de Copilot remite aqui, no define una arquitectura distinta.

## Lectura y autoridad

1. [README.md](README.md): entrada y comandos disponibles.
2. [docs/01-spec-driven-development.md](docs/01-spec-driven-development.md): permisos/contratos/tokens, base RF-01..RF-15/RN-01..RN-07/D01..D08 y evolucion documental RF-16..35/RN-08..20/D09..16.
3. [docs/02-arquitectura.md](docs/02-arquitectura.md): capas, datos, seguridad y despliegue.
4. [docs/03-estado-actual-y-roadmap.md](docs/03-estado-actual-y-roadmap.md): evidencia F0..F6, F7 bloqueada y F8..F12 propuestas, dependencias/Definition of Done por autorizacion.
5. [docs/04-entorno-y-portabilidad.md](docs/04-entorno-y-portabilidad.md): PostgreSQL, credencial exclusivamente local, clon nuevo, backups y diagnostico.
6. [docs/05-paquetizacion-instalacion-y-actualizaciones.md](docs/05-paquetizacion-instalacion-y-actualizaciones.md): paquete/instalacion local o gestionada, bootstrap, integraciones/exports y fuente unica del protocolo de release (seccion 7).

Los documentos de dominio gobiernan comportamiento; esta guia gobierna como trabajar. Ante discrepancia con el checkout, verificar evidencia y actualizar documentos afectados antes de implementar. Una autorizacion nueva del usuario cambia el alcance solo de forma explicita; nunca convertir una solicitud documental en desarrollo de negocio.

## Identidad y stack

- OCOTE: gestion de planes con horizontes configurables (incluidos anuales), ejecucion operativa y evaluacion gerencial; constancia, claridad y trazabilidad. No es un ranking automatico de personas.
- Monorepo sin Nx: Angular permanece en raiz; backend/ tecnico ya existe dentro del mismo proyecto. docs/ contiene especificacion; scripts/ contiene utilidades de desarrollo.
- Frontend: Angular 18.2 standalone, SPA sin SSR, SCSS, Material 3 custom, Animations, CDK drag-drop, ngx-echarts 18.x / Apache ECharts y vis-timeline. No actualizar versiones/lock automaticamente; compatibilidad y soporte son puerta D07.
- Backend F1-F3/F5/F6: Python3.12/FastAPI/Pydanticv2/SQLAlchemy2/psycopg3/Alembic, Argon2id/RS256. Salud, identidad/admin, nucleo, evidencia/vistas y analitica/evaluaciones/exports internos por alcance; F7 bloqueado. [Runbook](backend/README.md).
- BD real: PG18.4 Windows, database/postgres/bin, cluster18 database/data, logs database/logs;127.0.0.1:5432/ocoteAppDatabase exacta, head20261125_0005,19 tablas de dominio/20 contando Alembic y seis releases terminales. Datos/configuracion/bootstrap previos preservados; evidencia/evaluaciones/items vacios al cierre F6. ocote conservada; no PG16 ni editar PG_VERSION.
- Planes/objetivos: start_date, due_date y horizon_type = annual/semiannual/quarterly/monthly/custom; rangos inclusivos elegidos por el responsable, incluidos cruces de anio y multiples planes simultaneos. annual_plans/annual_plan_id son nombres tecnicos estables, no un limite anual. Contencion plan -> objetivo -> fechas de tarea; cambio de periodo con motivo/version/audit_events, sin cascada ni alteracion de originales. Ver RN-01/RN-02/RN-06.

## Estado y alcance permitido

F0-F3 consolidados; F4/F5 tecnicas preservadas y **F6 autorizada/implementada/migrada local/sintetico**, [evidencia vigente](docs/03-estado-actual-y-roadmap.md#17-analitica-evaluaciones-y-exports-f6-local-2026-11-25). Cierre operativo F5/aceptacion del operador y almacenamiento/ClamAV reales pendientes; no inventarlos ni sobrescribir bootstrap/custodia. D03/D08/RN-06 ratificados, calendario manual, evaluacion departamental sin ranking/score y corte real al generar. F7 no autorizado/iniciado. Orden F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7; se autorizo F6 expresamente sin fingir aceptacion operativa F5.

### Evolucion empresarial documental

- [SDD,seccion8](docs/01-spec-driven-development.md#8-evolucion-empresarial-propuesta) especifica20 RF nuevos,13 RN y8 decisiones; [arquitectura,seccion8](docs/02-arquitectura.md#8-arquitectura-empresarial-proyectada) proyecta47 tablas nuevas, no creadas. No cambiar conteo instalado/head ni anunciar wizard/SSO/colas/integraciones como disponibles.
- [Roadmap18](docs/03-estado-actual-y-roadmap.md#18-evolucion-empresarial-documental): F7 endurecimiento/instalador/PG flexible/in-house, luego F8 configuracion/branding, F9 extensiones de dominio, F10 notificaciones, F11 identidad/conectores/API, F12 imports/reportes/operacion. Cada fase exige autorizacion expresa/puertas/DoD; ni esta especificacion ni flags las habilitan. D06/D07 no se renuevan por documentar.
- Objetivo futuro: toda configuracion funcional/visual/seguridad/limites/modulos/almacenamiento/antivirus/correo/chat/SSO/integraciones en PostgreSQL. Unica excepcion: conexion PG/CA inicial/credenciales por identidad y raiz MASTER_ENCRYPTION_KEY generada/sellada en almacen SO. Boveda AEAD/write-only, nunca secreto plano/ciphertext por GET; roles/formulas/permisos/fail-closed son codigo, no JSON ejecutable. [Entrega futura](docs/05-paquetizacion-instalacion-y-actualizaciones.md#9-entrega-empresarial-sin-archivos-operativos) gobierna transicion, sin editar/borrar .env actuales ni reiniciar servicios por docs.
- En esta tarea exclusivamente documental son intocables codigo backend/src, todas las migraciones aplicadas0001..0005, backend/tools/f1_local.py..f6_local.py/f6_visual.cjs, scripts, package-lock y database. backend/README.md es la unica excepcion documental bajo backend expresamente solicitada. No conectar PG, ejecutar init-dev/build/tests de negocio ni probar endpoints/proveedores; solo validar Markdown/JSON/IDs/modelo/diff. Futuros cambios requieren nuevas revisiones/herramientas, no reutilizar helpers inmutables como actualizador cliente.
- Preservar etapa/avance/puntualidad, cuatro roles/alcance, originales/cortes sellados y no ranking, zona RN-07, memoria/cookies/CSRF/Web Locks, expected_version/409/request_id, roles SQL separados e historia append-only. Ninguna plantilla, calendario, conector o import precarga catalogos/datos sinteticos ni modifica hechos finales; retencion no autoriza purga.

D01 America/Mexico_City solo bootstrap RN-07. Politica D05/objetivos D06 RPO <=24 h/RTO <=4 h aprobados, no SLA; responsable LUIS ANGEL VALLEJO - DESARROLLADOR. Excepciones extendidas a F6 hasta **2026-12-24**: D06 sin suplente (sin responsable suspender migraciones/restores); D07 soporte Angular18 y, separadamente,61 alertas npm (2 criticas/19 altas/33 moderadas/7 bajas). Solo F1-F6 local/sintetico, sin red compartida ni entradas/plantillas/archivos no confiables; no remediacion/productivo. Antes de vencer: suplente independiente capacitado y migracion/remediacion autorizadas con nuevas pruebas, o decision expresa, sin renovacion automatica. Cambio de exposicion/nuevas alertas exige reevaluar.

F4 agrega UI F2/F3, F5 evidencia/Kanban/Timeline y F6 analitica/evaluacion/exports internos, sin nube. **Sin seeds/defaults ni fixtures en origen**; preservar datos/bootstrap, nunca inventar identidad/configuracion/periodos/evaluadores. CLI sin overwrite/getpass; cuatro settings/cinco horizontes/normal activa/grafo valido explicitos por UI/API. configuration-status incompleto esperado, altas operativas fail-closed. Cinco revisiones aplicadas inmutables. Evidencia requiere IDs de misma tarea, ACL privada fuera del checkout, limite BD/MIME/extension/firma/hash y ClamAV fresco/limpio; ausente/error/desconocido503, malware422. Sin DELETE/purga; publicacion/version/historia atomicas con compensacion del archivo nuevo. Scanner/config reales pendientes: cargas cerradas. Firma/cifrado off-host/scheduler/TLS productivo/capacidad/homologacion pendientes, no SLA. Cierre operativo F5 requiere aceptacion/configuracion y ensayo real D05.

F4 usa rutas standalone lazy, formularios reactivos/Material18.2 y HttpClient relativo /api/v1. Access/CSRF solo memoria, cookie refresh exclusivamente navegador; Web Locks obligatorios mas single-flight por pestana y BroadcastChannel de cierre. Origin generado por navegador/Referer same-origin; no fabricar esas cabeceras ni bajar Secure. Retry401 una vez; segundo401/revocacion limpia identidad,503 de logout no finge cierre. 409 conserva formulario y bloquea reenvio hasta descarte/recarga explicitos. Guards no sustituyen rol/alcance del servidor. Proxy de desarrollo loopback en guia04; AUTH_ORIGIN existente https://localhost:8443 no se cambia por pruebas.

## Permisos, parametros e integraciones

- Aplicar matriz SDD en servidor antes de consultar/paginar/agregar, no solo en menu/guard. Colaborador solo tareas asignadas/contexto minimo: sin analitica, agregados departamentales/globales, exports, evaluaciones o administracion. Lider solo departamento y finales propias; gerente no mueve tareas. URL/API directa conserva 401/403/404 segun SDD.
- Configuracion operativa F1-F6 en system_settings tipado y catalogos priorities/horizon_types/workflow en BD, con version/motivo/lock/audit_events; cinco codes de horizonte estables, normal/custom protegidos. ORGANIZATION_TIMEZONE solo bootstrap; zona en BD bloqueada tras primera tarea/evaluacion. Roles/formulas/permisos son codigo, no JSON ejecutable. Secrets/DSN/JWT actuales en entorno/gestor, nunca settings/SPA/logs; futuro F7+ usa boveda cifrada y bootstrap minimo segun D09/D10, no implementados. RN-07 y diccionarios son autoridad.
- Solicitudes de fecha se persisten en due_date_requests; aprobar por A/G distinto de solicitante verifica versiones/alcance y cambia fecha+task_history+decision atomicamente; no flujo informal externo ni cambio de original. REST/OpenAPI y exports internos acotados segun guia 05; ERP/SSO/mensajeria/webhooks/IA/importacion masiva fuera de MVP. No usar tokens humanos como integracion.
- F6: cohorte original inclusiva/todas las tareas/vacios null; REPEATABLE READ por peticion, no corte unico entre endpoints. Maximo10000 tareas/1200 meses y413 sin truncar. Draft solo recalculo explicito; finalize recalcula/sella, summary10..4000/periodo concluido/no vacio/expected_version. Final/items inmutables y no solapamiento incluso draft. Exports solo finales/alcance, export_max_rows+1/16MiB/CSV seguro/auditoria fail-closed. Tablas5/10/20/50 y ECharts con tokens/tablas equivalentes. C sin reportes; L solo departamento/finales; A/G gestionan evaluaciones, G no mueve tareas.

## PostgreSQL antes de backend o Alembic

Solo para desarrollo local autorizado, desde raiz en Bash/Git Bash con credencial publica descrita en guia 04 (no ejecutar por una tarea puramente documental):

```bash
bash scripts/init-dev.sh --check
```

Si esta detenido o falta ocoteAppDatabase, y la operacion local esta autorizada:

```bash
bash scripts/init-dev.sh
bash scripts/init-dev.sh --check
```

init-dev resuelve la raiz, delega validaciones en db-start.sh y muestra backend/.venv, backend/alembic y node_modules sin instalarlos/ejecutarlos. Usa PGPASSWORD del entorno o fallback publico holamundo SOLO para desarrollo/test; nunca imprime la password ni carga .env automaticamente. Para PGPASSFILE sin fallback usar db-start.sh sin --local-dev y con PGPASSWORD sin definir, como explica la guia. No cambiar el nombre a minusculas en SQL ni apuntar a otra base para sortear un error.

Git NO incluye binarios ni cluster. Un fallo de check no autoriza initdb, restore, matar procesos o borrar data/postmaster.pid. El helper valida version/puerto/identidad, nunca resetea, migra, hace seeds ni detiene un servidor. No envolver errores con `|| true` para continuar hacia Alembic.

Password conocida SOLO local, nunca reutilizar/subir secretos/pgpass/data/logs/backups ni imprimir entornos. API ocote_runtime, Alembic ocote_migrador, nunca postgres runtime. No provision/rehearse ni regenerar secretos. Comandos F1-F3/F5 historicos: no ejecutarlos en origen F6 ni adaptar helpers. apply0002/0003/0004/0005 ya ejecutados: no repetir. f6_local check-migration solo UUID aislados ocote_f2 y autorizacion PG, via PYTHONPATH=backend/python -m tools.f6_local. Artefactos F6 privados fuera del checkout. CREATE temporal del migrador se autorizo solo para btree_gist en este release y ya se revoco; no permiso permanente/general. Fallo conserva maintenance/evidencia, sin retirada manual; nunca create_all/stamp.

Cliente local/contenedor o PG18 gestionado usa guia 05, nunca init-dev. Nube exige TLS verify-full/CA/hostname, red privada/firewall, btree_gist y roles aprobados, pools acotados y endpoint directo de migracion/lock. No adaptar helper a remoto ni afirmar soporte de proveedor/SO sin ensayo F1/F7. Binarios de desarrollo no son paquete cliente.

## Actualizaciones del cliente y migraciones

Toda release local/gestionada sigue [guia 05, seccion 7](docs/05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada): paquete firmado/head compatible, lock persistente, maintenance sin escritores, backup automatico y restore aislado, Alembic/seeds, integridad/smoke y reapertura aprobada o contingencia. Arranque local no lo sustituye. release_history registra intentos; alembic_version solo revision; bitacora externa cubre fallos antes de BD/tabla y se reconcilia tras restore.

- Cambios de esquema/backfill solo en revisiones Git bajo backend/alembic/versions; no DDL manual, create_all, stamp head ni revision ya publicada modificada. Una sola head por artefacto inmutable; repetir alembic upgrade head debe ser no-op si ya se aplico.
- Expand/backfill/validate/contract para NOT NULL, renombres y tipos; no truncar/borrar/reescribir task_history, audit_events, originales, solicitudes/releases terminales ni fotos. Seeds agregan faltantes por code/key, nunca pisan parametros/catalogos operativos, personas o credenciales.
- Si falla: mantener mantenimiento y evidencia, revisar revision/estado parcial, preferir fix-forward. Downgrade solo reversible y probado con autorizacion; restore a destino aislado y switchover aprobado, nunca sobrescribir data/. Tras nuevas escrituras no prometer rollback sin perdida; reconciliar antes.
- Existen backend/Alembic y ensayo tecnico local, no actualizador cliente, paquete firmado ni ocote-admin. F7 homologa instalaciones completas; no inventar migraciones ejecutadas o respaldos restaurados por haber pasado init-dev.

## Convenciones obligatorias

- Mantener IDs RF-_, RN-_, D* y F*; no renumerar para acomodar cambios. Actualizar contratos y criterios primero, implementar lo minimo de la fase autorizada y dejar evidencia verificable.
- Nombres de API/BD snake_case, UUID, fechas civiles para compromisos y timestamps UTC. Conservar original_due_date inmutable, due_date vigente y completed_at del servidor. Etapa, avance y puntualidad son conceptos separados; formulas canonicas en RN-02/RN-03/RN-06.
- Roles exactos admin, gerente, lider, colaborador; autorizacion por rol Y alcance en servidor, incluidas metricas, evidencia e historia. Mutacion e historial en una transaccion con control de version. No ocultar fallos de concurrencia.
- F3: configuracion compartida para comandos/consultas operativos, exclusiva para auth/admin. Orden de filas departamento -> usuarios UUID ordenados -> plan -> objetivo -> tarea -> subtarea -> solicitud. Flush explicito une datos/version/historia/decision; no commits en routers ni DELETE. Originales/cierre/solicitudes terminales protegidos; fechas civiles ISO estrictas y timestamps UTC.
- Tema OCOTE aplicado en F4: tokens canonicos --ocote-\* de la SDD en src/_ocote-tokens.scss y paletas M3 completas en src/_ocote-palettes.scss. Primary #B85A1E, Bosque #2E5A44, acento/warning #D98A1C; success #2E7D5B, danger #B83227. Roles tonales distintos de marca documentados en SDD; mat.core una vez, overrides Sass publicos, no variables privadas. Source Sans3/Material Icons locales licenciados. Foco visible sobre Material y radios8px comprobados. Kanban/Timeline/ECharts futuros deben reutilizar semantica y alternativas accesibles; no afirmar homologacion AA completa por la revision tecnica F4.
- Reutilizar patrones locales y evitar dependencias, carpetas o abstracciones innecesarias. Sin cambios productivos solo para satisfacer un ejemplo documental. No mover Angular a otra carpeta.
- Respetar cambios ajenos; no hacer reset/checkout destructivo, commits, cambios de rama, actualizaciones de dependencias ni operaciones destructivas de BD sin solicitud explicita. No editar binarios ni archivos internos de data/.
- Tras un cambio, ejecutar primero la validacion enfocada. Para DB, usar mocks en tests y PostgreSQL real solo para comprobaciones autorizadas; no afirmar que SQLite valida constraints PostgreSQL. Mantener el estado actual al dia al finalizar.

## Comandos disponibles

```bash
bash -n scripts/init-dev.sh
bash -n scripts/db-start.sh
node --test scripts/db-start.test.cjs
backend/.venv/Scripts/python -m pytest -q backend/tests
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m pip check
npm run build
CHROME_BIN='C:/Program Files/Google/Chrome/Application/chrome.exe' npm test -- --watch=false --browsers=ChromeHeadless --progress=false --reporters=dots
git diff --check
```

Suite helper mocks/temporales, no data real. Solo docs: enlaces/anclas/fences/JSON/IDs/modelo/diff, sin reconectar BD. Backend OCOTE_RUN_PG_TESTS=1: F1 rollback, F2/F3/F5/F6 UUID aisladas; credencial administrativa temporal solo para preparar/eliminar destinos, nunca API. F6 agrega30 pruebas focales; resultados globales en acta F6, Ruff/pip check obligatorios. Angular164 ChromeHeadless/build/revision visual F6; node backend/tools/f6_visual.cjs usa API interceptada/perfil desechable/artefactos temporales. npm ci solo si necesario/revisado D07. Mocks no son antivirus real/E2E en origen/homologacion productiva ni remediacion. ocote-admin no existe; no confundir CLI local con paquete cliente.

Al cerrar una tarea indicar archivos cambiados, verificaciones y limites, estado de BD si se arranco y siguiente paso de la fase correspondiente. No dejar conocimiento esencial unicamente en el chat.
