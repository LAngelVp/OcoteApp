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
- Monorepo sin Nx: Angular permanece en raiz; backend/ se creara dentro del mismo proyecto. docs/ contiene especificacion; scripts/ contiene utilidades de desarrollo.
- Frontend: Angular 18.2 standalone, SPA sin SSR, SCSS, Material 3 custom, Animations, CDK drag-drop, ngx-echarts 18.x / Apache ECharts y vis-timeline. No actualizar versiones/lock automaticamente; compatibilidad y soporte son puerta D07.
- Backend planeado: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, psycopg 3 y Alembic; routers -> schemas/policies -> services transaccionales -> models/BD. Aun no existe backend/ ni hay migraciones.
- BD real: PostgreSQL 18.4 portable Windows en database/postgres/bin; cluster mayor 18 en database/data; logs en database/logs; host 127.0.0.1, puerto 5432, base exacta ocoteAppDatabase vacia al corte 2026-11-24. La base anterior ocote se conserva sin renombrar/copiar/borrar. No instalar PostgreSQL 16 sobre este cluster ni editar PG_VERSION.
- Planes/objetivos: start_date, due_date y horizon_type = annual/semiannual/quarterly/monthly/custom; rangos inclusivos elegidos por el responsable, incluidos cruces de anio y multiples planes simultaneos. annual_plans/annual_plan_id son nombres tecnicos estables, no un limite anual. Contencion plan -> objetivo -> fechas de tarea; cambio de periodo con motivo/version/audit_events, sin cascada ni alteracion de originales. Ver RN-01/RN-02/RN-06.

## Estado y alcance permitido

F0 documental consolidado; helper local probado y base vacia disponible. F1 NO esta terminado: faltan backend, roles tecnicos, migraciones, compatibilidad del stack y restauracion probada. F2-F7 no iniciados. Las dependencias siguen F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7.

Este cierre solo autoriza documentacion/instrucciones; helpers de desarrollo previos se conservan sin cambios. NO autoriza codigo productivo, componentes funcionales Angular, routers/services FastAPI ni migraciones ejecutables de negocio. Antes de base tecnica F1 solicitar autorizacion y resolver D01/D05/D06/D07 aplicables. D06 desarrollo portable confirmado, no RPO/RTO/restore/produccion. No inventar aprobaciones, zona, SLA o resultados. Las 19 tablas del modelo son objetivo, no tablas existentes; F1 tecnica no crea todo el dominio por anticipado.

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

La password conocida es SOLO local y no se reutiliza. Nunca subir .env, tokens, pgpass, datos, logs ni respaldos; no imprimir variables de entorno completas. El backend productivo no usa el superusuario postgres: F1 debe definir rol dedicado runtime y rol de migraciones. Verificar PG_VERSION, conectividad y base objetivo antes de cualquier migracion autorizada; nunca `create_all()` automatico en produccion.

Cliente local/contenedor o PG18 gestionado usa guia 05, nunca init-dev. Nube exige TLS verify-full/CA/hostname, red privada/firewall, btree_gist y roles aprobados, pools acotados y endpoint directo de migracion/lock. No adaptar helper a remoto ni afirmar soporte de proveedor/SO sin ensayo F1/F7. Binarios de desarrollo no son paquete cliente.

## Actualizaciones del cliente y migraciones

Toda release local/gestionada sigue [guia 05, seccion 7](docs/05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada): paquete firmado/head compatible, lock persistente, maintenance sin escritores, backup automatico y restore aislado, Alembic/seeds, integridad/smoke y reapertura aprobada o contingencia. Arranque local no lo sustituye. release_history registra intentos; alembic_version solo revision; bitacora externa cubre fallos antes de BD/tabla y se reconcilia tras restore.

- Cambios de esquema/backfill solo en revisiones Git bajo backend/alembic/versions; no DDL manual, create_all, stamp head ni revision ya publicada modificada. Una sola head por artefacto inmutable; repetir alembic upgrade head debe ser no-op si ya se aplico.
- Expand/backfill/validate/contract para NOT NULL, renombres y tipos; no truncar/borrar/reescribir task_history, audit_events, originales, solicitudes/releases terminales ni fotos. Seeds agregan faltantes por code/key, nunca pisan parametros/catalogos operativos, personas o credenciales.
- Si falla: mantener mantenimiento y evidencia, revisar revision/estado parcial, preferir fix-forward. Downgrade solo reversible y probado con autorizacion; restore a destino aislado y switchover aprobado, nunca sobrescribir data/. Tras nuevas escrituras no prometer rollback sin perdida; reconciliar antes.
- No existe aun actualizador de releases, backend o Alembic ejecutable. F1 debe implementarlos/probarlos y F7 homologarlos; no inventar migraciones ejecutadas o respaldos restaurados por haber pasado init-dev.

## Convenciones obligatorias

- Mantener IDs RF-*, RN-*, D* y F*; no renumerar para acomodar cambios. Actualizar contratos y criterios primero, implementar lo minimo de la fase autorizada y dejar evidencia verificable.
- Nombres de API/BD snake_case, UUID, fechas civiles para compromisos y timestamps UTC. Conservar original_due_date inmutable, due_date vigente y completed_at del servidor. Etapa, avance y puntualidad son conceptos separados; formulas canonicas en RN-02/RN-03/RN-06.
- Roles exactos admin, gerente, lider, colaborador; autorizacion por rol Y alcance en servidor, incluidas metricas, evidencia e historia. Mutacion e historial en una transaccion con control de version. No ocultar fallos de concurrencia.
- Tema OCOTE: tokens canonicos --ocote-* de la SDD, no volver a escoger paleta. Primary #B85A1E, Bosque #2E5A44, acento/warning #D98A1C; success #2E7D5B, danger #B83227; colores/on-colors y demas tokens en SDD. Material 3 exige paletas tonales completas, no un hex ni APIs de otras versiones. Kanban/Timeline/ECharts comparten semantica, contraste AA y alternativas accesibles; tema aun no aplicado al scaffold.
- Reutilizar patrones locales y evitar dependencias, carpetas o abstracciones innecesarias. Sin cambios productivos solo para satisfacer un ejemplo documental. No mover Angular a otra carpeta.
- Respetar cambios ajenos; no hacer reset/checkout destructivo, commits, cambios de rama, actualizaciones de dependencias ni operaciones destructivas de BD sin solicitud explicita. No editar binarios ni archivos internos de data/.
- Tras un cambio, ejecutar primero la validacion enfocada. Para DB, usar mocks en tests y PostgreSQL real solo para comprobaciones autorizadas; no afirmar que SQLite valida constraints PostgreSQL. Mantener el estado actual al dia al finalizar.

## Comandos disponibles

```bash
bash -n scripts/init-dev.sh
bash -n scripts/db-start.sh
node --test scripts/db-start.test.cjs
git diff --check
```

La suite del helper usa temporales/mocks, no data real; si solo cambian documentos, validar enlaces/anclas, fences/JSON, IDs/modelo y coherencia de permisos/parametros/releases, sin reconectar BD ni rerun de mocks como prueba de negocio. Comandos Angular existentes: npm ci si necesario, npm start/build/test (Karma requiere navegador). No declarar build/E2E por pruebas del helper. Backend/Alembic/ocote-admin aun no tienen comandos ejecutables.

Al cerrar una tarea indicar archivos cambiados, verificaciones y limites, estado de BD si se arranco y siguiente paso de la fase correspondiente. No dejar conocimiento esencial unicamente en el chat.