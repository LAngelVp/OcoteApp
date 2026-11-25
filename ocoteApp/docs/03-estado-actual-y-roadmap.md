# OCOTE: estado actual y roadmap

Version documental: 2.0 con acta de cierre F1 local. Fecha de corte: 2026-11-24 local / 2026-11-25 UTC. No implementa F2, negocio ni instalador cliente.

Estado vigente: **F1 cerrado para desarrollo local con datos sinteticos y excepciones expresas hasta 2026-12-24**, segun [acta de seccion 7](#7-cierre-formal-f1-local). F2 no autorizado ni iniciado. La seccion 6 conserva la primera ejecucion y su fallo/reintento; secciones 1 y 5 son fotografias historicas F0, no inventario actual. Reglas y DoD se preservan; los limites y gates de entornos no homologados se explicitan, no se proclaman cumplidos.

Referencias normativas: [SDD](01-spec-driven-development.md), [arquitectura y datos](02-arquitectura.md), [entorno local](04-entorno-y-portabilidad.md), [entrega/actualizaciones](05-paquetizacion-instalacion-y-actualizaciones.md). RF-01..12 y RN-01..06 se conservan; se agregan RF-13..15 y RN-07 sin renumerar D01-D08/F0-F7.

## 1. Donde nos encontramos

### Evidencia observada en el workspace

| Area                    | Evidencia                                                                                                                                            | Interpretacion                                                                                                |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Proyecto                | [package.json](../package.json), nombre ocote-app, version 0.0.0                                                                                     | Angular creado en raiz, no monorepo con herramientas adicionales                                              |
| Framework               | Dependencias Angular ^18.2.x; CLI/build ^18.2.21; TypeScript ~5.5.2                                                                                  | Linea 18.2 declarada, no certificacion de versiones resueltas ni build exitoso                                |
| Render y estilos        | [angular.json](../angular.json): builder application, browser src/main.ts, SCSS, sin opciones server/SSR                                             | SPA sin SSR configurada                                                                                       |
| Componente              | [app.component.ts](../src/app/app.component.ts) y [app.component.html](../src/app/app.component.html)                                                | Componente standalone con titulo ocoteApp y plantilla inicial de Angular; sin funcionalidad OCOTE             |
| Tema                    | [styles.scss](../src/styles.scss)                                                                                                                    | Material 3 define-theme con azure/blue y tipografia Roboto, no tema OCOTE aplicado                            |
| Animaciones             | [app.config.ts](../src/app/app.config.ts)                                                                                                            | provideAnimationsAsync ya registrado                                                                          |
| Bibliotecas             | Material/CDK/animations ^18.2.14, ngx-echarts ^18.0.0, echarts ^6.1.0, vis-timeline ^8.5.6 declarados                                                | Instalacion/declaracion no prueba integracion ni compatibilidad efectiva                                      |
| Instalacion local       | Existen node_modules/ y [package-lock.json](../package-lock.json)                                                                                    | No se modifican; reproducibilidad y peers se verificaran en F1                                                |
| Backend                 | No hay backend/                                                                                                                                      | Python 3.12, FastAPI, SQLAlchemy 2.0 y Alembic siguen planeados; no hay migraciones ni tablas de negocio      |
| PostgreSQL local        | Evidencia previa de database/postgres/bin, database/data/PG_VERSION=18 y database/logs                                                               | PostgreSQL 18.4 Windows activo en comprobacion anterior; proceso no consultado en este cierre                 |
| Conexion                | 127.0.0.1:5432; listen_addresses=127.0.0.1; reglas host locales SCRAM-SHA-256                                                                        | Base exacta ocoteAppDatabase creada vacia; base anterior ocote conservada; credencial exclusiva local en guia |
| Retoma segura           | [init-dev.sh](../scripts/init-dev.sh), [db-start.sh](../scripts/db-start.sh) y [pruebas](../scripts/db-start.test.cjs)                               | Suite de 16 escenarios; ejecucion repetida y --check real desde otra carpeta sin alterar bases previas        |
| Horizontes              | RN-01/RN-02/RN-06 y esquema de planes/objetivos                                                                                                      | start_date/due_date/horizon_type configurables; ya especificado, no implementado                              |
| Actualizaciones cliente | Protocolo en arquitectura y guia operativa                                                                                                           | Alembic, backup automatico y contingencia especificados; automatizacion y restore aun pendientes F1/F7        |
| Modelo ampliado         | 19 diccionarios de tablas en arquitectura; RN-07 y RF-13..15 en SDD                                                                                  | Configuracion, prioridades/horizontes, solicitudes de fecha y releases especificados, no creados              |
| Entrega local/nube      | Guia 05: paquete, dos instalaciones, exports internos y actualizaciones                                                                              | Ningun instalador, proveedor o restauracion certificado por redactar la guia                                  |
| Contexto portable       | [AGENTS.md](../AGENTS.md), [.github/copilot-instructions.md](../.github/copilot-instructions.md), [README.md](../README.md) y cinco documentos docs/ | No requiere historial de chat; aprobaciones siguen siendo puertas                                             |

No hay login/tablas/endpoints/tableros OCOTE implementados. En la entrega anterior de helpers se creo solo ocoteAppDatabase vacia, se preservaron OIDs/catalogo legacy, pasaron 16 mocks y retoma real; backend/.venv y backend/alembic ausentes, node_modules presente. Es evidencia previa, no pruebas reejecutadas ahora ni garantia del estado actual del proceso.

Esta ampliacion solo edita los ocho documentos/instrucciones del diagnostico siguiente; no cambia Angular, scripts, dependencias/lock, .env ni BD. No arranca/consulta servidor ni ejecuta initdb, reset, backup/restore, seeds o migraciones. Verificacion documental: inventario de 19 tablas/FK, ejemplos JSON y referencias locales, preservacion de IDs/tokens y contratos de permisos. Sus limites: no valida SQL ejecutado, diagramas renderizados, seguridad real, builds/E2E, instalacion o recuperacion.

Resultado del chequeo estructural 2.0: 8 archivos, 70 referencias locales con anclas verificadas, 9 bloques JSON parseados, 29 bloques cercados balanceados y 19 entidades ER coincidentes con diccionarios/FK. IDs RF-01..15/RN-01..07/D01..08/F0..7 y tokens principales conservados; diagnostico del editor sin errores y git diff --check limpio. Son comprobaciones estructurales, no prueba semantica exhaustiva ni ejecucion del protocolo cliente.

### Diagnostico de completitud por archivo

Completitud significa especificacion lista para revision, no aprobacion formal ni implementacion.

| Archivo                                                      | Cobertura consolidada                                                                  | Pendiente fuera de este cierre                                     |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [SDD](01-spec-driven-development.md)                         | Matriz rol/menu/ruta/accion/datos, RN-01..07, RF-01..15, API y tokens                  | Ratificar D01..D05/D08 y ejecutar aceptacion por fase              |
| [Arquitectura](02-arquitectura.md)                           | Capas/seguridad, ER y 19 diccionarios, settings/catalogos/locks y topologia local/nube | SQLAlchemy/Alembic, pruebas PostgreSQL y homologacion D06/D07      |
| Este roadmap                                                 | Evidencia previa separada, trazabilidad F0..F7 y puertas/DoD ampliadas                 | Autorizacion y evidencia real de cada fase                         |
| [Entorno](04-entorno-y-portabilidad.md)                      | Retoma local, credencial publica limitada y enlace al protocolo central                | Restore ensayado; no extrapolar helper a cliente/nube              |
| [Entrega](05-paquetizacion-instalacion-y-actualizaciones.md) | Paquete/firma, instalaciones A/B, bootstrap, integraciones/exports y contingencia      | Herramientas, proveedor/SO, backup automatico y pruebas operativas |
| [AGENTS.md](../AGENTS.md)                                    | Lectura, autoridad, limites/permisos/parametros y continuidad sin chat                 | Cumplimiento en cada implementacion; no otorga autorizacion        |
| [Adaptador Copilot](../.github/copilot-instructions.md)      | Entrada del editor y guardrails criticos enlazados a fuente comun                      | No sustituye AGENTS/SDD ni certifica ejecucion                     |
| [README](../README.md)                                       | Entrada, comandos existentes, estado y siguiente paso                                  | No anuncia funcionalidades/instalador como disponibles             |

### Decisiones consolidadas

- Producto: planes/objetivos con horizontes annual/semiannual/quarterly/monthly/custom y rango explicito, incluida meta anual y cruces de anio; ejecucion/evaluacion con trazabilidad que no se borra al reprogramar.
- Identidad: OCOTE, constancia y claridad. Paleta completa y roles visuales canonicos en seccion 5 de la SDD; definida documentalmente, pendiente de tema custom Material y adopcion por graficas/Kanban/Timeline.
- Stack: Angular 18.2 SPA SCSS en raiz; Python 3.12/FastAPI/SQLAlchemy 2.0 futuros; desarrollo PG18.4 portable observado. Cliente local/contenedor o PG18 gestionado especificados, homologacion pendiente D06/D07.
- Seguridad: Argon2id, access/refresh JWT, rotacion/revocacion, token_version, roles admin/gerente/lider/colaborador y alcance validado en servidor.
- Dominio: fecha original inmutable, fecha vigente auditable, cierre UTC del servidor; etapas configurables separadas de puntualidad y avance.
- Datos: annual_plans conserva nombre tecnico, sin unicidad por anio; objectives tiene intervalo/horizonte propio contenido en padre. Fotos finales preservan contexto temporal; metricas usan fecha original y rango inclusivo, sin cambio oculto de denominador.
- Parametros: system_settings tipado y prioridades/cinco horizontes en BD; secretos en entorno/gestor; zona elegida al instalar y protegida tras uso. Formularios no editan roles/formulas como reglas arbitrarias.
- Permisos: C solo tareas asignadas/contexto minimo, sin agregados, exports ni evaluaciones. L solo departamento, solicitudes de fecha auditables y finales propias; aprobacion de fecha por persona A/G distinta del solicitante. Gerente no mueve tareas.
- Integraciones: REST interna/OpenAPI y exports JSON/CSV acotados; ERP/SSO/mensajeria/webhooks/IA/importacion masiva fuera de MVP, con puertas propias. No tokens humanos reutilizados como integracion.
- Actualizaciones: cada release requiere maintenance, respaldo automatico verificado, Alembic forward, seeds conservadores, integridad/revision/smoke y contingencia aprobada; no DDL manual ni migraciones al arrancar. Protocolo detallado en guia, aun no automatizado.
- Metodo: SDD antes de codigo; cada fase implementa criterios verificables y no cambia reglas silenciosamente.

### Estado de cierre y aprobacion

La base documental queda redactada y trazable, no aprobada en nombre de negocio/TI. F0 se mantiene cerrado documentalmente y ampliado con contexto operativo. Se autorizo esta habilitacion local, no implementar negocio ni declarar F1 completo. El backend de F1 requiere autorizacion explicita y puertas D01, D05, D06 y D07 que correspondan; D06 ya tiene modalidad de desarrollo confirmada, pero backup/restore y produccion siguen pendientes. Una decision abierta no se sustituye por una suposicion escondida en codigo.

## 2. Forma de ejecucion

Fases estrictamente secuenciales F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7. La dependencia significa que la DoD anterior esta satisfecha; referencias a requisitos de fases futuras no son prerrequisitos adicionales ni crean ciclos.

DoD comun de F1-F7: requisitos y contratos actualizados antes del codigo, pruebas enfocadas aprobadas, cambios revisados sin secretos, errores/permisos negativos cubiertos, instrucciones reproducibles y evidencia adjunta a la entrega. Fases con UI requieren build de produccion, teclado, contraste y revision responsive. Fases con persistencia requieren migraciones verificadas en PostgreSQL real. Ninguna fase se declara terminada por crear carpetas o compilar solamente.

### F0. Fundacion documental

Dependencia: ninguna. Alcance: documentacion fundacional; ampliacion con guia operativa e instrucciones agenticas sin modulos de negocio.

Entregables: cinco documentos normativos, README, AGENTS y adaptador; SDD/ER/contratos, permisos/parametros, evidencia/roadmap, D01-D08, entrega A/B e integraciones y trazabilidad. Sin codigo productivo ni nuevas utilidades en este cierre.

DoD: todos los modulos del MVP tienen criterios verificables, lenguaje y formulas unicos, entidades/relaciones documentadas y enlaces locales validos; ejemplos JSON parseables y paleta consistente. Validacion estructural no certifica runtime ni aprobacion de negocio. Estado al cierre de esta sesion: documentacion cerrada para revision; aplicacion no implementada.

### F1. Base tecnica, compatibilidad y portabilidad

Dependencia: F0. Puertas: autorizacion para base tecnica; D01 zona IANA; D05 privacidad/retencion y almacenamiento; D06 objetivos RPO/RTO/responsable (modalidad portable de desarrollo ya confirmada); D07 soporte Angular y compatibilidad de dependencias. Elegir gestor y lock Python, hardware/SO destino y propietario de operacion. Si Angular 18 no satisface politica de soporte, registrar excepcion temporal con fecha/responsable o aprobar cambio de stack y actualizar la SDD antes de implementar.

Entregables: backend/ tecnico, Python 3.12/lock, conexion exacta, health/revision, Alembic y roles runtime/migrador separados sin secretos. Primera revision tecnica incluye release_history sin dependencias de usuarios de negocio; tablas de identidad/configuracion F2, negocio F3/F5/F6, no crear todo el modelo por anticipado. Bitacora externa cubre migracion inicial fallida. Preparar herramienta/protocolo de release, firma/manifest y backup bloqueante. Prototipo de compatibilidad visual sin pantallas de negocio ni upgrades automaticos. Diseñar/probar conexion directa y pooling/TLS gestionado con instancia autorizada; si falta proveedor, dejar evidencia de ese gate abierta.

DoD: base reproducible, ready bloquea esquema incompatible, migracion tecnica desde cero/segundo upgrade no-op; backup bloqueante y restore aislado medidos, fallo mantiene mantenimiento/invariantes. release_history/reintentos y bitacora externa recuperables. Build/prototipo sin peers incompatibles. Contratos y evidencia de TLS/CA, roles/btree_gist, limite de conexiones y backup local/gestionado segun entorno aprobado; F7 homologa instalaciones completas, no se proclama soporte nube si no se probo.

Riesgo principal: version instalada no compatible o perdida del volumen. Mitigacion: lock y prueba minima ejecutable; restore real y datos fuera de Git.

### F2. Identidad, permisos y administracion

Dependencia: F1. Puertas: D02, D04 catalogos/flujo inicial y provision segura del primer admin; revisar refresh/CSRF y credenciales, ratificar nombre/zona RN-07.

Entregables: departments/users/audit_events/refresh_sessions, system_settings/priorities/horizon_types y etapas/aristas, migraciones/seeds conservadores; bootstrap admin de uso unico sin default, JWT/Argon2id/CSRF y politicas. RF-01/RF-02/RF-13 API; no tableros de negocio. Zona sin override env; protegerla desde F3 con primera tarea/evaluacion.

DoD: ciclo sesion/CSRF/reuso/revocacion, carreras ultimo admin y 401/403/404; politicas positivas/negativas por modulo/proyeccion, no solo boton oculto. Parametros rechazan claves/tipos/limites invalidos y conflictos; procesos observan mismo valor; cinco horizontes/normal/custom protegidos. Seeds repetidos no pisan datos y bootstrap repetido no duplica/resetea admin. Workflow inicial/terminal y grafo validos.

Riesgo principal: permisos solo visuales o cookies vulnerables. Mitigacion: autorizacion central, pruebas negativas en servidor y HTTPS/origen/CSRF.

### F3. Nucleo de planes, ejecucion, fechas y auditoria

Dependencia: F2. Puertas: ratificar ejemplos temporales D01, formulas D03, flujo D04 y corte/cohorte D08 con gerencia. Elegir correccion administrativa fuera de MVP si no se acepta cierre irreversible.

Entregables: annual_plans/objectives con FK horizonte/rangos, tasks con prioridad, subtasks/task_history/due_date_requests; period-changes y solicitudes/decisiones atomicas auditadas; RF-03/04/05/11/14 y RN-01..07. Probar duplicada pending, versiones obsoletas, autoaprobacion rechazada, contracciones y zona bloqueada tras uso. Foto final F6/evidencia F5: no habilitar reglas dependientes antes.

DoD: formulas con fixtures manuales; contencion plan/objetivo/tarea y cambios de periodo concurrentes probados, incluidos un dia y multiples anios. Originales/append-only protegidos; errores revierten todo; concurrencia cierre/subtarea/reprogramacion consistente. Cambios conservan historial/versiones; migraciones ensayadas sobre copia con datos, con backfill antes de endurecer constraints.

Riesgo principal: reprogramacion que maquille resultados. Mitigacion: original inmutable, dos puntualidades, cohorte por original y auditoria transaccional.

### F4. Sistema visual y flujos de gestion Angular

Dependencia: F3. Puerta: validar muestra visual accesible con negocio, licencia/autoalojamiento tipografico y mapeo publico Material 18.2 de roles secondary/tertiary.

Entregables: tokens/paletas M3, shell y sesion/refresh en memoria, formularios de administracion/parametros/catalogos, planes/objetivos/tareas/subtareas y solicitudes/decisiones de fecha. Menus/rutas/proyecciones exactamente SDD; UI de releases solo lectura sanitizada. Analitica/evaluaciones permanecen ocultas hasta F6. Sin nuevo tema/paleta elegida de cero.

DoD: color/typography/density del tema se compilan con APIs publicas, paleta de marca trazada a roles M3, WCAG 2.2 AA en combinaciones usadas, estados vacio/carga/error/conflicto y navegacion por teclado. E2E por rol de alta y ejecucion basica; pantallas a 360/768/1440 px y zoom 200% sin superposicion. Build respeta budgets o ajuste justificado aprobado.

Riesgo principal: asumir que un hex es una paleta Material o persistir tokens en navegador. Mitigacion: prototipo previo, matriz de roles y pruebas de sesion tras recarga y entre pestanas.

### F5. Kanban, Timeline y evidencias

Dependencia: F4. Puerta: D05 antimalware y retencion aprobados. Definir integracion de escaneo o aceptar formalmente controles compensatorios y riesgo antes de habilitar cargas; no declarar archivos seguros por verificar MIME solamente.

Entregables: carga/descarga privada de evidencia, RF-06/RF-07/RF-08; carriles configurables con paginacion por etapa, drag/drop y menu accesible, Timeline con baseline/actual/cierre, filtro compartido y comandos auditados. Reprogramar en formulario, no por drag de barras.

DoD: archivo ajeno/invalido/excesivo rechazado, lectura de evidencia requiere alcance; etapa que exige evidencia no se alcanza sin ella; conflicto 409 restaura tarjeta. Teclado equivalente al raton, filtros y fechas coinciden entre tabla/Kanban/Timeline; upload/BD manejan fallos y no dejan referencias rotas. Render comprobado en movil y escritorio.

Riesgo principal: diferencias de estado entre vistas y archivos maliciosos. Mitigacion: misma API y calculos, rollback visual, almacenamiento privado y puerta antimalware.

### F6. Analitica y evaluacion gerencial

Dependencia: F5. Puerta: ratificar D03/D08 con ejemplos de negocio y validar interpretacion de denominadores; definir calendario de evaluaciones y gerentes responsables.

Entregables: RF-09/RF-10/RF-15, analytics/ECharts con tema, tablas equivalentes; evaluations/evaluation_items con corte y final inmutable; exports JSON/CSV acotados/auditados segun guia 05, solo A/G/L autorizado. Sin tabla/job/exportacion publica ni integraciones externas.

DoD: fixtures/denominadores correctos, sin duplicacion por joins, no-data null; fotos y exclusiones bajo concurrencia, catalogos renombrados no alteran foto. C recibe 403 en analytics/evaluations/exports por URL/API, L nunca global ni drafts ajenos. Exports prueban cero/limite+1, inyeccion CSV, cancelacion/fallo/auditoria y corte consistente; etiquetas/tabla accesibles.

Riesgo principal: evaluar personas con datos incompletos o historicos moviles. Mitigacion: evaluacion departamental, corte/denominador visibles, baseline y foto inmutable sin score oculto.

### F7. Endurecimiento, piloto y entrega local/gestionada

Dependencia: F6. Puertas: responsable de operacion y seguridad, excepciones cerradas o formalmente aceptadas, soporte D07 resuelto, volumen y objetivos de rendimiento aprobados para hardware real.

Entregables: paquete firmado con SBOM/licencias/dependencias por plataforma, instalaciones A/B de guia 05 y manual de soporte, proxy TLS, respaldo/restore BD+evidencia y monitoreo. Homologar herramienta/runbook por cada revision origen, fallos/reintentos, seeds conservadores, history/fotos y contingencia/switchover; medir red/pool/failover/CA y salida del proveedor. Sin rollback destructivo tras nuevas escrituras ni anuncio de plataforma no ensayada.

DoD: recorrido de cada RF con evidencia, revision de vulnerabilidades de dependencias y aplicacion, pentests negativos de roles/uploads/tokens, restauracion dentro de RTO y perdida dentro de RPO acordados, medicion de p95 y carga aprobada, accesibilidad manual/automatizada, aprobacion de gerencia/TI y responsables capacitados. Ninguna excepcion critica de seguridad sin bloqueo de liberacion.

Riesgo principal: una demo funcional se confunda con operacion lista. Mitigacion: piloto, restauracion en host alterno, runbooks y responsables verificables.

## 3. Trazabilidad de implementacion y pruebas

| Requisito | Reglas principales     | Fase que lo entrega               | Evidencia minima                                                            |
| --------- | ---------------------- | --------------------------------- | --------------------------------------------------------------------------- |
| RF-01     | RN-01, RN-04, RN-05    | F2 API, F4 UI                     | Roles, unicidad, desactivacion y workflow valido                            |
| RF-02     | Seguridad arquitectura | F2, integracion F4                | Rotacion/reuso, CSRF, revocacion y acceso cruzado                           |
| RF-03     | RN-01, RN-02           | F3 API, F4 UI                     | Horizontes/rangos, cruce de anio, contencion y cambios de periodo auditados |
| RF-04     | RN-02, RN-03           | F3 API, F4 UI                     | 0/1/N subtareas y carrera cierre/alta                                       |
| RF-05     | RN-02, RN-05           | F3                                | Original/vigente, medianoche y auditoria                                    |
| RF-06     | RN-04, RN-05           | F5                                | Motivo/evidencia, alcance y fallos de archivo                               |
| RF-07     | RN-03, RN-04           | F5                                | Carriles, menu/drag, filtros y conflicto                                    |
| RF-08     | RN-02                  | F5                                | Barras, baseline/cierre y permisos                                          |
| RF-09     | RN-03, RN-06           | F6                                | Fixture de denominadores, sin datos y alcance                               |
| RF-10     | RN-06                  | F6                                | Foto sellada, cohorte y solapamientos                                       |
| RF-11     | RN-05                  | F3 y extensiones F5/F6            | Atomicidad, before/after y acceso a historia                                |
| RF-12     | Seccion 5 SDD          | F4-F6; gate F7                    | Teclado, contraste, lector y responsive                                     |
| RF-13     | RN-07, RN-05           | F2 API, F3 proteccion zona, F4 UI | Tipo/limites, dos procesos, FK/inactivos, seeds no destructivos             |
| RF-14     | RN-02, RN-05           | F3 API, F4 UI                     | Pending unica, decision distinta, carrera/rollback y original intacta       |
| RF-15     | RN-05, RN-06, guia 05  | F6; gate F7                       | Alcance, CSV seguro, limite/corte y fallos auditados                        |

## 4. Riesgos y decisiones pendientes de confirmacion

| Riesgo / decision                                                  | Responsable propuesto       | Puerta y mitigacion                                                                                                                   |
| ------------------------------------------------------------------ | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| D01 Zona y horizontes configurables, sin ciclo anual rigido        | Gerencia + TI               | Flexibilidad adoptada; F1 confirma zona IANA; F3 valida ejemplos, contencion y cruces de anio                                         |
| D02 Un departamento/rol por usuario no cubra organigrama           | Gerencia + seguridad        | F2; aprobar matriz o especificar memberships antes de migrar                                                                          |
| D03 Pesos iguales sin criterio de calidad                          | Gerencia                    | F3; aceptar metricas separadas, no prometer score de productividad                                                                    |
| D04 Etapas/cierre y catalogos iniciales                            | Administrador de proceso    | F2 aprueba etapas/prioridades/horizontes y RF-13; F3 ratifica cierre/solicitudes, sin reglas arbitrarias                              |
| D05 Datos personales, evidencia y retencion                        | Seguridad + legal + TI      | F1 politica; F5 escaneo/compensaciones; minimizar datos y proteger descargas                                                          |
| D06 Desarrollo portable confirmado; A/B productivos pendientes     | TI/operaciones              | F1 SO/proveedor/region, roles/extension/TLS/red/pool, RPO/RTO y restore; F7 paquete/instalacion/upgrade/contingencia homologados      |
| D07 Soporte Angular 18 y compatibilidad ECharts 6 / ngx-echarts 18 | Lider tecnico + seguridad   | F1 y F7; Angular 18 es version historica al corte; verificar soporte oficial, no asumir parches vigentes; upgrade solo con aprobacion |
| D08 Evaluacion al snapshot_at y no reconstruccion al cierre        | Gerencia                    | F3; aprobar periodo, cohorte y fecha real de corte; validar de nuevo F6                                                               |
| Capacidad sin medicion                                             | Lider tecnico + operaciones | F1 dimensionar; F7 acordar usuarios concurrentes, tareas/anio, evidencia y p95 antes de prueba de carga                               |
| Respaldo incompleto o auditoria manipulable por operador           | Operaciones + seguridad     | F7; backup conjunto cifrado, restore probado y acceso privilegiado auditado                                                           |

No hay estimaciones de tiempo ni SLA de rendimiento inventados. La duracion por fase se acuerda despues de aprobar alcance y disponibilidad del equipo. RPO/RTO son ahora objetivos de diseno aprobados segun seccion 7, no SLA de produccion ni tiempos de recuperacion de un host demostrados.

## 5. Resumen ejecutivo y siguiente paso exacto

Fundacion documental 2.0 completa para revision: cinco documentos y tres entradas/instrucciones, 19 tablas objetivo (14 previas + system_settings, priorities, horizon_types, due_date_requests y release_history). Inventario/diccionarios completos en arquitectura; alembic_version tecnica no cuenta como tabla de dominio. F0 documental cerrado, D01-D08 no firmadas por este acto. F1-F7 siguen pendientes; no hay negocio, tema o instalador implementado.

Siguiente paso al cierre documental anterior (historico; sustituido por la evidencia de seccion 6): revisar/registrar decisiones y obtener autorizacion explicita F1, no escribir codigo aun. Primer paso tecnico condicionado a esa autorizacion y D01/D05/D06/D07: `bash scripts/init-dev.sh --check`; si detenido/base ausente y arranque local autorizado, init-dev y nuevo check, nunca ignorar error. Preparar Python 3.12/lock y backend/ tecnico FastAPI/SQLAlchemy 2.0/psycopg 3, roles runtime/migrador, conexion exacta, health/revision y Alembic tecnico con release_history; probar backup-upgrade-no-op-restore aislado. No crear las 19 tablas de golpe, componentes funcionales Angular ni routers/services de negocio de fases posteriores.

## 6. Ejecucion local de la base tecnica F1

### Alcance y estado del primer incremento (historico)

Autorizacion expresa del usuario para esta sesion: construir solo backend/ tecnico, roles separados, salud/revision y ensayo controlado de respaldo, upgrade, no-op y restauracion aislada. No autoriza F2 ni negocio. F1 tecnico local entregado; F1 integral permanece abierto por las puertas y comprobaciones ajenas a este alcance. SDD, reglas RN/RF, modelo objetivo y DoD anteriores permanecen intactos.

- [Backend y runbook](../backend/README.md): configuracion de entorno validada, SQLAlchemy sincrono/psycopg 3, unidad de trabajo, errores problem+json sanitizados con request_id, salud y Alembic. Dependencias reproducibles en pyproject.toml/requirements.lock con hashes; backend/.venv creado.
- Versiones realmente instaladas: Python 3.12.0 Windows x64, FastAPI 0.165.0, SQLAlchemy 2.0.58, psycopg 3.3.9, Alembic 1.20.1, Pydantic 2.14.4 y Uvicorn 0.54.0. No se actualizo Python, PostgreSQL, Node ni Angular.
- Solo public.alembic_version y public.release_history existen en la base objetivo; revision unica 20261124_0001. No users/system_settings/audit_events ni tablas de negocio. No seeds, bootstrap de usuarios, create_all, stamp, downgrade ni migracion automatica al arrancar.
- ocote_runtime: CONNECT, USAGE public y SELECT en las dos tablas tecnicas; sin DDL, TEMP, DML sobre bitacora ni pertenencia a ocote_migrador. ocote_migrador: CONNECT y USAGE/CREATE public, propietario de objetos creados por Alembic. Ambos sin SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS; limite de conexiones local 8/3. No permisos DML genericos a futuras tablas.
- Credenciales nuevas aleatorias, distintas por rol; configuracion local backend/.env y artefactos privados ignorados por Git, con ACL de usuario. La API exige el DSN runtime y Alembic exige el DSN migrador. El superusuario solo se utilizo en aprovisionamiento y operaciones locales autorizadas, nunca como cuenta API.
- PostgreSQL permanece activo en 127.0.0.1:5432, cluster original mayor 18. OIDs finales: ocote=16384 y ocoteAppDatabase=16389, conservados durante el ensayo; catalogo legacy comparado sin cambios, sin leer sus registros de negocio. Cero bases temporales restantes. btree_gist 1.8 disponible, no instalado ni necesario para esta revision.

### Comandos y resultados reales

Comandos desde raiz en Git Bash; credencial administrativa solo temporal en entorno, nunca en los archivos nuevos. Los comandos de provision/ensayo no deben repetirse a ciegas sobre esta base ya inicializada.

| Comprobacion          | Ejecucion / resultado                                                                                                                                                                                                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Cluster antes/despues | `bash scripts/init-dev.sh --check` -> exit 0, PostgreSQL 18.4, base exacta; servidor ya activo, no se arranco ni detuvo                                                                                                                                                                    |
| Entorno Python        | `py -3.12 -m venv backend/.venv`; instalacion pip-tools 7.5.2; `python -m piptools compile --extra dev --generate-hashes --strip-extras --output-file backend/requirements.lock backend/pyproject.toml`; `python -m pip install --require-hashes -r backend/requirements.lock` -> exitosos |
| Roles                 | `backend/.venv/Scripts/python backend/tools/f1_local.py provision --execute` -> conexiones independientes verificadas y atributos elevados todos false                                                                                                                                     |
| Salud sin esquema     | GET /api/v1/health/ready con token de monitor -> 503 antes de la revision                                                                                                                                                                                                                  |
| Ensayo inicial        | `backend/.venv/Scripts/python backend/tools/f1_local.py rehearse --execute` -> backup previo/restore, upgrade y no-op exitosos; cierre bloqueado en comparacion de CHECK posterior, sin revertir esquema ni ocultar fallo                                                                  |
| Respaldo              | pg_dump -w -h 127.0.0.1 -p 5432 -U postgres -d ocoteAppDatabase --format=custom --file=destino-unico -> exit 0; cabecera PGDMP, tamano y SHA-256; pg_restore --list exit 0                                                                                                                 |
| Alembic               | Desde backend/: `python -m alembic upgrade head` inicial y segunda invocacion -> exit 0; revision 20261124_0001 y snapshot identico en segunda invocacion                                                                                                                                  |
| Reintento controlado  | `backend/.venv/Scripts/python backend/tools/f1_local.py retry-verification --execute` -> exit 0; nuevo backup/restore bloqueante, dos upgrades no-op, backup/restore posterior y limpieza                                                                                                  |
| Restauracion          | pg_restore -w -h 127.0.0.1 -p 5432 -U ocote_migrador -d base-temporal-unica --exit-on-error --no-owner --no-acl archivo.dump -> exit 0; verificacion de filas/revision, columnas, indices, restricciones/FK, triggers y funcion; fixtures invalidas revertidas                             |
| Suite final real      | `OCOTE_RUN_PG_TESTS=1 backend/.venv/Scripts/python -m pytest -q backend/tests` -> 31 passed; incluye 7 casos PostgreSQL y negativas de runtime; una advertencia de deprecacion TestClient/httpx, sin error                                                                                 |
| Herramientas          | `python -m ruff check backend` y `python -m pip check` -> sin errores/incompatibilidades declaradas; editor sin errores                                                                                                                                                                    |
| Revision final        | `python -m alembic -c backend/alembic.ini current` y `heads` -> 20261124_0001 (head), una sola head                                                                                                                                                                                        |
| HTTP real             | Uvicorn temporal en 127.0.0.1:8000: live 200, ready sin token 403, ready con token 200, request_id en cada respuesta; proceso API detenido despues del smoke                                                                                                                               |

Las invocaciones Python de instalacion/Alembic de la tabla utilizaron el ejecutable de backend/.venv; el runbook contiene rutas completas. No se ejecutaron los mocks de helpers ni build/tests Angular, porque esos archivos no se modificaron.

### Intentos, hashes y recuperacion

1. Intento 4c1f7c32-ccd4-4d8a-a9e2-d17ec71a6b14, request_id 46a3311e-fd34-4e1e-b074-be30201ef754. Inicio UTC 2026-11-25T02:05:41.430763Z. Respaldo virgen previo de 1992 bytes, SHA-256 670b91bccd227551bfdd2acc01c7bc927ee87c93d36aa8cd1865589cd705e680; restore verificado antes del DDL (0.395 s). Upgrade inicial y segundo no-op confirmados. Restore posterior completo, pero la comparacion textual de tres CHECK mostro casts ARRAY equivalentes descompilados de forma distinta por PG18. Mantencion preservada y destino temporal eliminado; no hubo apertura ni reset.
2. Se corrigio solo el comparador de la herramienta, NO la revision aplicada. Se comparan propiedades estructuradas del catalogo, datos/revision, columnas, indices, triggers y cuerpo de funcion; se ejercitan 17 INSERT invalidos y transiciones protegidas, todos revertidos, tanto en origen como en destino. No es una demostracion formal de equivalencia de todo SQL ni prueba de modulos futuros. El intento original se reconcilio como failed/RESTORE_COMPARISON_FAILED, version=2, conservando identidad/timestamps.
3. Reintento 1ec4dc50-0871-467a-aafb-db58a6c2f9ef, retry_of_id original, request_id 720e4f8d-3c5c-4da1-a9e1-e8afac3845d1. Final UTC 2026-11-25T02:08:26.355736Z; duracion 7.050 s. Respaldo previo 11082 bytes, SHA-256 4e850ba19a2ff15b3d260168bb8a97f6a494fa8b49bff1886bce2c82a7397029, restore 0.506 s. Respaldo posterior 11285 bytes, SHA-256 2b1262e184591f2796c72ec89011e8d26e97e41e1f92b979b4aff7047b62b8e4, restore 0.559 s. Termino succeeded/F1_RETRY_VERIFIED, version=2; dos invocaciones adicionales de upgrade no-op.

Bitacoras durables append-only del ensayo, dumps y manifests con hashes en los dos directorios locales ignorados database/backups/f1-<id-del-intento>/. Se creo y elimino tambien un destino de diagnostico; cinco bases temporales en total, cero al cierre. Ningun pg_restore apunto a ocoteAppDatabase ni a ocote, y nunca se uso --clean. Se mantuvo lock advisory de sesion en conexion directa durante cada ensayo/reintento. Los mocks prueban que fallo de backup bloquea Alembic; el fallo real de comparacion mantuvo mantenimiento y bitacora externa, y el reintento quedo enlazado.

Los manifests describen la instantanea de cada ensayo local, no un paquete firmado ni el hash del checkout final. El dump posterior captura el intento nuevo running; su resultado terminal posterior se conserva en bitacora externa y debe reconciliarse al restaurar ese dump, antes de reabrir. No se invento un restore que ya incluyera ese evento futuro. No se restauro sobre el origen ni se cambio data/, PG_VERSION, configuracion del cluster o la base legacy.

### Puertas y siguiente paso exacto

| Puerta | Estado real y limite                                                                                                                                                                                                                                                                                                                      |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D01    | America/Mexico_City es supuesto explicitamente autorizado para configuracion/salud F1, pendiente de ratificacion gerencial; no se creo system_settings ni override runtime de datos operativos                                                                                                                                            |
| D05    | Privacidad, retencion, almacenamiento, cifrado/copia fuera del host y antimalware siguen pendientes; respaldos del ensayo local solo con ACL, no cifrados ni homologados para datos reales                                                                                                                                                |
| D06    | Roles, conexion exacta y recuperacion logica en otra base del mismo cluster Windows probados; no segundo host/cluster, proveedor, TLS/CA real, pool bajo carga, fallo de host, RPO/RTO o responsable formal aprobados. No homologacion de release/instalador/firma/PITR; Python 3.12.0 local no certifica politica de parches productivos |
| D07    | Angular 18 y compatibilidad Material/CDK/ECharts/vis-timeline no reevaluados ni actualizados, sin build/prototipo por exclusion expresa de esta sesion; no se aprueba soporte de seguridad                                                                                                                                                |

Preparacion hacia F2: ratificar D01/D05/D06/D07 y cerrar/aceptar formalmente las puertas F1 restantes; despues aprobar D02, D04 y custodia/bootstrap seguro del primer admin, y autorizar expresamente F2. Primer incremento F2: migracion propia para identidad/administracion (departments/users/audit_events/refresh_sessions, settings/catalogos/workflow), seeds conservadores, JWT/Argon2id/CSRF y politicas segun SDD; no planes, tareas o evaluaciones. Esta sesion no implementa ni autoriza ese incremento.

## 7. Cierre formal F1 local

Acta del 2026-11-24 local. Titular y responsable operativo: **LUIS ANGEL VALLEJO - DESARROLLADOR**. El usuario autorizo completar F1, ratifico decisiones y acepto expresamente los riesgos delimitados abajo. **F1 queda cerrado en Windows x64, PostgreSQL portable 18.4/loopback y datos sinteticos; no es una liberacion productiva ni homologacion nube/F7.** Secciones 1, 5 y 6 conservan evidencia historica; esta seccion gobierna el estado actual. No hubo cambios de dependencias, helpers previos, endpoints de negocio ni pantallas funcionales.

### Decisiones y excepciones expresas

| Decision | Estado y condicion de cierre |
| -------- | --------------------------- |
| D01 | America/Mexico_City ratificada como zona IANA oficial. ORGANIZATION_TIMEZONE sigue siendo solo bootstrap; no se creo system_settings ni override runtime. Ejemplos temporales de F3 pendientes. |
| D05 | Base de privacidad, minimizacion, almacenamiento privado, cuarentena/escaneo fail-closed, conservacion y backup aprobada en [guia 05, seccion 3.1](05-paquetizacion-instalacion-y-actualizaciones.md#31-base-aprobada-de-privacidad-y-recuperacion-d05d06). Es diseno normativo, no implementacion F5 ni visto bueno legal/productivo. |
| D06 | RPO <=24 h/RTO <=4 h como objetivos de diseno; backup diario/por release, minimo 30 dias, restore mensual/por release. Responsable identificado. Excepcion expresa **sin sustituto hasta 2026-12-24**: si no esta disponible, se suspenden migraciones/restores. Designar/capacitar suplente independiente antes de vencer o de datos reales/produccion. |
| D07 soporte | Angular 18 esta fuera de soporte, confirmado en [releases oficiales](https://angular.dev/reference/releases) y [compatibilidad historica](https://angular.dev/reference/versions). Excepcion expresa hasta **2026-12-24**, solo F1/F2 local y datos sinteticos, sin exposicion productiva ni red compartida. No afirmar soporte de seguridad vigente. |
| D07 alertas | Tras informar el resultado npm, el titular acepto **separadamente** 61 alertas (2 criticas, 19 altas, 33 moderadas, 7 bajas) bajo la misma fecha/alcance local. Criticas transitivas: piscina y tar en herramientas CLI/build; hay altas directas en Angular. Sin entradas/plantillas/archivos no confiables, sin exposicion de dev servers ni instalacion de paquetes/artefactos no revisados. No se demostro explotabilidad ni se descarto exposicion; un build exitoso no remedia las alertas. |

Luis Angel es responsable del riesgo, seguimiento y salida de ambas excepciones. Antes del 2026-12-24 debe autorizarse/ejecutarse una migracion a Angular soportado con dependencias compatibles, tratar las alertas y repetir audit, peers, prototipo, pruebas y build; designar/capacitar suplente. La version destino se evalua en esa tarea, no se actualiza automaticamente ahora. Al vencer se bloquea continuar F1/F2 bajo estas excepciones hasta resolverlas o una nueva decision expresa; nunca habilitan datos reales/produccion. Vulnerabilidades nuevas o cambio de exposicion requieren reevaluacion, no quedan aceptados por anticipado. D02/D03/D04/D08 no se aprobaron con este acto.

### Entregables y Definition of Done

| Entregable / criterio F1 | Resultado verificable y limite |
| ----------------------- | ------------------------------ |
| Backend reproducible | Confirmado: Python 3.12.0 Windows x64, pyproject/lock con hashes, FastAPI/SQLAlchemy/psycopg/Alembic; pip check limpio. Otros SO y nivel de parche productivo no homologados. |
| Conexion, roles y sesiones | Confirmado: base exacta, runtime/migrador separados sin elevacion; pool local 3+0 por proceso, timeouts, unidad transaccional y cierre/rollback. Sin prueba de capacidad productiva. |
| Health/revision/errores | Confirmado: live minimo, ready 403 sin token y 503 ante revision/BD/mantenimiento incompatibles; request_id y errores sanitizados. HTTP real de seccion 6 y pruebas actuales; no autenticacion RF-02. |
| Revision tecnica desde cero / no-op | Confirmado historicamente desde vacio en seccion 6; current=head=20261124_0001. Dos no-op adicionales del cierre compararon snapshot completo sin alterar esquema ni las dos filas terminales. No se reescribio ni reaplico desde cero la revision sobre origen. |
| Backup previo bloqueante | Confirmado: fallo de backup impide Alembic en pruebas; dump real con tamano/cabecera/hash/listado y restore validado antes de dos no-op. No copia off-host/cifrado/programacion implementados; prohibidos datos reales. |
| Restore medido e invariantes | Confirmado: destino temporal unico en el mismo cluster, revision/filas/catalogo/triggers y 17 inserts invalidos/transiciones protegidas con rollback; restore+verificacion 0.482 s. No demuestra recuperacion de host ni SLA/RPO de operacion. |
| Fallo/reintento/ledger | Confirmado: fallo inicial conservado failed, retry enlazado succeeded, version 2 ambos; journals externos durables. Cierre nuevo solo de verificacion, **sin mutar release_history**. Historia restaurada ya incluye ambos estados terminales. |
| Protocolo/herramienta/manifest | Preparacion confirmada: herramienta local explicita, lock advisory persistente, mantenimiento, hash/manifest y bitacora. Protocolo cliente/firma definidos en guia 05; manifest del ensayo NO firmado, sin paquete distribuible ni ocote-admin. Firma/SBOM, actualizador cliente e instalaciones integrales pendientes F7; no se certifican como implementados. |
| Build/prototipo/peers | Confirmado: build produccion dentro de budgets, 6 pruebas ChromeHeadless, npm ls --all sin problemas. Fixture solo de pruebas: Material/CDK, ECharts real por ngx-echarts y Timeline con CSS; no tema OCOTE, accesibilidad/responsive ni UI F4-F6 homologados. Soporte/alertas bajo excepciones D07, no aprobacion de seguridad. |
| D01/D05/D06 | Confirmadas decisiones de diseno y responsable; continuidad bajo excepcion. No hay configuracion de negocio ni evidencia privada real creada. No prometer retencion/escaneo/cifrado operativos por documentarlos. |
| TLS/CA, btree_gist y entorno gestionado | Gate **abierto para nube/produccion**, no aplicable a la unica modalidad local aprobada: no proveedor/instancia autorizada. Perfil managed valida contrato verify-full/CA, no conexion TLS real. btree_gist 1.8 disponible, no instalado ni GiST de negocio probado; probar con fase/entorno autorizados. No rebajar controles de guia 05. |

### Comandos y evidencia del cierre

Desde raiz en Git Bash, sin regenerar locks ni repetir provision/rehearse sobre la base existente:

| Comando | Resultado |
| ------- | --------- |
| `bash scripts/init-dev.sh --check` | Exit 0; PostgreSQL 18.4 y base exacta, servidor ya activo. |
| `OCOTE_RUN_PG_TESTS=1 backend/.venv/Scripts/python -m pytest -q backend/tests` | 33 passed, incluidos 7 casos PostgreSQL; warning TestClient/httpx conocido, no fallo. |
| `backend/.venv/Scripts/python -m ruff check backend` / `-m pip check` | Sin errores/incompatibilidades declaradas. |
| `backend/.venv/Scripts/python backend/tools/f1_local.py verify-existing --execute` | Exit 0, credencial administrativa solo en entorno privado. Backup/restore bloqueante, dos no-op, historia y catalogo legacy preservados, mantenimiento retirado solo por exito. |
| `backend/.venv/Scripts/python -m alembic -c backend/alembic.ini current` / `heads` | 20261124_0001 (head), una sola head. |
| `npm run build` | Exit 0; inicial 302.19 kB, transferencia estimada 75.31 kB, sin superar budgets. Solo scaffold productivo; fixture no incluida en app servida. |
| `CHROME_BIN='<Chrome local>' npm test -- --watch=false --browsers=ChromeHeadless` | 6 passed en Chrome 158: 3 scaffold + 3 prototipo; canvas ECharts no vacio, resize/dispose, Material/CDK y Timeline seleccion/ventana/CSS. Drag/drop probado por evento CDK, no gesto E2E humano. |
| `npm ls --all --json` | Cero problemas de peers/dependencias; Node 22.21.1/npm 10.9.4. |
| `npm audit --json` | 61 alertas; inventario/advisories consultados, sin audit fix ni cambios del lock. Excepcion expresa adicional D07, no remediacion. |

Versiones resueltas del prototipo: Angular core/Material/CDK 18.2.14, CLI 18.2.21, TypeScript 5.5.4, RxJS 7.8.2, ngx-echarts 18.0.0, ECharts 6.1.0, vis-timeline 8.5.6 y vis-data 8.0.6. ngx-echarts declara echarts >=5.0.0; la integracion real con ECharts 6 paso. package-lock.json se conserva con SHA-256 ed33229e23b14cbf548c7e53c7622f3483b8dee926426008fac5a06e023786e2. No se ejecutaron npm ci ni upgrades como parte del cierre. Los mocks de helpers anteriores no se reejecutaron porque sus implementaciones no cambiaron; no son prueba de negocio.

Verificacion de cierre **642b1122-bb0d-483e-8fd7-4ff309d09241**, request_id **188f86e8-9c68-4e74-9a8f-5ae5c60de18b**, final UTC **2026-11-25T02:31:01.661156Z**, total **5.085 s**. Evidencia privada ignorada: database/backups/f1-closure-642b1122-bb0d-483e-8fd7-4ff309d09241/ (journal, manifest y dump). closure.dump: **11307 bytes**, SHA-256 **c33d425c8017fae2e51539b3aef7ea210647f3e1b8df4675fb8cb39929ac1008**, snapshot estructurado **f87bcece0d5e9f63ee51627daa041e97ef24a987b4aa26f28512e881c53d5021**. artifact_sha256 **3caf35a1b74f2f85e9c7846f3f215f174419765e833220520866fcadd44bb03c** es el hash del inventario canonico de archivos del manifest, no del JSON completo, del checkout final ni de una release de cliente; sin firma.

Revision aplicada preservada byte a byte: SHA-256 **9ae3e2a4e570b89aa5296844949805001289dbb4889073b0f409ed26c8080bb6**. Comprobacion documental del cierre: 9 archivos, 114 referencias locales/anclas y 9 bloques JSON validos, fences balanceados e IDs conservados; git diff --check limpio y sin diagnosticos del editor en archivos tocados. Es validacion estructural, no prueba de diagramas renderizados ni cumplimiento semantico exhaustivo. Git no rastrea data/binarios/logs/dumps/.env/.venv; cambios ajenos preexistentes preservados, incluido scripts/db-start.test.cjs.

El destino ocote_f1_restore_ed913a74b9f4443696af67b0c708ab6c fue eliminado sin FORCE; cero temporales restantes. OIDs ocote=16384/ocoteAppDatabase=16389 y catalogo legacy preservados, sin leer filas de negocio legacy. En origen siguen solo alembic_version/release_history y las dos filas terminales de seccion 6; no se borraron ni reconciliaron de nuevo. PostgreSQL queda activo; no Uvicorn/dev server persistente. No initdb, reset, restore sobre origen, edicion de data/, seeds, nueva revision ni cambio de endpoints.

### Puerta de entrada F2

**Base lista para solicitar F2, no autorizacion de F2.** Antes de iniciarla: aprobar D02 (matriz de permisos/organigrama y responsables), D04 (catalogos y flujo inicial), definir identidad/custodio, entrega segura y recuperacion del primer admin sin credenciales por defecto, ratificar nombre organizacional y conservar zona D01 conforme RN-07; obtener autorizacion expresa F2 dentro de los limites temporales anteriores. D03/D08 y ejemplos temporales siguen sus puertas F3/F6.

Primer trabajo tras esas aprobaciones: especificar y crear revisiones F2 propias para identidad/administracion (departments/users/audit_events/refresh_sessions, system_settings/priorities/horizon_types y workflow), seeds conservadores y bootstrap de uso unico; despues sesion JWT/Argon2id/CSRF y politicas positivas/negativas. No editar la revision aplicada, crear todas las tablas objetivo ni iniciar planes/tareas/evaluaciones o pantallas funcionales por anticipado.
