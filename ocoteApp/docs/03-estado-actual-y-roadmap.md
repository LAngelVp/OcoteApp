# OCOTE: estado actual y roadmap

Version documental: 2.1,2026-11-25. **Incremento F7 acotado completado**, [evidencia vigente](#cierre-del-incremento-f7-acotado): head0006/26 tablas/siete releases, datos previos preservados, PG1:178 y Angular171 aprobados, API live/ready200, relevo eliminado. Setup Wizard e instalador/empaquetador in-house diferidos al cierre final posterior a branding/F8..F12; fases aun no autorizadas. Secciones1..18 y avances parciales de19 conservan evidencia historica, no sustituyen este cierre acotado ni certifican entrega cliente.

Estado vigente: **F6 autorizada/implementada/migrada local/sintetico**, [evidencia y limites](#17-analitica-evaluaciones-y-exports-f6-local-2026-11-25). F5 conserva cierre operativo pendiente segun [seccion11](#11-kanban-timeline-y-evidencias-f5-local). El titular ratifica D03/D08/RN-06, calendario manual y operaciones gerenciales admin/gerente; autoriza avanzar sin fingir aceptacion operativa F5. Almacenamiento/ClamAV reales pospuestos, cargas cerradas, bootstrap preservado, sin seeds. F7 bloqueado. Excepciones D06 sin suplente y D07 soporte Angular/61 alertas de [seccion7](#7-cierre-formal-f1-local) extendidas expresamente a F6 hasta2026-12-24, mismo responsable y limites locales, sin renovacion automatica. Secciones historicas conservan evidencias, no inventario vigente ni aprobacion productiva.

Referencias normativas: [SDD](01-spec-driven-development.md), [arquitectura y datos](02-arquitectura.md), [entorno local](04-entorno-y-portabilidad.md), [entrega/actualizaciones](05-paquetizacion-instalacion-y-actualizaciones.md). RF-01..15/RN-01..07/D01..08/F0..F7 conservados; RF-16..35/RN-08..20/D09..16 son contratos futuros. El inventario diagnostico de seccion1 y actas1..16 son historicos, no reemplazan seccion17 ni autorizan fases nuevas.

## 1. Donde nos encontramos

### Evidencia observada en el workspace

| Area                    | Evidencia                                                                                                                                            | Interpretacion                                                                                                |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Proyecto                | [package.json](../package.json), nombre ocote-app, version 0.0.0                                                                                     | Angular creado en raiz, no monorepo con herramientas adicionales                                              |
| Framework               | Dependencias Angular ^18.2.x; CLI/build ^18.2.21; TypeScript ~5.5.2                                                                                  | Linea 18.2 declarada, no certificacion de versiones resueltas ni build exitoso                                |
| Render y estilos        | [angular.json](../angular.json): builder application, browser src/main.ts, SCSS, sin opciones server/SSR                                             | SPA sin SSR configurada                                                                                       |
| Componente              | app.component.ts/app.component.html en el diagnostico F0; plantilla inicial retirada por F4, ver seccion10                                           | Componente standalone con titulo ocoteApp y plantilla inicial de Angular en F0; no inventario vigente          |
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

Dependencia: F1. D02/D04 confirmadas en la autorizacion F2 de seccion 8. La instalacion queda vacia deliberadamente; provision segura del primer admin y configuracion explicita del operador son necesarias antes de uso, no defaults de migracion. Revisar refresh/CSRF y credenciales, introducir nombre/zona RN-07.

Entregables: departments/users/audit_events/refresh_sessions, system_settings/priorities/horizon_types y etapas/aristas, migracion aditiva sin seeds segun autorizacion expresa; bootstrap admin de uso unico sin default, JWT/Argon2id/CSRF y politicas. RF-01/RF-02/RF-13 API; no tableros de negocio. Zona sin override env; probar proteccion desde F3 con primera tarea/evaluacion real.

DoD: ciclo sesion/CSRF/reuso/revocacion, carreras ultimo admin y 401/403/404; politicas positivas/negativas por modulo/proyeccion, no solo boton oculto. Parametros rechazan claves/tipos/limites invalidos y conflictos; procesos leen BD sin cache; cinco horizontes/normal/custom protegidos. Migracion/no-op no inventan ni pisan datos; bootstrap repetido no duplica/resetea admin. Workflow inicial/terminal y grafo validos al configurar atomicamente. Instalacion vacia reporta configuracion incompleta, no viola este contrato ni habilita F3.

Riesgo principal: permisos solo visuales o cookies vulnerables. Mitigacion: autorizacion central, pruebas negativas en servidor y HTTPS/origen/CSRF.

### F3. Nucleo de planes, ejecucion, fechas y auditoria

Dependencia: F2. Ejemplos D01, formulas del nucleo y cierre irreversible/fechas D04 ratificados por autorizacion F3 de seccion 9. D03/D08 gerenciales siguen F6. Configuracion explicita es requisito de uso, no datos que deban inventarse para pruebas aisladas. Sin reapertura fuera del MVP.

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
| D02 Un departamento/rol por usuario no cubra organigrama           | Gerencia + seguridad        | Confirmada para F2 local: un rol; departamento obligatorio L/C. No memberships implicitas; custodia del admin pendiente del operador |
| D03 Pesos iguales sin criterio de calidad                          | Gerencia                    | F3; aceptar metricas separadas, no prometer score de productividad                                                                    |
| D04 Etapas/cierre y catalogos iniciales                            | Administrador de proceso    | Semanticas F2 confirmadas, sin seeds; operador elige etiquetas/posiciones/grafo. F3 ratifica cierre/solicitudes y F5 evidencia |
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

Acta historica del 2026-11-24 local. Titular y responsable operativo: **LUIS ANGEL VALLEJO - DESARROLLADOR**. El usuario autorizo completar F1, ratifico decisiones y acepto expresamente los riesgos delimitados abajo. **F1 queda cerrado en Windows x64, PostgreSQL portable 18.4/loopback y datos sinteticos; no es una liberacion productiva ni homologacion nube/F7.** Secciones 1, 5 y 6 conservan evidencia anterior; seccion 8 registra el incremento posterior F2. En este cierre F1 no hubo cambios de dependencias, helpers previos, endpoints de negocio ni pantallas funcionales.

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

## 8. Identidad y administracion F2 local

### Autorizacion y estado

El titular autoriza expresamente implementar/verificar F2 local con datos sinteticos y confirma D02/D04: un rol por usuario, departamento obligatorio para lider/colaborador, etapas globales con inicial open sin requisitos y terminal completed unica, transiciones sin gerente y con admin. Sustituye la puerta F2 pendiente de seccion 7; no altera su evidencia ni autoriza F3-F7. Se mantienen responsable, restricciones y vencimiento 2026-12-24 de las excepciones.

**Base F2 implementada y verificada; puesta en uso pendiente de bootstrap/configuracion explicitos.** Por instruccion expresa no se inventaron ni sembraron usuarios, departamentos, etapas, aristas, prioridades, horizontes o parametros. No se genero identidad/password de un admin real ni se eligio un origen HTTPS en nombre del operador. La herramienta segura esta probada con identidades sinteticas exclusivamente en bases aisladas eliminadas al terminar. No pantallas Angular funcionales, planes/tareas/evaluaciones, exports ni cargas de archivos.

### Entregables y pruebas

| Superficie | Implementacion y evidencia |
| ---------- | ------------------------- |
| Modelos/revision | [Nueve modelos](../backend/app/models/identity.py) y [20261124_0002](../backend/alembic/versions/20261124_0002_identity.py), aditiva desde 0001, sin INSERT/seeds. Nueve tablas F2 mas release_history y alembic_version; CHECK/FK/UNIQUE, indices, triggers de identidad/version y auditoria append-only. Ambas revisiones aplicadas quedan inmutables. |
| Sesion | Argon2id 64 MiB/3 iteraciones/2 vias, rehash; RSA >=3072/RS256 con kid y claims fijados. Access 10 min, refresh absoluto 7 dias, solo hash de jti en BD. Cookie Secure/HttpOnly/SameSite Strict, origen HTTPS loopback exacto, CSRF ligado a familia/expiracion. Rotacion/reuso concurrente, revocacion persistida antes del 401, logout idempotente y cambio/reset de password probados. |
| Permisos | Usuario/rol/departamento/token_version/familia consultados en cada solicitud. Admin para CRUD/configuracion/auditoria/releases; catalogos minimos L solo departamento, C solo propio contexto, G lectura global. Denegacion antes de lookup administrativo, 401/403/404 sanitizados y sin hashes. Cambio rol/departamento/estado/password revoca sesiones; carrera ultimo admin deja exactamente uno. |
| Administracion | Altas/PATCH con DTO allowlist, version y motivo; sin DELETE. Catalogos con codes estables, normal/custom protegidos, reordenamiento atomico, cuatro claves tipadas, grafo completo atomico con versionado y rollback. `/configuration-status` permite instalacion vacia y reporta incompleta; no crea datos. Lock advisory compartido/exclusivo y transaccion unica. |
| Bootstrap | [CLI](../backend/tools/bootstrap.py) crea claves privadas sin sobrescribir; bootstrap exige cero usuarios y lock exclusivo, captura password con getpass y audita. Repetir no crea/resetea identidades. Configuracion separada en backend/.local/auth.env ignorada; sin secretos en argumentos/SPA/logs. |
| Limites HTTP | JSON <=1 MiB, 413/415/422, request_id/no-store/nosniff, 401 con WWW-Authenticate, 429 con Retry-After. Login/refresh limitados por cuenta y cliente en memoria acotada por proceso; no proteccion distribuida productiva. |
| Herramienta local | [f2_local.py](../backend/tools/f2_local.py): lock de sesion/mantenimiento, cero sesiones ajenas, backup previo y restore bloqueantes, upgrade, no-op y restores posteriores; conserva historia/legacy. Fallo retiene mantenimiento y journal; si existe fila propia running intenta terminal failed sin modificar terminales. Sin reset, downgrade, stamp, create_all o restore sobre origen. |

Dependencias nuevas revisadas y fijadas con hashes: argon2-cffi 25.1.0, PyJWT 2.15.1 y cryptography 50.0.2 (mas transitivas). Regeneracion con pip-tools sin upgrade global y con --allow-unsafe para incluir setuptools fijado. Angular/package-lock y revision F1 preservados; no audit fix ni cambio de stack.

| Gate ejecutado | Resultado real |
| -------------- | -------------- |
| `bash scripts/init-dev.sh --check` previo/posterior | Exit 0, PG18.4 y base exacta, servidor ya estaba activo y queda activo. Su mensaje heredado de siguiente paso F1 no gobierna la fase vigente. |
| `f2_local.py check-migration --execute` | Migracion desde cero en base temporal unica, nueve tablas vacias y segundo upgrade no-op; destino eliminado. |
| `f2_local.py apply --execute` | Exit 0, backup/restore before, upgrade, segundo upgrade no-op, restore after y recorded; reapertura solo al terminar validaciones. No se repite sobre head0002. |
| `OCOTE_RUN_PG_TESTS=1 backend/.venv/Scripts/python -m pytest -q backend/tests` | **58 passed**: 33 base F1 actualizados, 1 caso adicional de head obsoleta y 24 de identidad/administracion. Incluye PostgreSQL real aislado, carreras de refresh/ultimo admin, scopes/errores, no-defaults, bootstrap no repetible, reordenamiento/rollback, paginacion/proyeccion de auditoria/releases y backup fallido antes de Alembic. Una deprecacion TestClient/httpx conocida, sin cambiar dependencias solo para silenciarla. |
| `backend/.venv/Scripts/python -m pytest -q backend/tests` sin opt-in | **33 passed, 25 skipped**; la suite ordinaria no conecta PostgreSQL ni crea fixtures de negocio en origen. |
| `python -m ruff check backend` / `python -m pip check` | Limpios, usando backend/.venv/Scripts/python. |
| Alembic `current` / `heads` | Ambos **20261124_0002 (head)**; head unica. Health ready positivo y negativos comprobados en suite. |
| Inventario final de solo lectura | Once tablas; cero filas en las nueve F2 (incluidas users/audit_events), tres releases terminales, cero temporales, maintenance ausente. ocote OID16384 y ocoteAppDatabase OID16389 conservados. |
| Documentacion/integridad | 9 documentos, 141 referencias locales/anclas, 9 JSON validos, fences balanceados e IDs conservados; diff check limpio. Hashes F1/package-lock identicos al acta anterior; no secretos/claves/dumps/data/logs/venv en archivos rastreados o nuevos no ignorados. Frontend/helpers y herramientas F1 sin cambios. |

El editor no reporta errores en los archivos F2 tocados. Si reporta un diagnostico TS6 de rootDir en tsconfig.json, no modificado por esta tarea; no se corrigio ni se repitio build Angular por estar fuera de alcance. Las pruebas/build frontend de seccion 7 son historicas, no gates reejecutados de F2. La validacion documental es estructural, no prueba de diagramas renderizados ni de cobertura semantica completa.

### Evidencia de migracion y recuperacion

Intento **c7eb0899-dc10-41ec-b347-11bd84218652**, request_id **ea97b886-d16e-416f-a0a1-fa1028cc27fb**. Inicio UTC 2026-11-25T03:10:09.417876Z; fin 03:10:16.748611Z; **7.769 s**. Resultado release_history `succeeded/F2_LOCAL_VERIFIED`, version2. Las dos filas F1 terminales conservaron su identidad/resultado/version. No reescritura de historia ni lectura de registros de negocio legacy.

| Dump privado | Bytes | SHA-256 | Restore medido |
| ------------ | ----- | ------- | -------------- |
| before.dump | 11307 | d821304dbb0a5f94964b616668e400e991629150054ce08583fcb655cceddcaf | 0.555 s |
| after.dump | 45945 | 8decd760df3389b7d1731bd228a1b9f7db955ff26dbd0933f6675c94beed2616 | 0.676 s |
| recorded.dump | 46196 | 6311a3540070b23c187775f76684a5ee54612aac2a7a67249152e660501d5fd9 | 0.656 s |

Dumps, manifests y journal fsync con ACL privada en database/backups/f2-c7eb0899-dc10-41ec-b347-11bd84218652/, ignorados por Git. SHA-256 de revision F2 aplicada: b14f3196c0572385d9af86cd451181b809933726cb89ce9915c3286df428006f. Restore siempre a destino unico del mismo cluster, --no-owner/--no-acl, sin --clean/FORCE ni sobrescribir origen/legacy. Se compararon datos/revision, columnas, propiedades de constraints, indices, triggers/funciones y probes F1 con rollback. `--no-acl` prueba recuperacion logica, no restauracion de grants; permisos runtime se verificaron aparte en suite. Los tiempos no son RTO/RPO productivos ni recuperacion de host.

recorded.dump contiene el intento running; el evento terminal posterior exige reconciliacion desde journal al restaurar antes de reabrir. Manifest es instantanea del ensayo local no firmada, no hash del checkout final: pruebas posteriores completaron contratos API/contingencia sin modificar revision aplicada ni repetir upgrade de origen. No paquete cliente/ocote-admin, cifrado/copia off-host, scheduler, TLS/proxy real, multiples workers, carga o homologacion nube.

### Retoma y puerta F3

Seguir [runbook de bootstrap](../backend/README.md#bootstrap-y-configuracion-f2): el operador elige origen HTTPS loopback y canal/custodia, inicializa claves sin sobrescribir y aporta nombre/email/password del primer admin directamente en terminal. Configura explicitamente nombre, zona oficial America/Mexico_City, limites, cinco horizontes, prioridad normal activa y grafo valido; verificar `/configuration-status`. No ejecutar seeds ni usar datos de pruebas en origen. Hasta entonces autenticacion no inicializada falla cerrada y configuracion esta incompleta por diseno.

**F3 no autorizado ni iniciado.** Antes de solicitarlo: resolver bootstrap/custodia/configuracion reales, registrar aceptacion de ejemplos temporales/D03/D08 y reglas de cierre/fecha D04 pendientes de negocio, revisar excepciones vigentes y obtener autorizacion expresa. RF-03..RF-15 de fases posteriores no se declaran implementados por estas pruebas; UI F4 y evidencia F5 siguen bloqueadas.

## 9. Nucleo operativo F3 local

Autorizacion expresa del titular del 2026-11-24: RF-03/04/05/11, solicitudes RF-14 y RN-01..06 aplicables al nucleo. Sustituye la puerta F3 anterior, no evidencia historica F1/F2. D01 America/Mexico_City y formulas/cierre irreversible ratificados; D03/D08 gerenciales siguen F6. F4-F7 no autorizados: sin UI, evidencia/Kanban/Timeline, analytics/evaluaciones/exports ni nube/produccion.

Se conservan responsable LUIS ANGEL VALLEJO - DESARROLLADOR, vencimiento 2026-12-24 y excepciones D06 sin suplente/D07 soporte Angular y 61 alertas separadas. Solo local/sintetico, sin red compartida ni entradas no confiables; sin responsable se suspenden migraciones/restores. No semillas/defaults ni datos reales autorizados por este desarrollo.

Implementacion: [revision0003](../backend/alembic/versions/20261124_0003_operations.py), [servicio](../backend/app/services/operations.py), [rutas](../backend/app/routers/operations.py), [pruebas](../backend/tests/test_operations.py) y [protocolo](../backend/tools/f3_local.py). Seis tablas annual_plans/objectives/tasks/subtasks/task_history/due_date_requests, fechas civiles ISO estrictas, UTC del servidor, originales/cierre protegidos, versiones e historia/decisiones atomicas. Scopes antes de filtros/agregacion/paginacion; C sin agregados, L departamento y G no mueve tareas. Evidencia requerida devuelve 422 hasta F5. Flush explicito y lock compartido de configuracion; filas departamento -> usuarios UUID ordenados -> plan -> objetivo -> tarea -> subtarea -> solicitud; administracion exclusiva.

Origen0002 ->0003 con migrador, lock persistente/mantenimiento/journal ACL privado. Before restaurado y migrado/no-op en UUID aislado antes de DDL origen; upgrade/no-op origen y cuatro restores. Intento e8ae650e-ed05-41fa-8cc6-0d206b7fed95, request_id349637c6-3382-4b9f-982b-6757a2f2cea9, succeeded/F3_LOCAL_VERIFIED version2. Inicio UTC2026-11-25T03:53:50.998863Z, evento final03:54:25.755377Z, 36.322 s. No repetir apply ni editar0003; SHA-256 c061c8aa372d34a881107bb37bb771d62a17db9e01bfc7d422c7c1f6e0775dc8.

| Dump privado | Bytes | SHA-256 | Restore |
| ------------ | ----- | ------- | ------- |
| before.dump | 46190 | 23057f4a7d6072dd2ece4947ac12bcb6821e44208ccd2e37bb00e9cf47dff0f4 | 1.703 s |
| after.dump | 82823 | 24b4327d4302b5d9236f1cb96c863531e3e8944d8e32184385705a32b962c70f | 2.020 s |
| recorded.dump | 83045 | 4d75dd296f27fb89c48235cb7b574e8b6802f74f471b7b9a93119e2f1bb0ac7b | 2.180 s |
| terminal.dump | 83034 | 288e3a21a894576ccfd4ed977cbd4b151950de642af02e239a5042659d6064d0 | 2.320 s |

Artefactos en database/backups/f3-e8ae650e-ed05-41fa-8cc6-0d206b7fed95/, ignorados/ACL privados. Prefijo temporal ocote_f2 reutilizado sin alterar helpers F1/F2; todos eliminados sin FORCE. Comparacion logica/estructural y grants runtime aparte: --no-acl no prueba recuperar ACL ni equivalencia formal de constraints. terminal incluye intento terminal; recorded contiene running y exige reconciliar journal. Manifest no firmado/instantanea, no checkout final, cifrado/copia off-host, recovery de host ni SLA.

Verificacion: **90 passed** con opt-in PostgreSQL; **46 passed/44 skipped** sin opt-in; Ruff format/check (31 archivos), pip check y diagnostico backend limpios. Preflight correcto, head0003 unica/17 tablas, cuatro releases terminales version2 y tres anteriores preservadas, OIDs ocote16384/ocoteAppDatabase16389 conservados, cero temporales/mantenimiento. PG ya activo y queda activo, sin API/dev server iniciado. Frontend/lock, scripts y herramientas F1/F2 intactos.

Cierre documental: nueve documentos/154 enlaces locales con anclas, fences balanceados/nueve bloques JSON validos, IDs RF/RN/D/F y paleta conservados,19 entidades ER objetivo. SHA-256 de las tres revisiones y package-lock verificados; diff sin errores de espacios y cero artefactos privados visibles para Git. Comprobaciones documentales sin reconectar BD; no prueban renderizado ni homologacion productiva.

Cobertura: 0/1/4 subtareas, progreso y pending_closure, medianoche/puntualidades, contencion/originales, scopes/errores/append-only, rollback historia/decision, migracion con datos F2 sinteticos preexistentes y fallos backup/restore bloqueantes. Carreras reales cierre/alta subtarea, cierre/aprobacion y periodo/alta tarea; promedio por tarea y filtros SQL. No SQLite ni fixtures en origen. Deprecacion TestClient/httpx y TS6 rootDir ajeno al cambio no remediados; sin build Angular repetido. Validacion documental estructural no prueba render ni cobertura semantica exhaustiva.

La migracion comprobo quince tablas F2/F3 vacias y no ejecuto bootstrap/seeds. Durante cierre se detecto bootstrap_admin del operador a UTC04:00:35.500686 (posterior al protocolo): auth.env presente, un usuario/un audit_event; no se modificaron ni revirtieron. Otras trece tablas F2/F3 vacias, incluidas las seis F3; settings/catalogos/workflow pendientes. terminal.dump no cubre esas escrituras posteriores.

Siguiente puerta F4: operador confirma custodia/origen HTTPS y bootstrap existente sin repetir/sobrescribir, completa configuracion explicita y verifica configuration-status segun [runbook](../backend/README.md#bootstrap-y-configuracion-f2). Requiere autorizacion expresa F4, muestra accesible con tokens OCOTE, licencia/autoalojamiento tipografico y mapeo publico Material18.2; no habilitar fases posteriores por anticipado.

## 10. Sistema visual y flujos Angular F4 local

Autorizacion expresa del titular2026-11-24: RF-01..05/RF-11 y RN-01..06 de interfaz, mas configuracion explicita/solicitudes sobre contratos F2/F3. F4 implementada y verificada tecnicamente local/sintetico; **aceptacion funcional del operador pendiente**, no cierre productivo ni permiso F5. Sustituye la puerta F4 anterior, no evidencias historicas. Sin seeds/defaults ni fixtures de negocio en origen. Conserva excepcion hasta2026-12-24 bajo LUIS ANGEL VALLEJO - DESARROLLADOR, sin renovacion automatica: D06 sin suplente y D07 soporte Angular/61 alertas separados (2criticas/19altas/33moderadas/7bajas). Solo loopback/sintetico, sin red compartida/entradas no confiables. F5-F7 no autorizados.

### Alcance entregado

- [Rutas lazy](../src/app/app.routes.ts), [shell](../src/app/shell.ts) y [sesion](../src/app/core/session.ts): login/perfil/password/logout/restore, access/CSRF solo memoria, refresh cookie Secure/HttpOnly/SameSite Strict/Path auth, Web Locks obligatorios entre pestanas, single-flight, BroadcastChannel de cierre. 401 un retry/segundo401 expira;409 no retry; logout503 conserva identidad/error. Sin credenciales/secretos en SPA/storage.
- [Administracion](../src/app/admin/admin.page.ts) y [grafo atomico](../src/app/admin/workflow.editor.ts): departamentos/usuarios/passwords, catalogos/cinco horizontes, parametros tipados, etapas/aristas y reordenamientos, versiones/motivos, auditoria/releases lectura. Instalacion vacia permanece vacia hasta decisiones explicitas del admin, no alta automatica al visitar.
- [Planes/objetivos](../src/app/operations/planning.page.ts), [tareas](../src/app/operations/tasks.page.ts), [detalle/subtareas/historia](../src/app/operations/task-detail.page.ts), [solicitudes](../src/app/operations/requests.page.ts): rangos inclusivos/cruces de anio, contencion servidor, originales visibles/inmutables, cambios auditados/versionados, cierres explicitos, progreso/puntualidad servidor y motivo. A/G planifican; A/L gestionan; G no transiciona; C solo asignadas/contexto minimo, sin planes/solicitudes/agregados. Sin DELETE.
- [Editor](../src/app/shared/editor.ts) con formularios reactivos: validacion civil ISO real, limites/enteros/motivo, departamento L/C requerido;409 conserva valores y bloquea hasta descarte/recarga explicitos;422 conserva formulario, errores sanitizados/referencia. [Presentacion](../src/app/shared/presentation.ts) distingue fecha civil de timestamps UTC mostrados en America/Mexico_City.
- [Tema](../src/styles.scss), [tokens](../src/_ocote-tokens.scss), [paletas](../src/_ocote-palettes.scss), marca y fuentes locales. Sin Kanban/Timeline/evidencia/analitica/evaluaciones/exports; etapas que exigen evidencia no se habilitan como si F5 existiera.

### Verificacion ejecutada

| Comprobacion | Resultado y alcance |
| --- | --- |
| npm run build | Produccion exitosa, initial369.43kB/transfer94.73kB estimada, sin warning de budget; budgets/dependencias/lock sin cambios |
| ChromeHeadless158 Windows | **49 passed**:3 raiz,3 compatibilidad F1,13 sesion,8 editor,22 vistas/roles/contratos/guardas F4. Ultimo ajuste solo Sass: compilacion Sass, build y radios computados8px posteriores correctos |
| Backend PostgreSQL opt-in | **90 passed,1 warning conocido** TestClient/httpx;209.07s. F1 rollback y F2/F3 UUID aislados eliminados por suite; no fixtures de negocio en origen ni SQLite |
| Ruff / pip check | All checks passed / No broken requirements found; codigo y lock Python sin cambios |
| init-dev --check antes/despues | PG18.4 ya activo, identidad/base exactas y directorios correctos; no instala/migra/crea seeds ni arranca otro cluster |
| Navegador HTTPS/proxy | Salud200/CSRF sin cookie401 reales; AUTH_ORIGIN existente https://localhost:8443 preservado. Vistas autenticadas con interceptores sinteticos de navegador, no escrituras de negocio a API real |
| Roles/409 entre capas | G sin mover etapa; L sin fecha directa; C sin planes/solicitudes/admin y URL plan denegada. 409 retuvo fecha/motivo, expected_version7, sin original en payload; Guardar bloqueado, detalle sensible oculto/request_id visible |
| Dos pestanas reales | Web Locks disponibles, recarga concurrente con fixture produjo2 rotaciones adicionales y maximo1 refresh simultaneo; no tokens en localStorage/sessionStorage, cookie HttpOnly no visible por document.cookie |
| Responsive/teclado | Capturas/revision1440/768/360 de tareas/detalle/configuracion/dialogos; sin overflow de pagina, tablas con scroll contenido. Foco corregido sobre Material:3px azul/offset3px/halo blanco2px.25 Tab mantuvieron foco en grafo. Zoom CSS200% de configuracion sin overflow; no ensayo exhaustivo de zoom nativo/lector |
| Assets/contraste | Marca no vacia, Source Sans3/Material Icons cargadas localmente; pares de texto/estado/foco >=4.5:1 segun matriz SDD. No auditoria WCAG exhaustiva ni prueba de todas las combinaciones posibles |
| Integridad | SHA-256 de0001/0002/0003 y package-lock identicos a actas; backend ejecutable/helpers/configuracion auth sin diff. Sin nuevas revisiones/provision/reset/restore origen ni cambios de legacy/releases historicas |
| Documentacion |9 fuentes sincronizadas,177 referencias locales/anclas,9 JSON,39 fences balanceados,19 entidades ER e IDs RF/RN/D/F conservados; git diff --check limpio. Validacion estructural basica, no AST/render Mermaid ni prueba semantica exhaustiva |

Comandos frontend reproducibles en README; backend: OCOTE_RUN_PG_TESTS=1 con PGPASSWORD administrativo temporal del operador, pytest -q backend/tests, ruff check backend, pip check y preflight. No imprimir secretos ni introducirlos en SPA/agente. Helpers mock no repetidos porque no cambiaron. No audit npm ni upgrade: siguen61 alertas bajo excepcion, no remediadas por build.

### Material, fuentes y entorno

Schematic local @angular/material:m3-theme, light, primary#B85A1E/secondary y tertiary#2E5A44/neutral#5C534A. primary M3 tono40#9B4505, secondary/tertiary tono40#3B6750 y on-colors blancos; mapas completos secundarios anidados/publicos, no opcion inexistente color.secondary ni variables privadas. mat.core una vez, tipografia Source Sans3/densidad0, overrides publicos button/dialog container-shape8px comprobados. Tokens de marca permanecen exactos; matriz de contrastes en SDD5.

Source Sans3 VF Upright WOFF2 desde adobe-fonts/source-sans commit87b37a2daaed80fcb8e8ccb0085c4d72ddade12e, OFL1.1 en [licencia](../public/fonts/Source-Sans-LICENSE.md). MaterialIcons-Regular TTF desde google/material-design-icons commitd7a78a2ad434d5d38e1b8708c9dd9847cc3ada9b, Apache2.0 en [licencia](../public/fonts/Material-Icons-LICENSE). Descarga oficial fijada/firma de formato y texto de licencia comprobados; fuentes autoalojadas sin CDN runtime. Pine mark propio, no asset de negocio.

Servidor Angular iniciado por esta tarea solo en127.0.0.1:8443 con --ssl; abrir **https://localhost:8443/login**, origen exacto del operador. Bind localhost inicial soloIPv6 no conectaba; se sustituyo exclusivamente nuestro proceso por bindIPv4. API existente127.0.0.1:8000 y PostgreSQL se preservaron. [Proxy](../proxy.conf.json) mantiene Origin, /api a API loopback, logs silenciosos. Certificado autofirmado aceptado solo en sesion automatizada mediante CDP; no confianza del sistema ni TLS cliente/productivo homologado. Fixtures/rutas/cookie sintetica retirados; navegador final en login real, storage vacio. No se solicito/uso password del operador ni se altero su bootstrap/configuracion.

### Limites y siguiente puerta

Backend/migraciones/roles/protocolo de release F3 no cambiaron. Ultima observacion de datos de origen es seccion9; no se recontaron por documentacion ni se revirtieron escrituras del operador. Pruebas API aisladas y mocks UI no son un E2E autenticado con identidad/configuracion reales del operador. Pendientes: aceptar muestra/recorridos con su sesion, completar configuracion explicitamente y confirmar custodia. No certificar lector de pantalla, todos los navegadores, zoom nativo, accesibilidad integral, soporte Angular o seguridad productiva por estas pruebas.

**F5 bloqueado hasta nueva autorizacion expresa**, aceptacion funcional F4 y configuration-status completo. Antes de cargas: D05 privado/autorizado, PDF/PNG/JPEG max10MiB, cuarentena/antimalware mantenido fail-closed y pruebas; no activar evidencia por MIME solamente. D03/D08 siguen F6, paquete/instalacion/nube F7. Responsable/fecha de excepciones no cambian; sin suplente independiente antes del vencimiento o nueva decision expresa no hay renovacion automatica.

## 11. Kanban Timeline y evidencias F5 local

Autorizacion expresa del titular2026-11-24 para RF-06/RF-07/RF-08 y revision aditiva0004 con protocolo de release. **Implementada y verificada tecnicamente local/sintetico; cierre operativo pendiente**, no aceptacion/configuracion F4 ni scanner real presumidos. Sin seeds/defaults/identidades ni fixtures en origen. Responsable LUIS ANGEL VALLEJO - DESARROLLADOR, excepcion local/sintetica hasta2026-12-24 conservada. F6-F7 no autorizados; helpers/revisiones0001/0002/0003/legacy/releases historicas intactos. Sin DELETE de evidencia publicada segun RN-04/D05.

### Implementacion y ensayo

[Revision0004](../backend/alembic/versions/20261124_0004_evidence.py), [almacen/ClamAV](../backend/app/core/evidence.py), [servicio](../backend/app/services/evidence.py), [API](../backend/app/routers/execution.py), [pruebas](../backend/tests/test_execution.py), [protocoloF5](../backend/tools/f5_local.py), [Kanban/Timeline](../src/app/operations/execution.page.ts), [evidencias](../src/app/operations/evidence.ts) y [transicion compartida](../src/app/operations/transition.ts).

Kanban pagina cada carril activo/vacio con filtros y conteos de alcance previo; C solo propias, G sin mover/cargar. Drag y boton usan mismo comando versionado/motivo/IDs. No movimiento optimista: cancelacion/409 conserva tarjeta. Timeline readonly usa vis-timeline fuera de NgZone, fechas civiles inclusivas, baseline/cierre en zona BD, niveles por permiso, grupos y tabla equivalente; sin drag de fechas. Fuentes/activos/tokens OCOTE y dependencias conservados.

PDF/PNG/JPEG con limite BD y10MiB duro, MIME/extension/firma/hash; cuarentena privada fuera del checkout, ACL nativa Windows y rechazo de enlaces/junctions. Solo ClamAV limpio/fresco publica. Scanner sintetico inyectado en tests, nunca fallback runtime. Atomicidad fila/version/historia/auditoria con compensacion de archivo nuevo por rollback cierto; commit incierto exige reconciliacion del operador, sin job automatico ni purga. Descarga autorizada attachment/nosniff/no-store con integridad y solicitud auditada. ACL por PowerShell fallo con politica1260; se sustituyo por API nativa sin cambiar la politica ni relajar ACL. Prueba real Everyone rechazada en temporal privado.

Operador confirmo detener API/escritores tras detectar3 conexiones; herramienta exigio cero conexiones antes de comenzar. Origen0003 ->0004 con ocote_migrador, lock persistente/mantenimiento y journal ACL privado. Before restaurado/migrado/no-op en UUID aislado antes de DDL origen; upgrade/no-op origen; cuatro dumps/restores before/after/recorded/terminal y ensayo restaurado adicional (cinco restores). Intento **f81efebb-718d-4899-bfec-c34eca858caf**, request_id162e4de4-6dff-467d-ace6-fa36f98009c6, succeeded/F5_LOCAL_VERIFIED/version2. UTC2026-11-25T05:42:42.261693Z a05:43:02.157764Z;20.312s. No repetir apply sobre origen0004.

| Dump privado | Bytes | SHA-256 | Restore |
| --- | --- | --- | --- |
| before.dump | 85378 | 96526447b2121a31d10152acf087375cfa1699bd7551b13a1f55b6c9b8b80bd9 | 1.250s |
| after.dump | 91021 | 19fbde27af02cf11299d280e8a0567bc8eb25361b00737f318206da91373f0b2 | 1.581s |
| recorded.dump | 91241 | e3fece68f12fcb12a625043db8ff118a2b6199cb0a7bcaa14a531bb9899c28e8 | 1.288s |
| terminal.dump | 91232 | a0b7cf09d682194f3db5c82ea6a33d0c3cdec14e0ea178c4a5666f9a3350c2c9 | 1.491s |

Artefactos en database/backups/f5-<attempt>/ ignorados, no publicados. Manifest es instantanea sin firma, no checkout final. Solo datos preexistentes preservados, sin evidencia publicada en origen; dump BD vacio de archivos **no prueba restore BD+evidencia operativa ni recuperacion de host/cifrado/off-host**. Cuatro releases anteriores se compararon sin cambio y nueva terminal capturada antes de reapertura. Head0004 unica/18 tablas/cinco releases terminales; seis F3/evidence_files vacias. Mantenimiento retirado solo tras exito; ocote/OIDs/roles preservados.

### Verificacion y limites

| Comprobacion | Resultado |
| --- | --- |
| PostgreSQL opt-in | **105 passed**,146.69s;1 warning TestClient/httpx conocido. Fixtures F2/F3/F5 solo UUID eliminados; F1 rollback tecnico origen |
| Sin opt-in | **56 passed/49 skipped**,5.15s, sin conectar PG |
| Calidad | Ruff/pip check limpios, sin instalar/actualizar dependencias |
| Angular | **59 ChromeHeadless passed**, build392.40kB inicial/98.05kB transferencia estimada; chunk lazy vistas639.74kB. Sin ampliar budgets; prueba de zona API Pacific/Auckland distinta del navegador |
| Navegador sintetico | 1440/360: Kanban3 carriles con vacios, drag/motivo/cancelar, boton/evidencia/409 con motivo conservado y Guardar bloqueado; Timeline no vacio, baseline/cierre, zoom efectivo/tabla; archivos/nombres/hash en movil sin desbordamiento. Fuentes/imagen locales cargadas |
| Entorno real | Preflight PG18.4/base exacta, ready/roles/head0004 siete pruebas positivas; API F5 en127.0.0.1:8000 tras parada confirmada, Angular HTTPS loopback8443/origen intacto |

No raiz EVIDENCE_STORAGE_ROOT ni EVIDENCE_CLAMAV_PORT configurados en el entorno, ni instalacion/escaneo ClamAV reales ensayados. Cargas operativas deshabilitadas por servidor/UI; los tests identifican dobles sinteticos y no prueban motor real, definiciones, antimalware mantenido ni E2E autenticado con identidad/configuracion del operador. No nuevas entradas no confiables/datos reales bajo excepcion. No homologacion AA integral/lector/navegadores, TLS productivo, seguridad de dependencias ni SLA por pasar estas pruebas.

Siguiente puerta: operador completa configuracion existente sin overwrite, valida configuration-status, raiz privada externa/ACL/ClamAV mantenido y pruebas reales limpio/deteccion autorizada/caida/timeout/definiciones viejas/restore coherente; acepta F4/F5 con su propia sesion. Solo despues cerrar operativamente F5. **F6 requiere nueva autorizacion expresa y ratificacion D03/D08**; F7, exports/analytics/evaluacion/nube no implementados. D06 sin suplente y D07 separados conservan responsable/fecha2026-12-24 sin renovacion automatica.

## 12. Correccion frontend de administracion 2026-11-25

Correccion autorizada exclusivamente Angular/pruebas/documentacion tras F4/F5; no cambia reglas, fases ni actas anteriores. Backend y contratos consultados solo en lectura. Sin cambios en backend, migraciones0001..0004, helpers/scripts, lockfile o database; sin comandos de BD, seeds ni configuracion de negocio inventada. Conserva sesion/CSRF/roles, versiones y tema OCOTE; cierre operativo F5 y restricciones D06/D07 siguen pendientes en los terminos anteriores.

### Causas y correcciones

- El track anidado de administracion usaba `row['id'] ?? row['key']`, susceptible al temporal indefinido de Angular18 reportado como tmp_18_0. Se reemplaza por una funcion pura de clave estable. Auditoria AST TypeScript/Angular de los25 archivos de src/app:16 plantillas y29 bucles, incluidos anidados; restantes tracks directos o referencias estables de FormGroup, sin coalescencia/encadenamiento opcional/condicionales en track.
- El input con `[type]` dinamico no seleccionaba NumberValueAccessor: al escribir un entero, el formulario podia conservar un string y rechazarlo. Rama estatica `type="number"`, enteros seguros/normalizacion estricta y payload numerico compartidos con el editor de grafo; sin truncar decimales ni adivinar separadores locales. Se valida entrada DOM real, cero, strings enteros, limites, decimales y valores ambiguos.
- Tras crear un ajuste, la clave seleccionada podia permanecer aunque desapareciera de las opciones. Se limpia solo esa seleccion al recargar y se bloquea Crear durante la recarga; no se elige otra clave por defecto. Los cuatro ajustes tienen campos visibles: nombre texto1..160, zona IANA texto1..100 sin opcion fija/preseleccion, evidencia entero1..10485760 y exportacion entero1..10000. RN-07/409 de zona usada siguen siendo autoridad del servidor.
- Reglas locales de etapas/transiciones alineadas al contrato: inicial abierta/activa sin requisitos, terminal activa sin salidas, roles validos/no duplicados/admin en arista activa, extremos distintos/activos cuando corresponde. Grafo completo verifica unicidad, inicial/terminal y caminos a terminal; preserva semanticas inmutables y expected_version. El servidor sigue resolviendo alcance, ocupacion, unicidad concurrente y conflictos.
- Cada apertura de Editor/WorkflowEditor crea controles/estado propios. Pruebas con MatDialog real verifican contenido completo tras cancelar/guardar/409 y descarte/recarga, sin borrar datos al recibir409 ni compartir filas canceladas. Las confirmaciones intencionalmente sin campos (completar subtarea/transicion sin requisitos) muestran contexto de la tarea/accion en lugar de un cuerpo vacio.

### Archivos y verificacion

[Administracion](../src/app/admin/admin.page.ts), [grafo](../src/app/admin/workflow.editor.ts), [editor compartido](../src/app/shared/editor.ts), [detalle de tarea](../src/app/operations/task-detail.page.ts), [transicion](../src/app/operations/transition.ts), [pruebas de vistas](../src/app/f4.spec.ts) y [pruebas del editor](../src/app/shared/editor.spec.ts); esta adenda es el unico cambio documental y no reescribe los resultados historicos.

| Comprobacion | Resultado |
| --- | --- |
| Build AOT | npm run build correcto,392.40kB inicial/98.05kB transferencia estimada; admin lazy25.02kB. Sin ampliar budgets ni modificar dependencias |
| ChromeHeadless | **80/80 passed**, incluidas21 regresiones adicionales; entradas DOM/payload, cuatro ajustes/versiones, grafo/reglas y reaperturas reales |
| Navegador sintetico | Cuatro ajustes creados/cancelados/reabiertos, limites y position de prioridades/horizontes enviados como number; sin ReferenceError. Modal IANA visible a360px sin desbordamiento de pagina |
| Alcance | git diff --check limpio; diff de backend/scripts/package-lock/database vacio. Sin limpieza manual de .angular/cache necesaria |

Navegador con API interceptada, datos sinteticos y sin escrituras a la API real; no demuestra aceptacion/E2E contra configuracion del operador. Rutas mock e identidad sintetica retiradas, pagina devuelta a https://localhost:8443/login. No se conecto/arranco/verifico BD por esta tarea frontend. No se repiten ni se atribuyen pruebas backend a este incremento. La siguiente puerta operativa F5 sigue siendo la de seccion11, sin autorizacion F6/F7 implicita.

## 13. Estabilizacion CRUD y consultas F1-F5 2026-11-25

Incremento autorizado full-stack sobre las operaciones disponibles; no inicia F6/F7 ni cambia las decisiones de retencion. Se conserva la seccion12 como evidencia historica independiente. Sin seeds/defaults/configuracion de negocio en origen, nuevas dependencias, migraciones de origen ni cambios a revisiones0001..0004, scripts, helpers f1_local..f3_local, lockfile o database. El unico ajuste de produccion backend es validacion de entrada, sin DDL ni cambio de roles.

### Hallazgos y cambios

- El consumidor de transiciones descartaba las etapas de `/catalogs/workflow` porque exigia `is_active`, campo no devuelto por esa proyeccion ya filtrada. Ahora acepta ausencia del indicador y sigue descartando un falso explicito; conserva aristas autorizadas, requisitos y version.
- El editor compartido impide precargar `reason`, valida texto tras trim y envia el motivo actual (10..2000), sin tocar contrasenas ni convertir fechas invalidas. Datos vigentes permanecen al editar. Pruebas distinguen motivo de creacion, modificacion y decision; 409 conserva contenido y bloquea reenvio.
- Administracion incorpora consulta de detalle fresco para recursos mutables y activacion/desactivacion explicita, confirmada y motivada con PATCH/version. Solo envia campos admitidos por cada DTO. Filas protegidas no ofrecen esa accion; dependencias y concurrencia siguen resolviendose en servidor, sin bajas en cascada.
- Crear una etapa abre el grafo atomico, tanto con instalacion vacia como existente. No inventa inicial/terminal/aristas/roles ni permite persistir una inicial activa aislada. Codigos/nombres/motivo se normalizan; semanticas existentes/versiones se conservan. La edicion individual permitida sigue disponible.
- `position` se acota a INTEGER PostgreSQL 0..2147483647 en DTO compartido, editor de catalogos, reordenamiento y grafo; evita overflow500 y devuelve422. Se rechazan enteros ambiguos, posiciones repetidas segun comando y grafo invalido, sin migracion.
- Cambios de periodo conservan visible el horizonte actual aunque este inactivo, sin ofrecerlo como default de alta. Una solicitud autorizada permanece visible si falla la consulta secundaria de tarea/subtarea; aprobar sigue bloqueado sin contexto. Evidencias limpian errores transitorios al reconsultar, pero conservan el bloqueo409 incluso si falla una descarga/recarga posterior.

### Matriz de acciones disponibles

| Recurso | Alta y consulta | Modificacion y motivo | Baja segura / limites |
| --- | --- | --- | --- |
| Departamentos / usuarios | Alta explicita, listado, detalle actualizado | PATCH con datos vigentes, motivo nuevo y expected_version; password por endpoint especifico | Desactivar/reactivar con confirmacion; usuarios activos/objetivos/tareas abiertas y ultimo admin protegidos por servidor |
| Etapas / transiciones | Grafo atomico sin precarga; listado/detalle | Campos permitidos o grafo completo versionado; motivo actual | Desactivar solo si grafo/dependencias lo permiten; inicial/terminal/etapa ocupada protegidas, sin omitir filas existentes |
| Prioridades / horizontes | Alta explicita y consulta; solo cinco codes de horizonte | Nombre/orden/actividad con motivo/version; reordenamiento atomico | Desactivar/reactivar, nunca normal/custom ni renombrar code; referencias previas conservadas |
| Parametros | Cuatro claves explicitas tipadas, listado/detalle | Valor y motivo actual/version; zona bloqueada tras uso | Sin DELETE ni desactivacion; sin secretos/claves libres |
| Planes / objetivos | Crear/listar/detalle segun rol y alcance | Datos ordinarios segun DTO; periodos con motivo/version, fechas contenidas y originales preservados | Plan cierra por comando validado; sin DELETE de plan/objetivo ni cascada |
| Tareas / subtareas | Alta, listado/detalle e historia segun alcance | Edicion, programacion, reasignacion, fechas, etapa/cierre segun contrato; motivo solo cuando el comando lo admite/requiere | Sin DELETE; completadas de solo lectura. Confirmar comando recarga detalle/contexto; historia se vuelve a consultar explicitamente |
| Solicitudes de fecha | Alta desde recurso, listado/detalle, motivo original readonly | Aprobar/rechazar/cancelar con motivo nuevo/version; no autoaprobacion | Cancelacion conserva solicitud y decision; estados terminales inmutables |
| Evidencia | Consulta/descarga privada y carga solo con almacenamiento/antivirus configurados | Version y reglas del servidor; IDs de la misma tarea | Sin DELETE de publicado; 409 exige descartar archivo y recargar tarea |
| Historia / auditoria / releases | Consultas y proyecciones permitidas por alcance | Solo lectura, sin editar motivos pasados | Sin baja ni purga por UI/API |

### Archivos y evidencia reproducible

Backend: [DTO](../backend/app/schemas/identity.py) y [pruebas de identidad](../backend/tests/test_identity.py). Frontend: [administracion](../src/app/admin/admin.page.ts), [grafo](../src/app/admin/workflow.editor.ts), [editor](../src/app/shared/editor.ts), [planificacion](../src/app/operations/planning.page.ts), [solicitudes](../src/app/operations/requests.page.ts), [evidencias](../src/app/operations/evidence.ts), [transicion](../src/app/operations/transition.ts), [pruebas de vistas](../src/app/f4.spec.ts) y [pruebas del editor](../src/app/shared/editor.spec.ts). Contrato aclarado en [SDD](01-spec-driven-development.md).

| Comprobacion ejecutada | Resultado |
| --- | --- |
| `bash scripts/init-dev.sh --check` | PG18.4 ya en ejecucion, identidad/base exacta verificadas; no se arranco/detuvo ni migro origen |
| `npm run build` | AOT correcto,392.40kB inicial/98.05kB transferencia estimada; admin lazy27.38kB. Sin cambios de budgets/dependencias |
| ChromeHeadless suite completa | **103/103 passed**;71 vistas/13 editor y resto de sesion/configuracion. Incluye payloads, refrescos, grafo vacio/existente, motivo nuevo, dependencias409 y consultas fallidas |
| `pytest -q backend/tests` sin opt-in | **57 passed / 50 skipped**,5.20s; no conexion PG |
| PostgreSQL opt-in test_identity/test_operations/test_execution | **62 passed**,144.70s, bases UUID aisladas eliminadas por fixtures. No se repitieron los siete casos tecnicos F1 de test_postgres sobre origen ni se atribuye suite completa PG a esta tarea |
| Caso API nuevo focal | Inicial activa aislada409/ninguna fila; grafo completo201; dependencia de departamento409 con problem+json/request_id/version intacta; baja logica tras desactivar usuario; FK conservada, DELETE405, overflow422 y motivos separados en auditoria |
| Ruff / pip check | Limpios, sin instalar/actualizar paquetes; un warning TestClient/httpx conocido en pytest, sin remediacion de dependencias implicita |
| Navegador sintetico | Grafo sin filas/motivo y guardado bloqueado; detalle fresco; desactivacion409 con mensaje seguro/request_id, motivo conservado y reenvio bloqueado. Capturas escritorio y360px CSS, modal sin desbordamiento; API totalmente interceptada, sin escrituras de negocio reales |

Validacion documental: enlaces/anclas locales, fences, JSON normativo, IDs y preservacion del contenido historico; `git diff --check` limpio y paths protegidos sin diff. El visor al150% requirio medir `innerWidth` para verificar360px CSS; excepcion temporal del certificado autofirmado solo en la pagina de prueba loopback, sin cambios a TLS/AUTH_ORIGIN/Secure. Pagina temporal cerrada, sin identidad ni rutas sinteticas persistentes. Los avisos HMR del visor no se presentan como prueba de E2E.

Origen no migrado ni recontado por este incremento: ultima observacion de head0004/18 tablas/cinco releases/bootstrap en seccion11, no cifras recertificadas. Pruebas aisladas/mocks no sustituyen aceptacion con sesion/configuracion del operador, permisos productivos, antivirus real ni homologacion integral. Se mantienen pendientes la aceptacion/configuracion F4/F5 y ensayo privado de almacenamiento/ClamAV/restore. F6 requiere autorizacion nueva/D03/D08; D06/D07 y vencimiento2026-12-24 no cambian.

## 14. Separacion de etapas y transiciones y secretos exactos 2026-11-25

Nueva correccion autorizada tras revision del titular en https://localhost:8443. **Sustituye el encaminamiento de altas de etapas a grafo atomico descrito en seccion13**, no reescribe sus resultados historicos. Se separan construccion administrativa y validez operativa sin semillas ni DDL. Continuan bloqueados F6-F7, aceptacion operativa F4/F5 y almacenamiento/ClamAV real pendientes; no cambia D01 ni excepciones D06/D07.

### Causas raiz y correcciones

1. **Acoplamiento UI:** Crear en Etapas llamaba a `workflow()` y abria WorkflowEditor con etapas/aristas juntas. Se retira esa derivacion: Editor recibe solo campos de StageCreate y envia POST `/workflow-stages`. Transiciones conserva su Editor y endpoint propios; el boton/editor atomico queda exclusivamente en Configuracion, tambien protegido ante llamada directa desde otro apartado.
2. **Validacion global durante construccion:** create_record/update_record exigian terminal y caminos en cada fila. Era imposible crear la inicial sola y despues completar el flujo sin el modal mezclado. La validacion administrativa permite incompletitud solo mientras no existen tareas/evaluaciones; conserva reglas locales, unicidad/FK y restricciones inicial/terminal. La inicial debe ser open/activa/sin motivo ni evidencia exigidos. Estado/operacion y POST `/workflow` siguen estrictos; tras uso tampoco se permite dejar un grafo invalido. No se habilita negocio con catalogo parcial.
3. **Secretos recortados por backend:** Command.str_strip_whitespace afectaba SecretStr. El caso real detecto que una password sin sus espacios extremos tambien autenticaba. ExactSecret envuelve el valor antes de esa normalizacion, reutilizado en alta/login/password actual/nueva/reset; conserva longitudes y tipos. Repetir el caso demuestra que solo autentica el secreto exacto. No se alteran hashes existentes, bootstrap, claves ni sesiones por una migracion.
4. **Validaciones administrativas tardias:** el checkbox podia enviar normal/custom inactivos y provocar409 evitable; ahora el formulario muestra la regla y bloquea ese envio, manteniendo proteccion del servidor. Ordenar un catalogo vacio abria un comando sin posiciones que no podia cumplir el DTO: boton deshabilitado y metodo sin apertura/POST en ese caso. Sin defaults activos ni filas automaticas.

### Revision por modulo

| Modulo | Resultado y cobertura |
| --- | --- |
| Departamentos | Conserva alta explicita, consulta fresca, PATCH/version/motivo y baja logica; pruebas de reapertura/cancelacion/guardado/conflicto y dependencia con usuario activo. Sin nueva regla de dominio |
| Usuarios | Departamento requerido L/C, nombre/correo normalizados y password intacta; alta/login/edicion/reset reales en UUID. Edicion ordinaria no presenta password ni motivo pasado; reset vacio y separado; revocacion/ultimo admin siguen protegidos |
| Etapas | Alta individual sin transiciones, inicial aislada201, sin requisitos inconsistentes. Grafo incompleto se guarda antes del uso y no habilita operaciones; lectura/edicion/baja mantienen versiones y retencion |
| Transiciones | Solo origen/destino/roles/activo/motivo; consulta etapas ya existentes. Aristas distintas, sin salida terminal, roles validos con admin en activa, extremos activos. Alta201, baja/reactivacion antes del uso, desfase409 y configuracion actualizada |
| Prioridades | Posicion numerica estricta0..2147483647, normal activa exigida local/servidor, sin reordenar vacio; se conservan detalle/PATCH/baja no protegida |
| Horizontes | Mismo rango entero; opciones exactas annual/semiannual/quarterly/monthly/custom, custom activa; sin precarga/renombrar codes y sin reordenar vacio |
| Parametros/configuracion | Inputs visibles y obligatorios: nombre1..160, IANA1..100 con America/Mexico_City oficial, evidencia1..10485760 y exportacion1..10000 enteros. Entrada DOM real y limites comprobados; cuatro claves explicitas, sin valores por defecto ni cambio de zona BD |

Motivo de cada comando permanece vacio al abrir edicion/reset/decision; datos vigentes se conservan e historia es readonly. 422 conserva formulario y permite correccion/reintento; 409 conserva contenido y exige descarte/recarga antes de reenviar. Mensajes sanitizados con request_id, sin SQL/passwords. No DELETE de dominio, cascadas ni modificacion de historia.

### Archivos del incremento

Produccion: [administracion UI](../src/app/admin/admin.page.ts), [DTO/secretos](../backend/app/schemas/identity.py), [validacion administrativa](../backend/app/services/administration.py). Pruebas: [vistas/componentes](../src/app/f4.spec.ts), [editor](../src/app/shared/editor.spec.ts), [identidad/API](../backend/tests/test_identity.py). Contratos/runbook: [SDD](01-spec-driven-development.md), [arquitectura](02-arquitectura.md), [backend](../backend/README.md) y esta adenda. Cambios del incremento anterior se preservan sin limpieza ajena.

### Verificaciones ejecutadas

| Gate / caso | Resultado |
| --- | --- |
| `bash scripts/init-dev.sh --check` | PG18.4 ya activo,127.0.0.1:5432/ocoteAppDatabase exacta; sin arranque/reset/migracion/seeds |
| `npm run build` | AOT correcto,392.40kB inicial/98.05kB transferencia estimada; admin lazy27.66kB. Sin dependencias ni budgets modificados |
| ChromeHeadless completo | **118/118 passed**;86 vistas/13 editor y19 restantes;15 casos mas que seccion13. Incluye siete reaperturas reales, primera inicial sin aristas, limites/campos, password exacta y422/409 |
| Backend completo sin opt-in | **65 passed/51 skipped**,5.41s; sin conexion PG |
| PostgreSQL opt-in test_identity/test_operations/test_execution | **71 passed**,126.73s; UUID aislados eliminados por fixtures. No se ejecutan siete casos F1 tecnicos sobre origen ni se atribuye suite completa PG |
| API incremental | Inicial/terminal individuales201 con transiciones vacias y workflow_valid=false; inicial con evidencia422, duplicado409 sin nuevas filas; arista201 completa el grafo; baja/reactivacion/version obsoleta cubiertas |
| Barrera operativa | Con cuatro settings/cinco horizontes/normal ya completos, arista desactivada deja complete/workflow_valid=false y alta de plan409 sin fila; reactivar permite201. Unit tests verifican estrictez despues de tareas y de evaluaciones |
| Secretos | Cinco campos DTO conservan espacios/tipos/limites y repr oculta; API alta/login/edicion/reset autentica valor exacto y rechaza variante recortada; auditoria sin passwords/hashes |
| Ruff / pip check | Correctos, sin instalar paquetes. Un warning TestClient/httpx conocido en pytest. Diagnostico Jasmine del proyecto inferido del editor no se confunde con fallo del runner real; no cambios a tsconfig ni dependencias |
| Navegador | API interceptada, identidad sintetica solo en memoria: POST de inicial individual con position numero0/sin aristas, lista recargada y nuevo modal completo/vacio; Transiciones solo sus propios campos. Capturas1440x1000/360x800 CSS, sin desbordamiento de pagina/modal, scroll contenido |

API de desarrollo reiniciada con autorizacion expresa del titular tras identificar listener Uvicorn exacto: PID anterior13884/nuevo14696, solo127.0.0.1:8000, comando del runbook sin access-log. Salud publica devuelve alive; config/claves/origen/Secure y datos se conservan. No se detuvo PostgreSQL ni se ejecutaron scripts de migracion/backup/restores sobre origen. Cambios de desarrollo no equivalen a release cliente homologada: guia05 seccion7 y aprobacion operativa siguen obligatorias para entrega.

Rutas de navegador retiradas e identidad sintetica descartada mediante navegacion completa a about:blank; excepcion temporal del certificado autofirmado desactivada. No se usaron credenciales del operador ni se crearon fixtures en origen. Lecturas publicas health/live no validan por si mismas la configuracion de negocio; pruebas API reales fueron exclusivamente aisladas. Avisos HMR del visor y limite de certificado local no implican alterar TLS ni validar todos los navegadores/AA.

Listo para probar con sesion propia en https://localhost:8443: Etapas -> crear inicial open/activa sin requisitos -> crear terminal/otras etapas -> Transiciones -> conectar caminos -> Configuracion -> verificar estado completo tras completar catalogos/ajustes explicitos. Si ya hay tareas/evaluaciones, cambios que rompan el grafo siguen rechazados y deben prepararse completos desde Configuracion. Hashes historicos ya recortados no son recuperables automaticamente; solo usar valor efectivo/restablecimiento autorizado. Cierre operativo F5/ClamAV real y aceptacion siguen pendientes; F6-F7 no autorizados.

## 15. Diagnostico de habilitacion operativa 2026-11-25

Revision full-stack F1-F5 autorizada, sin F6/F7. Checkout inicialmente limpio. `init-dev.sh --check` confirma PG18.4 ya activo y base exacta. Lectura consistente REPEATABLE READ/READ ONLY con `ocote_runtime` y lock compartido: head20261124_0004, cuatro claves presentes, cinco horizontes activos, normal activa y America/Mexico_City en BD. Cero planes/objetivos/tareas/subtareas/solicitudes al diagnosticar; no se captura identidad, nombre de organizacion ni secretos en esta evidencia.

**Causa exacta:** inicial open activa/sin requisitos, planeacion open activa y completo completed activa; unica arista inicial -> planeacion, activa/solo admin. Falta un camino desde inicial/planeacion hasta completo: evaluador devuelve409 WORKFLOW_HAS_NO_TERMINAL_PATH. No faltan parametros/horizontes/prioridad ni una terminal activa. El titular decide expresamente **no modificar configuracion desde el agente y completar el grafo por UI**; por tanto la operacion permanece cerrada hasta esa captura. No afirmar habilitacion ni aceptacion funcional real por las pruebas.

**Correccion:** configuration-status agrega workflow_error con el codigo del validador o null, sin alterar complete, validacion ni permisos. Administracion reutiliza mensajes seguros y ofrece enlaces a Etapas/Transiciones. Los comandos conservan problem+json/request_id y no saltan requisitos. Sin DDL, seeds, migraciones de origen, cambios de roles/secretos, dependencias, scripts, helpers historicos, lockfile ni ediciones de database/. Las cuatro revisiones aplicadas permanecen inmutables. Access/CSRF solo memoria, origen HTTPS y America/Mexico_City preservados.

### Verificaciones Y Limites

- Backend sin opt-in: **68 passed/51 skipped**. Backend completo con PostgreSQL autorizado: **119 passed**,143.93s; un warning conocido TestClient/httpx. Bases UUID aisladas eliminadas por fixtures; roles runtime/migrador separados. Incluye ensayos aislados existentes de migracion/no-op/restauracion; no es una release ni ensayo de backup/restore aplicado a origen.
- Regresion API: con parametros/horizontes/normal completos y arista desactivada, workflow_error especifico/alta409, application/problem+json, request_id UUID igual a cabecera y ningun plan creado. Reactivacion explicita/versionada permite estado completo y alta201. Unit tests cubren grafo valido, incompleto y sin camino.
- Angular completo: **140/140 ChromeHeadless**, incluido diagnostico que desaparece tras recarga valida; Kanban conserva tarjeta/motivo nuevo/version/referencia ante409/422/403 y bloquea reenvio409. Contratos existentes verifican periodos entre anios/horizontes, fechas originales, subtareas, solicitudes y rol/alcance. Build391.46kB inicial/97.81kB transferencia estimada, sin ampliar budgets. Ruff/pip check correctos.
- La suite existente verifica alta/consulta/edicion/activacion/cierre y contraccion de periodos; contencion objetivo/plan/departamento; originales e historia atomicos; avance/subtareas/carreras; aristas/evidencia/version; Kanban/Timeline por alcance; solicitudes pendientes/unicas/decision distinta del solicitante. No se agregaron funciones ni reglas F6/F7 ni se reescribieron modulos sin un defecto reproducible.
- Reinicio de API de desarrollo expresamente autorizado: listener14696 detenido, nuevo Uvicorn24612 en127.0.0.1:8000, comando del runbook sin access-log. Salud publica200/alive; configuration-status anonimo401 con request_id coherente. PostgreSQL no se reinicio. No homologacion de release cliente: protocolo guia05 seccion7 sigue obligatorio para entrega.
- Lectura final READ ONLY con runtime: misma head0004, tres etapas/una arista y cero planes/objetivos/tareas/subtareas/solicitudes; complete=false con workflow_error=WORKFLOW_HAS_NO_TERMINAL_PATH. Configuracion capturada preservada, sin atribuirse una habilitacion aun pendiente del titular.
- Limite visual de esta ejecucion: Angular HTTPS responde200 en8443, pero dos navegaciones de la pagina de prueba del visor integrado agotaron timeout antes de cargar el documento; no se obtuvieron capturas nuevas ni se afirma comprobacion visual/responsiva o E2E real actual. API interceptada solo en pagina de prueba, sin credenciales del operador; rutas retiradas, navegacion a about:blank y excepcion temporal del certificado autofirmado desactivada. No se reinicio Angular ni se cambio TLS/origen/Secure para sortearlo.

### Aceptacion Pendiente Del Titular

En https://localhost:8443, Transiciones -> completar el camino planeacion -> completo con los roles y motivo decididos -> Configuracion -> Recargar -> verificar complete=true. Si se eligieran otros caminos, todas las etapas activas igualmente deben alcanzar la unica terminal. No reinsertar catalogos, sobrescribir bootstrap ni desactivar reglas para pasar la puerta.

Despues: crear plan borrador con rango incluso cruzando anio -> objetivo con departamento y fechas contenidas -> activar plan -> crear tarea con responsable del departamento -> agregar/completar subtareas -> comprobar avance y comparar original/vigente en detalle/Kanban/Timeline. Editar/solicitar/decidir con motivos nuevos; probar dos sesiones para409 y solicitante distinto de aprobador. Gerente no mueve tareas; colaborador solo asignadas y sin planificacion/solicitudes administrativas. Esta aceptacion real no fue ejecutada por el agente ni se crearon fixtures en origen.

**Barrera independiente:** completo exige motivo y evidencia. Almacenamiento/ClamAV reales siguen pendientes segun runbook, por lo que su cierre permanece fail-closed; completar el grafo no constituye configuracion de antivirus ni autoriza omitir evidencia. F5 conserva cierre operativo pendiente y excepciones vigentes; F6/F7 no iniciados.

## 16. Paginacion de tablas y evidencia explicita (2026-11-25)

**Alcance:** mejora frontend F4/F5 autorizada, local/sintetica, sin backend nuevo. El titular reporta haber completado el grafo y estar conforme con Planes/Objetivos/Timeline salvo paginacion; este incremento no reconsulta ni modifica esa configuracion y no reescribe el diagnostico historico de la seccion 15. F5 sigue con cierre operativo pendiente; F6/F7 bloqueados.

### Cambios Y Decisiones

- Todas las tablas usan cinco filas iniciales y selector 5/10/20/50: recursos administrativos, planes, objetivos, tareas, solicitudes de fecha, subtareas y tabla de Timeline. [Pager/Pagination](../src/app/shared/pager.ts) comparte controles Material etiquetados, tooltips, anuncio de pagina y adaptacion movil. Primera/anterior/siguiente usan cursores del servidor y un historial local; cambiar tamano/filtros reinicia la pagina, conserva los filtros y no inventa totales. No se agregaron tablas, endpoints ni parametros de negocio.
- Las subtareas reemplazan la pagina visible en lugar de acumularla, sin mutar version/avance/tarea. Los catalogos para selectores, configuracion atomica y reordenamiento siguen cargandose completos con Api.all; el limite visual no recorta opciones ni items de comandos. Timeline mantiene grafico/tabla sobre la misma pagina. Historia y evidencia mantienen sus listas existentes.
- [Transiciones](../src/app/operations/transition.ts) selecciona evidencias ya adjuntas/verificadas de esa tarea, incluidas paginas posteriores. Si no existen, explica la causa y remite al detalle para adjuntar. Si uploads_configured=false, explica almacenamiento privado y/o ClamAV pendientes; no demuestra estado sanitario del scanner. El selector sigue obligatorio y Guardar permanece deshabilitado sin evidencia, incluso con motivo valido. No hay omision del requisito, carga desde ese selector ni configuracion tecnica inventada.
- **Avance por etapas evaluado y no implementado:** RN-03 sigue siendo autoridad: sin subtareas 0/100 segun cierre; con subtareas completadas/total. Tener todas completas produce 100% con cierre explicito pendiente cuando corresponda. La posicion visual no representa trabajo en grafos con saltos, ramas o retornos; no se mezcla con avance ni puntualidad ni se introduce un porcentaje alternativo silencioso. Cambiar esa metrica requiere decision normativa expresa.
- **Kanban preservado:** carriles, arrastre/boton, limite25, grafo, roles/alcance y validaciones de destino sin cambios. No se exige minimo cinco etapas: inicial abierta y terminal completada distintas, con caminos validos, son el minimo estructural de dos; no una configuracion creada por el agente. Sin reglas adicionales para Planes/Objetivos/Timeline.

### Archivos Y Verificaciones

- Implementacion: [admin.page.ts](../src/app/admin/admin.page.ts), [planning.page.ts](../src/app/operations/planning.page.ts), [tasks.page.ts](../src/app/operations/tasks.page.ts), [requests.page.ts](../src/app/operations/requests.page.ts), [execution.page.ts](../src/app/operations/execution.page.ts), [task-detail.page.ts](../src/app/operations/task-detail.page.ts), [transition.ts](../src/app/operations/transition.ts) y [pager.ts](../src/app/shared/pager.ts). Pruebas: [f4.spec.ts](../src/app/f4.spec.ts) y [pager.spec.ts](../src/app/shared/pager.spec.ts). Contratos/arquitectura y entrada actualizados en SDD, arquitectura y README.
- **154/154 ChromeHeadless** en suite completa, de ellos 115 focalizados de vistas/paginador. Casos nuevos: cinco filas iniciales; limites 5/10/20/50 enviados; siguiente/anterior y reinicio tras cambiar tamano conservando filtros; subtareas sin acumulacion ni cambio de tarea/version/avance; evidencia vacia con y sin configuracion; evidencia disponible en paginas posteriores. Los controles compartidos verifican etiquetas, eventos y bloqueo durante carga.
- **npm run build correcto**, AOT, inicial391.46kB/97.81kB transferencia estimada; execution639.73kB, sin ampliar budgets, dependencias ni lockfile. Diagnosticos de editor del paginador/pruebas/transicion/detalle sin errores. No se requieren pruebas backend nuevas porque no cambia ese codigo ni su contrato.
- **bash scripts/init-dev.sh --check correcto:** PostgreSQL18.4/ocoteAppDatabase ya activos. Sin arranque, reinicio, migracion, seeds, cambios de datos ni lectura de configuracion de negocio durante este incremento; se deja activo. API y Angular existentes tampoco se reiniciaron. Head/revisiones aplicadas, scripts, legacy, database/ y bootstrap sin ediciones.
- **Revision sintetica ChromeHeadless a 1280x900 y 360x900 CSS:** siete familias de tablas en cada tamano (14 recorridos), cinco filas iniciales, opciones 5/10/20/50 y siguiente/cambio a diez con vuelta a pagina1. Sin desbordamiento horizontal del documento; tablas anchas conservan scroll interno. Capturas del paginador y modal de evidencia revisadas en ambos tamanos, sin solapamientos; modal movil dentro del viewport (x6.91..338.09). Motivo valido mas evidencia vacia mantiene Guardar deshabilitado y no genera comandos, incluso al enviar el formulario. Sin excepciones de aplicacion en los recorridos exitosos.
- Limite de herramientas: el visor integrado agoto timeout antes de cargar; se limpio su pagina/rutas y excepcion temporal de certificado. Alternativa verificada con ChromeHeadless/perfil temporal separado y API completamente interceptada, sin identidad del operador ni escrituras de dominio; navegador/perfil eliminados. Dos intentos del script de comprobacion necesitaron corregir respuestas sinteticas/selector DOM, no la aplicacion; el recorrido final paso. Capturas generadas fuera del checkout, no son datos ni fixtures de origen.
- Documentacion: cuatro archivos verificados, 144 enlaces/anclas locales y ocho bloques JSON correctos, fences balanceados e IDs RF/RN/D/F preservados; git diff --check correcto. Estas comprobaciones estructurales no sustituyen ejecucion, render ni aceptacion funcional.
- America/Mexico_City, tokens OCOTE, acceso/CSRF solo memoria, cookies Secure, Web Locks, versiones/409, autorizacion servidor, formulas, originales y requisitos de cierre preservados. La revision visual/sintetica no homologa accesibilidad completa, antivirus real, E2E operativo ni produccion; no remedia D07 ni habilita F6/F7.

### Aceptacion Local Pendiente

En https://localhost:8443, con la sesion/alcance propios: abrir cada tabla, comprobar cinco filas iniciales y elegir 10/20/50/5; navegar siguiente/anterior/primera con suficientes registros y verificar reinicio tras cambiar tamano/filtros. En detalle, paginar subtareas sin cambiar el avance. En Timeline, comprobar correspondencia entre tabla y grafico de la pagina; Kanban debe conservar su operacion actual.

Probar Cambiar etapa hacia un destino que exija evidencia: sin adjuntos debe explicar la ausencia y mantener el envio bloqueado; sin configuracion tecnica, tambien debe explicar almacenamiento/ClamAV. Tras configuracion real autorizada, adjuntar archivo limpio desde detalle, recargar y seleccionarlo en la transicion, preservando motivo/version y requisitos de cierre. Esa aceptacion y ensayo real D05 siguen pendientes del operador; no desactivar evidencia ni alterar el grafo para sortearlos.

## 17. Analitica evaluaciones y exports F6 local (2026-11-25)

### Autorizacion Y Limites

El titular ratifica D03/D08/RN-06 sin cambios: evaluacion departamental, pesos iguales, sin ranking/nota compuesta, cohorte por original_due_date inclusiva, calendario manual y admin/gerente responsable de cada operacion. Ejemplo4 tareas/2 cerradas/1 originalmente puntual:50% cierre/25% puntualidad base. Corte real al generar, no reconstruccion al fin de periodo. Finalizacion recalcula y sella, exige periodo concluido, conclusion10..4000 y cohorte no vacia. Lider lee solo sus finales departamentales; colaborador sin analitica/evaluaciones/exports.

Autoriza F6 local/sintetico pese a cierre operativo F5 pendiente y extiende expresamente D06 sin suplente y las dos excepciones D07 (soporte Angular18/61 alertas npm), hasta2026-12-24, mismo responsable LUIS ANGEL VALLEJO - DESARROLLADOR; sin renovacion automatica. Solo loopback/sintetico, no red compartida, entradas no confiables, datos reales, produccion/nube. F7 y almacenamiento/ClamAV reales pospuestos/bloqueados; cargas siguen fail-closed. No se configura ni sobrescribe bootstrap/custodia/grafo/identidad.

### Implementacion

- Backend: [calculos/alcance](../backend/app/services/analytics.py), [lifecycle/fotos](../backend/app/services/evaluations.py), [exports](../backend/app/services/exports.py), [rutas](../backend/app/routers/analytics.py), [DTO](../backend/app/schemas/analytics.py), [modelos](../backend/app/models/evaluations.py), [revision0005](../backend/alembic/versions/20261125_0005_evaluations.py) y [tests](../backend/tests/test_analytics.py). Integracion en [main](../backend/app/main.py), [unidad de trabajo](../backend/app/services/identity.py), [plan/contencion](../backend/app/services/operations.py), [permisos auth](../backend/app/routers/auth.py). Pruebas existentes ajustadas en [foundation](../backend/tests/test_foundation.py), [operations](../backend/tests/test_operations.py) y [postgres](../backend/tests/test_postgres.py); el ensayo historico F5 apunta a0004, no head flotante.
- Analitica: alcance antes de agregar/limitar, denominador completo, progreso RN-03 exacto, dos puntualidades, retrasos/reprogramaciones y cambios de fecha incluso al volver al original. Meses YYYY-MM, vacios null, cruces/leap day; maximos10000 tareas/1200 meses,413 sin truncar. Cada peticion tiene su snapshot REPEATABLE READ; no unica transaccion distribuida entre endpoints.
- Draft con foto persistida, recalc explicito, finalize con expected_version/summary, exclusion GiST de periodos solapados e inmutabilidad final/items reforzada por triggers/privilegios. Contraccion de plan protege periodos de evaluaciones. Sin seeds, defaults de periodos/evaluadores, DELETE ni reabrir finales.
- Exports JSON/CSV autenticados/materializados, export_max_rows+1/16MiB/limiter10-cuenta/50-cliente por minuto/proceso. CSV neutraliza formulas tras blancos/controles, conserva quoting/contexto/conclusion/metrics congelados. Auditoria separada requested/prepared/failed/denied sin contenido; fallo de auditoria bloquea respuesta. Prepared no certifica recepcion; transaccion cerrada antes del envio, fallo de transporte independiente.
- Angular: [analitica](../src/app/operations/analytics.page.ts), [evaluaciones](../src/app/operations/evaluations.page.ts), [descarga](../src/app/shared/export-menu.ts), [API Blob](../src/app/core/api.ts), [mensajes](../src/app/core/problem.ts), [presentacion](../src/app/shared/presentation.ts), [rutas](../src/app/app.routes.ts), [shell](../src/app/shell.ts) y [tests F6](../src/app/f6.spec.ts)/[navegacion F4](../src/app/f4.spec.ts). ECharts lazy y tokens existentes, filtros, cortes/denominador, tablas equivalentes5/10/20/50, detalle de foto/capturados y acciones solo por permiso. Sesion/locks/Secure/Origin intactos, autoridad de servidor y409 conserva/bloquea hasta descarte/recarga.

### Release Y Datos Preservados

[Herramienta F6](../backend/tools/f6_local.py) separada, invocacion explicita via PYTHONPATH=backend/python -m tools.f6_local; artefactos externos privados en LOCALAPPDATA/OCOTE/f6-evidence/f6-0b6b137b-42f0-4ac7-91d8-3fdc743d4ab2. No edita scripts/helpers F1-F3 ni revisiones0001..0004. Precheck PG correcto, API conocida detenida sin tocar PG/Angular. Preflight inicial rechazo falta de CREATE, sin maintenance/DDL; el titular autorizo despues concesion temporal solo al migrador en esta base para btree_gist. Grant/revoke registrados19:08:39.770..19:08:40.575 UTC; revocado/comprobado antes de backups posteriores. Migracion como migrador, nunca superusuario runtime. No DDL manual de tablas.

Intento0b6b137b-42f0-4ac7-91d8-3fdc743d4ab2, request_id6a0622f6-7c67-4bdd-844f-e285221df13b, release0.6.0/F6_LOCAL_VERIFIED/version2/succeeded,28.872s. Head20261125_0005,20 tablas contando Alembic/19 de dominio y seis releases terminales (cinco succeeded/una failed historica). Hash artefacto0d64f8f1e4a14af1286ead2049d02a737a6795f857677173b92fd5e5dab0e667; manifest928851ad158169e4f217521c06e0f20ce3f397b8af4cdc2f08163d1d5284e609. Instantanea tecnica sin firma, no hash del checkout final ni paquete cliente.

| Backup | Bytes | SHA-256 | Restore aislado |
| --- | --- | --- | --- |
| before | 106547 | e22bfdde7988c1910c54eb4d5051361ea1d4e654c1d7ecce07b0fc050882f093 | 2.174s |
| after | 120765 | 23de3a604cdb0b31c0aef8d4766a000f9db833dd8f6f2684b2ecbc2ade3082bc | 2.207s |
| recorded | 120988 | 7cebb23fc92ba99008864bcffb3172cd0582ecd16a2073130deb0f29d00934e5 | 1.876s |
| terminal | 120976 | 34108e21142f5047c3ce8aca7f745afea25862c6fb8b9b1ce5916980c6293ab5 | 1.725s |

Cinco restores contando ensayo adicional before->upgrade/no-op antes de origen; upgrade/no-op origen con snapshots identicos y grants runtime minimos. before/after/recorded/terminal comparan estructura/filas y contratos de ledger; --no-acl no homologa recuperacion de grants cliente. Catalogo/OIDs legacy ocote, datos/configuracion/bootstrap y cinco releases previas preservados. Inventario final de solo lectura:1 plan/1 objetivo/2 tareas/3 subtareas/9 historias previas,0 solicitudes/evidencias/evaluaciones/items; esos datos operativos existian antes y no fueron sembrados por F6. Dumps sin cifrado/copia off-host; no hay archivos operativos para ensayar BD+evidencias reales; no satisface recuperacion de host/RPO/RTO productivos.

### Verificaciones Y Aceptacion

- Backend F6:30 passed PG aislado. Incluye4/2/1, vacios, precision, meses/leap day, formulas CSV/metadata, alcances negativos, foto tras cambios de catalogos/tareas, inmutabilidad SQL, vacio/futuro/solape/plan contraido/version409, limites/auditoria fallida/transporte y carreras create/recalculate/finalize. Escritura concurrente confirmada entre dos lecturas del reporte no cambia snapshot. No SQLite ni fixtures persistidas en origen.
- Regresion backend global final:149 passed con PostgreSQL en288.51s; sin opt-in85 passed/64 skipped en17.32s. Expectativa historica0004 corregida a0005 en prueba vigente de roles; CREATE de runtime/migrador revocado comprobado. Ruff format/check y pip check correctos; unico warning conocido TestClient/httpx, sin actualizar dependencias. Precheck init-dev confirmo cluster/base ya activos, sin migraciones/seeds ni cambios de configuracion.
- Angular164/164 ChromeHeadless (10 F6), build AOT de produccion correcto en39.095s:392.86kB iniciales/98.85kB transferencia estimada, sin cambiar budgets/dependencias/lock. [Comprobador visual](../backend/tools/f6_visual.cjs): ChromeHeadless/CDP, perfil desechable y API interceptada;1280x900/360x900 CSS,68 solicitudes sinteticas, tablas5 filas, dos canvas no vacios por viewport (59291/21741 y21415/9965 pixeles), finales sin mutaciones, vacio bloqueado y409 conserva conclusion/bloquea reenvio. Sin overflow horizontal de documento; tablas con scroll interno; dialogo640px/331.19px. Capturas revisadas fuera del checkout en temporal ocote-f6-visual-h3d4xu. Un intento necesito sincronizacion CDP y otro agoto condicion DOM; repeticion instrumentada paso sin cambiar la aplicacion. No E2E autenticado, capacidad ni accesibilidad AA homologados. Visor integrado no disponible; su timeout no es evidencia funcional.
- Smoke real tras reiniciar API F6 en127.0.0.1:8000:live200,ready200/403 sin token, maintenance ausente, CREATE temporal=false. Angular existente conserva8443; PG18.4 permanece activo sin reinicio. Sin archivos/manual edits bajo database/, cambios a scripts/helpers historicos/package-lock ni commits/ramas.
- Documentacion sincronizada en README, runbook, SDD, arquitectura, entorno/entrega y guias de agentes: nueve archivos,279 enlaces/anclas locales, nueve JSON y fences/IDs RF/RN/D/F correctos. git diff --check correcto e indice sin cambios; rutas protegidas sin diff. Validacion estructural no demuestra comportamiento, render, aceptacion ni homologacion operativa/productiva.

Aceptacion del operador pendiente en https://localhost:8443: A/G revisan filtros/denominadores, crean un periodo deliberado, recalculan/comparan cortes, finalizan solo periodo concluido con conclusion y contrastan JSON/CSV con la foto; L solo departamento/finales; C no recibe modulos ni datos. No inventar calendario/evaluador ni generar pruebas en origen para aparentar aceptacion. Cierre operativo F5 y configuracion/ClamAV reales siguen pospuestos; F7 requiere autorizacion nueva y sus puertas. No renovar excepciones automaticamente ni anunciar seguridad productiva por pasar tests/build.

## 18. Evolucion empresarial documental

Solicitud del titular2026-11-25: ampliar exclusivamente normativa/arquitectura/datos/formularios/entrega. No implementacion ni autorizacion F7+. Punto de partida instalado confirmado documentalmente por acta17: head20261125_0005,20 tablas contando Alembic y seis releases terminales; no nueva consulta de BD en esta tarea. Evidencias149 backend/164 Angular/build pertenecen al cierre F6, no a estas capacidades futuras. No iniciar/consultar/reiniciar servicios, migrar, configurar antivirus ni probar proveedores por esta ampliacion.

### Alcance y trazabilidad nueva

- [SDD empresarial](01-spec-driven-development.md#8-evolucion-empresarial-propuesta):20 RF nuevos RF-16..35,13 RN nuevas RN-08..20,8 decisiones propuestas D09..16, matriz ampliada y contratos de formularios/UI/API. Dominio canonico y cuatro roles sin cambios; no rankings ni reemplazo del calendario manual RN-06.
- [Arquitectura empresarial](02-arquitectura.md#8-arquitectura-empresarial-proyectada):47 tablas nuevas proyectadas, claves/indices/triggers/grants, boveda, actores tecnicos, outbox/leases y transicion aditiva. No tablas creadas ni compromiso de un numero final de esquema antes de revisar cada release.
- [Entrega futura](05-paquetizacion-instalacion-y-actualizaciones.md#9-entrega-empresarial-sin-archivos-operativos) y [portabilidad](04-entorno-y-portabilidad.md#9-portabilidad-empresarial-proyectada): wizard seguro, PG local/externo, bootstrap sellado, configuracion BD, rotacion/restore y actualizacion incremental con protocolo seccion7 de guia05.
- README/runbook/AGENTS/adaptador distinguen instalado/proyectado. Las cinco revisiones0001..0005 y herramientas backend/tools/f1_local.py..f6_local.py/f6_visual.cjs son intocables; tampoco codigo backend/src, scripts, lock ni database. La propuesta no elimina .env existentes ni cambia AUTH_ORIGIN o credenciales.

### Orden recomendado y puertas

Dependencias ejecutables propuestas exclusivamente lineales: F7 depende de F6 y cierre de gates operativos indicados; F8 de F7; F9 de F8; F10 de F9; F11 de F10; F12 de F11. Referencias de diseno a tablas/contratos posteriores no crean prerrequisitos circulares ni autorizan adelantarlos. Cada fase requiere orden de trabajo expresa con alcance/entorno/destinos de pruebas y custodia, revision SDD y evidencia propia; ningun estado actual se cambia a iniciado por esta tabla.

| Fase | Entrega propuesta y RF principales | Puerta de entrada | Definition of Done discriminante |
| --- | --- | --- | --- |
| F7 | Endurecimiento/instalador/wizard, PG local o externo, bootstrap/boveda/configuracion minima, backup/upgrade in-house. RF-16..18, base RF-19/20/35 | Autorizacion nueva; aceptar operacion F4-F6/cierre F5 con storage/ClamAV reales; resolver D07 soporte y61 alertas con cambio autorizado/pruebas, suplente independiente D06 y custodia/alcance productivo; aprobar D09/D10/D14/D16 | Instalar limpio y actualizar copia desde0005, segundo upgrade no-op; no datos demo. Wizard prueba roles/TLS/CA/btree_gist y se cierra; runtime no DDL ni credencial migrador. Restaurar BD+archivos+claves en host/destino aislado, contingencias mantienen maintenance. Paquete firmado/SBOM/SO homologado, UI minima para tecnicos existentes sin .env; entrega local y gestionada cada una con evidencia, no soporte nube supuesto |
| F8 | Centro de configuracion/flags/seguridad/branding, boveda UI, storage S3/Azure/MinIO/R2 y modos scanner. RF-17..20 | F7 aceptada; D09..D11/D13; proveedores/egress/retencion y audiencia aprobados | Configurar/probar/activar sin reinicio manual; revision consistente multiproceso y409. GET/logs nunca exponen secreto; prueba de tag invalido/rotacion/restore. Desactivar modulo/proveedor no elude cierre ni rompe evidencia; anti fail-closed real, branding1280/360/teclado/contraste. Compatibilidad certificada solo para adaptadores ensayados |
| F9 | Calendario laboral, dependencias/impedimentos, plantillas/recurrencia, campos/tags, comentarios/busqueda/vistas. RF-27..31/33 | F8 aceptada; D13/D15; reglas de bloqueo, delegacion worker y clasificacion de comentarios aprobadas | DAG concurrente sin ciclos; intervalos de bloqueo sin doble conteo; generar ocurrencia exactamente una vez en dominio aun con reintento. service_principals/actor tecnico y outbox basicos disponibles sin API externa; no atribucion humana ficticia. Campos requeridos y permisos no invalidan fotos; festivos/flags no cambian RN-02/RN-03/RN-06. Busqueda/snippets/facetas y menciones sin fuga por rol |
| F10 | Bandeja/reglas, SMTP/HTTP, Teams/Slack/Telegram/Discord/Google Chat y feeds iCal. RF-21/22/26 parcial/32 | F9 aceptada; D11/D15, egress/proveedores/audiencias/consentimiento y cuotas aprobados | Outbox+dominio atomicos, lease/fencing/dedup y reintentos probados; revocar alcance antes de envio bloquea datos. Quiet hours/DST y calendario laboral correctos sin duplicar alerta. Pruebas rotuladas aisladas; feed revocable/expirable y C solo asignadas. Aceptacion proveedor no se presenta como lectura humana |
| F11 | API scopes/webhooks, DevOps, SSO OIDC/SAML/LDAP-AD y sync calendario CalDAV/Outlook/Google. RF-23..26 | F10 aceptada; D11/D12/D15, IdP/protocolos/mapeos/JIT/egress y endpoints externos autorizados | Hash key/one-time/revocacion/CIDR, scopes positivos/negativos por comando. HMAC/replay/SSRF/rebinding/dedup, dead-letter/replay y limites. SSO sin auto-admin/email takeover, ultimo admin local/emergencia y revocacion probados; misma seguridad de sesion. Commits/calendarios no cambian fechas/avance; cada proveedor homologado por separado |
| F12 | CSV/XLSX dry-run/commit, XLSX/PDF ejecutivos y consola ampliada salud/backup/retencion/update. RF-34/35 | F11 aceptada; D14, librerias de parseo/render y agente/plataformas/retencion aprobados | Dry-run sin dominio y commit atomico/idempotente incluso tras concurrencia/corte; ZIP bombs/macros/formulas rechazadas. Export final reproduce foto y limites/alcance/auditoria F6. Agente sin shell ni restore origen, backups cifrados con restore aislado, fallos dejan maintenance; no purga historica ni SLA inferido |

La aceptacion real de almacenamiento/ClamAV pendiente F5 es puerta operativa, no desarrollo anticipado de S3/centro F8: en F7 solo se configura por UI el adaptador privado/ClamAV existente y se migra su configuracion tecnica al registro BD. Conectores externos nuevos permanecen ausentes/deshabilitados hasta su fase. Si esas puertas no pueden cumplirse, F7 sigue bloqueada; no se presume otra excepcion ni se extiende2026-12-24.

### DoD comun empresarial

Antes de cada implementacion: aprobar requisitos/rangos/DTO/OpenAPI, threat model y clasificacion/retencion; elegir librerias mantenidas y actualizar lock solo con permiso. Revisiones nuevas expand/backfill/validate/contract desde head admitida, pruebas PostgreSQL reales aisladas, no tocar0001..0005 ni helpers de evidencia historica. No cambiar formulas para una demo ni seeds de usuario/calendario/canales/plantillas/catalogos por conveniencia.

Cada entrega adjunta pruebas por cuatro roles y scopes de servicio cuando apliquen, rutas directas y colecciones/agregados/errores; concurrencia409 conserva valores; audit/task_history append-only y fotos/fechas originales preservadas. UI verifica1280/360px CSS, zoom200%, teclado/foco/lector, estados sin configurar/vacio/error/prueba/conflicto, secretos write-only, tablas5/10/20/50 y tokens OCOTE. Validacion SQL incluye triggers/grants/RLS solo si expresamente implementada, no SQLite como PG. Requiere build/regresion focal/global segun riesgo, revision seguridad y aceptacion operativa registrada; no homologacion por screenshots o mocks.

Una fase no cambia exposicion local a red compartida/productiva por implicacion. Los presupuestos de conexiones/colas/volumen/latencia/RPO/RTO se acuerdan y miden en entorno autorizado; no prometer capacidad empresarial por el inventario de funciones. Diferenciacion propuesta: trazabilidad de compromiso original, gobernanza departamental sin ranking, operacion soberana y configuracion segura por UI; no estudio comparativo de mercado ni paridad verificada.

### Evidencia de esta ampliacion documental

Comprobacion estructural: nueve Markdown actualizados,312 enlaces locales/anclas resueltos, nueve JSON validos y fences balanceados; definiciones nuevas RF-16..35/RN-08..20/D09..16 unicas/consecutivas y47 tablas proyectadas sin duplicados. IDs RF-01..15/RN-01..07/D01..08/F0..F7 preservados; filas RF/D heredadas y seccion canonica RN-01..07 comparadas contra Git sin cambios. git diff --check correcto. Huella SHA-256 conjunta de94 archivos tecnicos protegidos (excluye backend/README.md documental permitido):4514b86fd468541f87b334727c9cd6ffb7f98c35d5472900d459cecb68e6c777, identica antes/despues. Sin backend, frontend, init-dev, SQL ni integraciones ejecutados. Estas comprobaciones no prueban diagramas renderizados, implementacion/seguridad runtime, proveedor, migracion o aceptacion de cliente; resultados F6 anteriores no se presentan como reejecutados.

## 19. F7 autorizada: ejecucion en curso

**Ajuste de alcance vigente del titular (2026-11-25):** esta sesion cerrara exclusivamente revision0006, boveda AES-256-GCM, configuracion BD de almacenamiento privado local/ClamAV fail-closed, protocolo de respaldo/restore aislado/preservacion, pruebas PostgreSQL reales, reinicio/smoke de API y documentacion. Setup Wizard, instalador y empaquetador/firma/SBOM in-house pasan al cierre final del proyecto despues de branding y F8..F12; no son gate de cierre de este incremento reducido ni funciones implementadas. No se autoriza iniciar F8..F12 por este cambio. Las exigencias de custodia/aceptacion y homologacion del cliente siguen siendo puertas de la entrega final. No modificar revisiones0001..0005, helpers F1-F6, scripts, lock Python ni datos previos.

Entrada privada: tarea visible VS Code **OCOTE F7: credencial administrativa**, con foco/terminal dedicada, ejecuta tools.f7_local authorize. El relevo administrativo entre esa tarea y las herramientas locales usa DPAPI del usuario Windows, ACL privada, fuera del checkout, caducidad60min, sin overwrite ni secreto en argumentos/logs/chat. No es MASTER_ENCRYPTION_KEY, no se distribuye al runtime/cliente ni conecta/migra por capturarlo. Revocar al terminar; una autorizacion ausente/expirada bloquea ensayos y nunca habilita fallback administrativo. La herramienta F7 todavia no implementa apply: registrar autorizacion no equivale a0006 ni a protocolo de release aprobado.

El titular autoriza expresamente F7 el2026-11-25: endurecimiento D07, revision nueva0006, boveda AES-256-GCM, bootstrap sellado, wizard aislado, configuracion BD/UI de almacenamiento privado local y ClamAV existentes, salud y paquete in-house. F8..F12 permanecen bloqueadas. Esta autorizacion sustituye los bloqueos de inicio anteriores, no sus evidencias historicas ni las puertas de liberacion al cliente. No se declara implementacion, migracion o cierre hasta registrar pruebas reales.

D07: se autoriza modificar package.json/package-lock.json y configuracion/codigo Angular estrictamente necesarios para una linea con soporte oficial y sus bibliotecas compatibles; no npm audit fix --force. backend/requirements.lock permanece inmutable; cryptography50.0.2/AES-256-GCM ya verificado con datos sinteticos en memoria. Preflight npm:61 alertas (2 criticas/19 altas/33 moderadas/7 bajas); no son excepciones renovadas ni resultado posterior de remediacion.

D06: LUIS ANGEL VALLEJO - DESARROLLADOR trabaja como autor unico de software en desarrollo local/generacion de artefactos, sin socio ni segundo operador interno inventado. Esa modalidad no bloquea desarrollo/ensayos locales autorizados; no representa custodia operativa de un cliente. Cada instancia cliente debera registrar en BD operador titular y suplente independiente, con nombres/contactos distintos, y acreditar su capacitacion/recuperacion antes de marcar entrega operativa completa. Consola y checklist distinguiran ingenieria del producto, custodia incompleta y homologacion del servidor final. No se precargan custodios ni se fabrican aceptaciones.

Estado inicial: checkout limpio, F6 segun acta17/head20261125_0005; no consulta de BD por el preflight D07. Revisiones0001..0005, tools/f1_local.py..f6_local.py/f6_visual.cjs, scripts y datos previos protegidos. Pruebas y estado de ejecucion pendientes de registrar en esta seccion.

### Avance tecnico verificado, no cierre F7

Alcance ratificado en la continuacion: incluye explicitamente custodia/salud BD/API/Angular junto con boveda y proveedores locales; se mantienen wizard y empaquetado para cierre posterior a F8..F12, sin autorizar estas fases. Antes de aplicar al origen:0006 aditiva ensayada dos veces/no-op/grants sin seeds;28 pruebas F7 (27 aprobadas antes de ampliar reescaneo, las dos afectadas por esa ampliacion aprobadas); backup/restore UUID con secreto sintetico cifrado y copia DPAPI descifrada; Angular170/170 globales y7 focales posteriores con render real, build413.89kB y visual Playwright1280/360 CSS aprobados. PG0:105/72 omitidas antes de ampliar una prueba PG. PG1 global previo:175 aprobadas y dos fallos identificados: test historico F6 corregido/fijado a0005 y aprobado; ready del origen aun0005 debe fallar hasta release. Se repetiran suites finales tras aplicar. Ruff/pip limpios; origen consultado sin mutar:0005,20 tablas,seis releases, API activa y tres conexiones runtime idle. Parada/release/reinicio pendientes, no se declara cierre por estos prechecks.

- Actualizacion oficial18->19->20->21 sin force/commits; versiones resueltas Angular21.2.26, CLI/build21.2.31, Material/CDK21.2.14, ngx-echarts21.0.0, TypeScript5.9.3 y zone.js0.15.1, Node22.21.1/npm10.9.4 sin cambiar. Migraciones intermedias20 completadas explicitamente tras interrupcion de instalacion; todas las obligatorias21 terminadas. Ajustes locales: await de Web Locks sin fallback, tokens Sass publicos de botones por variante/radios8px. Presupuestos originales intactos.
- npm run build aprobado: inicial412.89kB/transferencia estimada102.56kB;164/164 ChromeHeadless158 aprobadas. npm ls --all sin problemas. npm audit:0 criticas/0 altas/21 moderadas/0 bajas; soporte anterior18 sustituido por linea21 LTS, no soporte perpetuo ni riesgo residual aceptado por inferencia. Las21 moderadas siguen pendientes de evaluacion antes de liberar al cliente.
- Nuevo nucleo app/core/vault.py y tests/test_f7.py: envoltura AES-256-GCM por instancia/proposito/version, nonces CSPRNG, autenticacion owner/UUID, rotacion conservando material anterior, repr sin ciphertext, DPAPI Windows con entropia de instancia/ACL y escritura O_EXCL sin overwrite.15 pruebas focales aprobadas, incluidas manipulacion/instancia incorrecta/sello inexistente/DPAPI real. No prueba aun la futura persistencia/rotacion transaccional BD, endpoints write-only ni backup/restore de boveda real.
- Suite backend OCOTE_RUN_PG_TESTS=0:100 passed/64 skipped/una advertencia conocida Starlette-httpx; Ruff y pip check limpios. No se modifica requirements.lock para eliminar el aviso. No se ejecuto OCOTE_RUN_PG_TESTS=1 sin credencial administrativa.
- init-dev.sh --check:PG18.4 ya activo/base exacta, sin arranque ni migraciones/seeds. No consulta de filas de negocio, generacion de raiz persistente ni alteracion de claves/origen/cookies/bootstrap. Las claves DPAPI de pruebas solo existieron en temporales sinteticos; no son la raiz de instancia ni material de recuperacion de cliente.

Bloqueo de ejecucion PG: PGPASSWORD administrativa no esta exportada en el terminal del agente. Se requiere entrada privada por el operador para crear/eliminar exclusivamente destinos UUID aprobados y verificar backup/restore antes de0006; no se solicita por chat ni se infiere credencial a partir del runtime. Faltan0006/modelos/persistencia/DTO/API/UI de custodia e integraciones, wizard/instalador separado, f7_local, empaquetador/firma/SBOM, suites PG, revision visual1280/360, migracion principal/smoke y arranque final. F7 no esta entregada; F8..F12 permanecen bloqueadas. Siguiente paso: habilitar credencial local temporal y continuar el primer ensayo aislado, no ejecutar helpers apply historicos ni migrar origen sin el protocolo nuevo.

### Cierre del incremento F7 acotado

Autorizacion efectiva del titular:0006, boveda AES-256-GCM, proveedores privados locales/ClamAV BD verificados/fail-closed, custodia operativa cliente titular/suplente, salud administrativa, /api/v1 y Angular, suites completas PG0/PG1/ChromeHeadless/build/Ruff/pip/visual1280 y360 CSS, release/reinicio API y nueve documentos. Setup Wizard e instalador/empaquetador/firma/SBOM in-house diferidos expresamente al cierre final despues de branding/F8..F12; esas fases siguen bloqueadas hasta autorizacion propia. No se cierra homologacion/entrega operativa cliente ni proyecto completo.

**Implementacion:** [0006](../backend/alembic/versions/20261125_0006_vault.py) aditiva/sin seeds con seis tablas: deployment_instances, configuration_revisions, secret_key_versions, encrypted_secrets, integration_configs e integration_health_checks. Boveda AES-256-GCM con DEK por proposito/epoch, AAD por instancia-owner-proposito-version, nonces CSPRNG/unicos, tags de biblioteca incluidos en ciphertext, historial append-only y rotacion DEK transaccional acotada100/413. GET solo metadatos y ningun decrypt web. Raiz256 DPAPI del usuario/UUID fuera del checkout, no regenerable al arrancar; JWT/CSRF/health/credenciales SQL anteriores preservados, no migrados/rotados por registrar secretos en boveda.

Custodia cliente con nombres/contactos nullable/distintos normalizados, expected_version/motivo/auditoria, sin datos ficticios ni homologacion por llenar contactos. Proveedores JSON tipados local_storage/clamav solo loopback; guardar invalida prueba/activacion, test versionado con sonda UUID propia y comprobacion limpio/EICAR/frescura, activacion separada exige prueba<=15min de config_revision. Fallo queda inactivo y persistido. Evidencias consume solo BD activa/verificada, sin fallback EVIDENCE_*, revalida ACL/firma/escanea cada carga y conserva503 ante fallo; cambiar raiz con objetos requiere migracion aprobada. API /api/v1/admin y consola standalone /administracion/infraestructura solo admin;403 por API directa G/L/C y409 sin reenvio hasta descarte/recarga.

**Release aplicada:** intento7db5ca6c-be1c-4f38-a10d-11007bd8ca2c, request_id d979d8ac-0231-448f-ac8a-f332058aa3d1,2026-11-25T22:41:48Z..22:41:59Z. Fuente20261125_0005, destino20261125_0006. [Herramientas nuevas](../backend/tools/f7_local.py)/[protocolo F7](../backend/tools/f7_release.py), sin tocar revisiones/helpers/scripts/lock Python protegidos. Se detuvo solo API8000 verificada, sin escritores; lock persistente/mantenimiento, backup antes de DDL y restore UUID con upgrade/no-op bloqueantes, upgrade origen/no-op y grants negativos. Tres dumps/restores: before (ademas upgrade aislado), recorded y terminal (ambos raiz DPAPI verificada). Comparacion estructurada de filas/columnas/constraints/indices/funciones/triggers: filas F6 intactas, releases terminales previas conservadas, catalogo/BD legacy intactos. Se genero solo identidad tecnica331b3cce-401c-468e-b1c8-3b0ede344fc8/raiz nueva de boveda, no personas/configuraciones/fixtures.26 tablas contando Alembic, siete releases, nuevo intento succeeded/F7_LOCAL_VERIFIED; mantenimiento retirado.

Artefactos privados fuera del checkout: LOCALAPPDATA/OCOTE/f7-releases/f7-7db5ca6c-be1c-4f38-a10d-11007bd8ca2c contiene eventos, manifiesto, before/recorded/terminal.dumps y manifests, copia master.dpapi. No publicar. Raiz activa LOCALAPPDATA/OCOTE/vault/331b3cce-401c-468e-b1c8-3b0ede344fc8/master.dpapi. Restore adicional de UUID sintetico con ciphertext real y copia DPAPI fue descifrado; valida misma cuenta/equipo Windows, no recuperacion interequipos/off-host ni custodia cliente. El manifiesto de fuentes/evidencia no es paquete firmado/SBOM.

**Verificacion final:**

Limite del editor: get_errors conserva diagnosticos de Angular Language Service sobre standalone/imports Material tambien en componentes existentes, aunque CLI21/build de produccion y171 ChromeHeadless (incluido render real del template nuevo) pasan. No se declaran limpios esos diagnosticos ni se modifica codigo valido para silenciarlos; refrescar el servicio de lenguaje/editor y el frontend8443 conserva pendiente operativa de entorno, distinta de un fallo de los gates ejecutados.

- Backend OCOTE_RUN_PG_TESTS=0:105 passed/73 skipped; OCOTE_RUN_PG_TESTS=1:178 passed, una advertencia conocida Starlette/httpx en ambas, sin cambiar requirements.lock.28 pruebas F7 incluidas. Fallos intermedios de fixtures departamentales/expectativas historicas0005 se corrigieron conservando sus invariantes; test F6 fijado a destino0005, readiness/roles actuales exigen0006. Ruff check backend y pip check limpios.
- Angular21:171/171 ChromeHeadless158, incluye render real de nueva consola; npm run build413.89kB inicial/103.60kB transferencia estimada, sin aumentar presupuestos. Audit registrado0 criticas/altas y21 moderadas pendientes; no audit limpia ni aceptacion de riesgo cliente.
- Playwright aislado: las cuatro pestañas a1280 y360 CSS medidos, sin desbordamiento de pagina, logo/fuentes cargados; formularios storage/ClamAV/custodia/boveda y409 retienen valor secreto sintetico exacto, Guardar bloqueado y descarte/recarga explicitos. Dialogo640 CSS escritorio/345.59 CSS movil, sin solapamiento. API100% interceptada/ninguna escritura origen. Servidor de revision8444 porque8443 servia build anterior; AUTH_ORIGIN8443/cookies/Web Locks intactos.8444 no es origen de autenticacion real. Capturas en recursos de la sesion, no Git ni datos reales.
- API reiniciada127.0.0.1:8000, live200/alive y ready200/ready con monitor sin imprimir token. Relevo administrativo DPAPI eliminado al concluir PG; archivo ausente, PGPASSWORD no presente en terminal/runtime. PG18.4 sigue activo. Lectura final:0006/26 tablas/siete releases/una identidad tecnica/cero proveedores; datos anteriores preservados, custodia incompleta/cargas cerradas.

Siguiente paso permitido sin inventar datos: operador cliente debe registrar titular/suplente reales, seleccionar directorio privado existente con ACL/subdirectorios correctos, disponer ClamAV real fresco y completar pruebas/activacion/aceptacion/recuperacion conforme D05/D06. El frontend existente8443 requiere recarga/reinicio con este codigo para usar la nueva consola; no bajar Secure ni cambiar AUTH_ORIGIN para usar8444. Branding/F8..F12 requieren autorizacion separada; wizard y empaquetado quedan para el cierre final posterior. No repetir apply F7 ni editar0006; proximo esquema solo0007 o posterior.
