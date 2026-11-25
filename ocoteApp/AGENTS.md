# OCOTE: instrucciones para agentes y desarrolladores

Este archivo es el punto de entrada independiente de editor/agente. Leerlo al retomar un clon nuevo; no depender de chats, memoria privada del agente o rutas personales. Si tu herramienta no lo descubre automaticamente, cargarlo explicitamente antes de actuar. El adaptador de Copilot remite aqui, no define una arquitectura distinta.

## Lectura y autoridad

1. [README.md](README.md): entrada y comandos disponibles.
2. [docs/01-spec-driven-development.md](docs/01-spec-driven-development.md): permisos por menu/ruta/accion/datos, RF-01..RF-15, RN-01..RN-07, D01..D08, contratos y tokens.
3. [docs/02-arquitectura.md](docs/02-arquitectura.md): capas, datos, seguridad y despliegue.
4. [docs/03-estado-actual-y-roadmap.md](docs/03-estado-actual-y-roadmap.md): evidencia, F0..F7, dependencias y Definition of Done.
5. [docs/04-entorno-y-portabilidad.md](docs/04-entorno-y-portabilidad.md): PostgreSQL, credencial exclusivamente local, clon nuevo, backups y diagnostico.
6. [docs/05-paquetizacion-instalacion-y-actualizaciones.md](docs/05-paquetizacion-instalacion-y-actualizaciones.md): paquete/instalacion local o gestionada, bootstrap, integraciones/exports y fuente unica del protocolo de release (seccion 7).

Los documentos de dominio gobiernan comportamiento; esta guia gobierna como trabajar. Ante discrepancia con el checkout, verificar evidencia y actualizar documentos afectados antes de implementar. Una autorizacion nueva del usuario cambia el alcance solo de forma explicita; nunca convertir una solicitud documental en desarrollo de negocio.

## Identidad y stack

- OCOTE: gestion de planes con horizontes configurables (incluidos anuales), ejecucion operativa y evaluacion gerencial; constancia, claridad y trazabilidad. No es un ranking automatico de personas.
- Monorepo sin Nx: Angular permanece en raiz; backend/ tecnico ya existe dentro del mismo proyecto. docs/ contiene especificacion; scripts/ contiene utilidades de desarrollo.
- Frontend: Angular 18.2 standalone, SPA sin SSR, SCSS, Material 3 custom, Animations, CDK drag-drop, ngx-echarts 18.x / Apache ECharts y vis-timeline. No actualizar versiones/lock automaticamente; compatibilidad y soporte son puerta D07.
- Backend F1-F3: Python3.12/FastAPI/Pydanticv2/SQLAlchemy2/psycopg3/Alembic, Argon2id/RS256. Salud, identidad/admin y nucleo operativo por capas routers -> schemas/policies -> services -> models/BD; no F4-F7. [Runbook](backend/README.md).
- BD real: PG18.4 Windows, database/postgres/bin, cluster18 database/data, logs database/logs; 127.0.0.1:5432/ocoteAppDatabase exacta, head20261124_0003, 17 tablas/cuatro releases terminales. Seis F3 vacias; bootstrap posterior del operador observado (1 usuario/1 audit_event), configuracion pendiente. ocote conservada; no PG16 ni editar PG_VERSION.
- Planes/objetivos: start_date, due_date y horizon_type = annual/semiannual/quarterly/monthly/custom; rangos inclusivos elegidos por el responsable, incluidos cruces de anio y multiples planes simultaneos. annual_plans/annual_plan_id son nombres tecnicos estables, no un limite anual. Contencion plan -> objetivo -> fechas de tarea; cambio de periodo con motivo/version/audit_events, sin cascada ni alteracion de originales. Ver RN-01/RN-02/RN-06.

## Estado y alcance permitido

F0/F1/F2 consolidados; **F3 autorizado, implementado y verificado local/sintetico**, [evidencia vigente](docs/03-estado-actual-y-roadmap.md#9-nucleo-operativo-f3-local). Formulas del nucleo/cierre ratificados, D03/D08 gerenciales pendientes F6. Confirmar custodia/bootstrap existente sin sobrescribir; configuracion explicita pendiente. F4-F7 no autorizados/iniciados. Orden F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7.

D01 America/Mexico_City solo bootstrap RN-07. Politica D05 y objetivos D06 RPO <=24 h/RTO <=4 h aprobados, no SLA; responsable LUIS ANGEL VALLEJO - DESARROLLADOR. Excepciones conservadas por F3 hasta **2026-12-24**: D06 sin suplente (sin responsable suspender migraciones/restores); D07 soporte Angular18 y, separadamente, 61 alertas npm (2 criticas/19 altas/33 moderadas/7 bajas). Solo F1-F3 local/sintetico, sin exposicion/red compartida ni entradas/plantillas/archivos no confiables; no remediacion/aprobacion productiva. Antes de vencer: suplente independiente capacitado y migracion autorizada/remediacion con audit/peers/prototipo/pruebas/build repetidos, o nueva decision expresa, sin renovacion automatica. Cambio de exposicion/nuevas alertas exige reevaluar.

F3 permite solo planes/objetivos/tareas/subtareas/historia/solicitudes API; sin UI, evidencia/Kanban/Timeline, analytics/evaluaciones/exports ni nube. **Sin seeds/defaults ni fixtures en origen**; preservar bootstrap del operador, nunca inventar identidad/configuracion. CLI sin overwrite/getpass; cuatro settings/cinco horizontes/normal activa/grafo valido explicitos via API. configuration-status incompleto es esperado y altas operativas fallan cerradas. Tres revisiones aplicadas inmutables. Evidencia requerida devuelve422 hasta F5. Firma/cifrado off-host/scheduler/TLS/capacidad/homologacion pendientes, no SLA. Antes de F4: configuracion explicita, muestra accesible OCOTE/licencia tipografica/Material18.2 y autorizacion expresa; 19 tablas siguen objetivo.

## Permisos, parametros e integraciones

- Aplicar matriz SDD en servidor antes de consultar/paginar/agregar, no solo en menu/guard. Colaborador solo tareas asignadas/contexto minimo: sin analitica, agregados departamentales/globales, exports, evaluaciones o administracion. Lider solo departamento y finales propias; gerente no mueve tareas. URL/API directa conserva 401/403/404 segun SDD.
- Configuracion operativa en system_settings tipado y catalogos priorities/horizon_types/workflow en BD, con version/motivo/lock/audit_events; cinco codes de horizonte estables, normal/custom protegidos. ORGANIZATION_TIMEZONE solo bootstrap; zona en BD bloqueada tras primera tarea/evaluacion. Roles/formulas/permisos son codigo, no JSON ejecutable. Secrets/DSN/JWT en entorno o gestor, nunca BD configurable/SPA/logs. RN-07 y diccionarios son autoridad.
- Solicitudes de fecha se persisten en due_date_requests; aprobar por A/G distinto de solicitante verifica versiones/alcance y cambia fecha+task_history+decision atomicamente; no flujo informal externo ni cambio de original. REST/OpenAPI y exports internos acotados segun guia 05; ERP/SSO/mensajeria/webhooks/IA/importacion masiva fuera de MVP. No usar tokens humanos como integracion.

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

Password conocida SOLO local, nunca reutilizar/subir secretos/pgpass/data/logs/backups ni imprimir entornos. API ocote_runtime, Alembic ocote_migrador, nunca postgres runtime. Roles/configuracion existentes: no provision/rehearse ni regenerar secretos. Comandos F1/F2 son historicos; no usarlos en origen F3 ni adaptar helpers. f2_local apply0002 y f3_local apply0003 ya ejecutados: no repetir. f3_local check-migration solo destinos UUID aislados con prefijo tecnico ocote_f2 reutilizado. Fallo conserva maintenance/evidencia, sin retirada manual; verificar identidad antes de migracion autorizada, nunca create_all/stamp.

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
- Tema OCOTE: tokens canonicos --ocote-\* de la SDD, no volver a escoger paleta. Primary #B85A1E, Bosque #2E5A44, acento/warning #D98A1C; success #2E7D5B, danger #B83227; colores/on-colors y demas tokens en SDD. Material 3 exige paletas tonales completas, no un hex ni APIs de otras versiones. Kanban/Timeline/ECharts comparten semantica, contraste AA y alternativas accesibles; tema aun no aplicado al scaffold.
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
git diff --check
```

Suite helper usa mocks/temporales, no data real. Solo docs: enlaces/anclas/fences/JSON/IDs/modelo y diff, sin reconectar BD. Backend: OCOTE_RUN_PG_TESTS=1 activa casos reales (F1 rollback, F2 bases UUID aisladas); requiere credencial administrativa local temporal para preparar/eliminar destinos, nunca API. Resultado F2 y conteo vigentes en runbook/acta; Ruff/pip check obligatorios. Angular npm ci solo si necesario/revisado D07; build y 6 pruebas ChromeHeadless historicas F1, 3 fixtures no E2E. No declarar remediacion por pasar build. ocote-admin no existe; no confundir CLI local con paquete cliente.

Al cerrar una tarea indicar archivos cambiados, verificaciones y limites, estado de BD si se arranco y siguiente paso de la fase correspondiente. No dejar conocimiento esencial unicamente en el chat.
