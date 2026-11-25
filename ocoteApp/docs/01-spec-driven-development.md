# OCOTE: especificacion funcional y visual

Version documental: 2.0. Fecha de corte: 2026-11-24. Estado: base funcional, seguridad y parametrizacion especificadas; aprobaciones formales por fase pendientes. No autoriza codigo productivo.

## 1. Proposito y gobierno SDD

OCOTE proviene del nahuatl _ocotl_, pino resinoso que ilumina el camino. Constancia, claridad y trazabilidad orientan un sistema de Gestion de Planes, Ejecucion Operativa y Evaluacion Gerencial para BI, TI, Inventarios, Compras, Contabilidad, Operacion y otros departamentos configurados.

La identidad de planes anuales se conserva, pero el producto gestiona tambien horizontes semestrales, trimestrales, mensuales y personalizados, incluso entre anios. No existe un unico ciclo anual obligatorio.

El producto permite entender que se comprometio, que se entrego, cuando se entrego y que cambio durante la ejecucion. No equipara actividad, volumen de tarjetas o tiempo conectado con productividad individual.

Fuentes normativas complementarias:

- Este documento gobierna comportamiento, lenguaje visual, contratos y aceptacion.
- [02-arquitectura.md](02-arquitectura.md) gobierna persistencia, seguridad y despliegue.
- [03-estado-actual-y-roadmap.md](03-estado-actual-y-roadmap.md) gobierna evidencia actual, secuencia, riesgos y puertas de ejecucion.
- [04-entorno-y-portabilidad.md](04-entorno-y-portabilidad.md) gobierna preparacion local, credenciales exclusivas de desarrollo y retomado en otra computadora.
- [05-paquetizacion-instalacion-y-actualizaciones.md](05-paquetizacion-instalacion-y-actualizaciones.md) gobierna paquete/instalacion local o gestionada, exportaciones/integraciones y protocolo de release del cliente.

Una discrepancia bloquea la fase afectada: se resuelve en los documentos afectados antes del cambio de codigo. Cada implementacion enlazara requisito `RF-*`, regla `RN-*`, pruebas y evidencia de aceptacion. Cambios de alcance requieren decision registrada, analisis de migracion y actualizacion de contratos antes de implementarse. OpenAPI sera derivado de esta base y versionado con pruebas de contrato; no la sustituye silenciosamente.

### Decisiones y supuestos controlados

| ID  | Base normativa                                                                                                                                                   | Confirmacion requerida                                                                                                              |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| D01 | Una organizacion, rangos/horizontes configurables, multiples planes y cruces de anio; zona operativa en system_settings.organization_timezone; sin multitenencia | America/Mexico_City y ejemplos del nucleo ratificados F3; ORGANIZATION_TIMEZONE solo bootstrap |
| D02 | Cada usuario tiene un rol y como maximo un departamento; `gerente` tiene lectura global                                                                          | Confirmada expresamente para F2 local el 2026-11-24: departamento obligatorio lider/colaborador; custodia/bootstrap reales pendientes del operador |
| D03 | Avance con pesos iguales; evaluacion departamental sin ranking individual ni nota compuesta | Formulas del nucleo ratificadas F3; politica gerencial pendiente F6 |
| D04 | Etapas/transiciones globales y catalogos en BD; cierre irreversible; roles/formulas no configurables | Semanticas F2 y cierre/fechas F3 confirmados; sin seeds. Evidencia pendiente F5 |
| D05 | Evidencia privada PDF/PNG/JPEG con techo 10 MiB; exportacion interna JSON/CSV; sin conexiones a sistemas externos en MVP                                         | Base de privacidad/retencion aprobada el 2026-11-24 en guia 05, seccion 3.1; no habilita datos reales, cargas ni aprobacion legal; escaneo fail-closed antes de F5 |
| D06 | Desarrollo portable 18.4; cliente soporta PostgreSQL 18 local/contenedor o gestionado remoto; base exacta ocoteAppDatabase                                       | Objetivos de diseno RPO <=24 h/RTO <=4 h y responsable LUIS ANGEL VALLEJO - DESARROLLADOR aprobados; sin suplente bajo excepcion local hasta 2026-12-24; restore local probado, homologacion productiva pendiente |
| D07 | Angular18.2 restringido; no actualizar automaticamente | Soporte/61 alertas son riesgos separados conservados por F4 local/sintetico hasta 2026-12-24; roadmap7/10 |
| D08 | Evaluaciones finales inmutables, corte al generar y cohorte por original | Calendario/cortes/responsables pendientes F6; no evaluaciones habilitadas por F3 |

Ratificaciones expresas del titular el 2026-11-24: D01; base D05 y objetivos/responsable D06; excepciones D06 sin suplente y D07 por fin de soporte y, separadamente tras audit, 61 alertas npm. La autorizacion posterior F2 confirma D02/D04 en los terminos siguientes. Detalle en [guia 05](05-paquetizacion-instalacion-y-actualizaciones.md#31-base-aprobada-de-privacidad-y-recuperacion-d05d06), [acta F1](03-estado-actual-y-roadmap.md#7-cierre-formal-f1-local) y [evidencia F2](03-estado-actual-y-roadmap.md#8-identidad-y-administracion-f2-local). No firmas de seguridad/legal/TI productiva ni aprobaciones D03/D08. Una puerta sin decision permanece cerrada; vencer excepcion no la renueva.

## 2. Alcance y permisos

### Autorizacion F2 del 2026-11-24

El titular autoriza expresamente F2 local/sintetico y confirma D02 (un rol, departamento obligatorio para lider/colaborador) y D04 (etapas globales, inicial open sin requisitos, terminal completed unica, aristas sin gerente y con admin). No autoriza F3-F7 ni cambia las excepciones con vencimiento 2026-12-24. Esta decision sustituye la puerta F2 pendiente del acta F1, no sus evidencias historicas.

No se ejecutan seeds de departamentos, usuarios, etapas, transiciones, prioridades, horizontes ni parametros. El primer admin se provisiona exclusivamente mediante CLI local controlada, con identidad y password introducidos por el operador, sin defaults ni secretos en argumentos/logs. Nombre organizacional, limites y etiquetas se introducen expresamente por admin; America/Mexico_City es la zona oficial elegida, no un override de entorno sobre BD.

La instalacion vacia puede estar incompleta: exactamente cinco horizontes de codes estables RN-01, prioridad normal activa, cuatro claves RN-07 y grafo valido con inicial/terminal son requisitos de configuracion completa, no filas que una migracion deba inventar. La configuracion atomica del workflow permite introducir el grafo completo sin estados intermedios invalidos. Ninguna operacion F3 se habilita en F2; la salud tecnica no certifica que el admin haya completado configuracion. La ratificacion productiva de seguridad/negocio, custodia organizacional y operacion integral siguen pendientes antes de datos reales/F7.

### Autorizacion F3 del 2026-11-24

El titular autoriza implementar, migrar y verificar F3 exclusivamente local/sintetico: seis tablas annual_plans/objectives/tasks/subtasks/task_history/due_date_requests y sus comandos/consultas. Ratifica America/Mexico_City y las formulas RN-01..RN-06 aplicables al nucleo; D03/D08 de evaluacion gerencial siguen pendientes para F6. Se conservan responsable LUIS ANGEL VALLEJO - DESARROLLADOR, vencimiento 2026-12-24 y restricciones sin datos reales, red compartida, produccion/nube ni entradas no confiables. No habilita F4-F7 ni cambia las evidencias historicas F1/F2.

No se introducen defaults/seeds de negocio ni identidades en origen. El admin debe completar bootstrap y configuracion F2 explicitamente; comandos operativos fallan cerrados si faltan parametros/catalogos/flujo. Las pruebas crean sus fixtures solo en destinos UUID aislados. No se modifican helpers locales, base ocote ni releases historicas validas. Etapas que requieren evidencia rechazan entradas con 422 hasta F5, sin aceptar URLs/IDs ficticios ni crear evidence_files. Cada mutacion tarea/subtarea e historia comparte transaccion; una carrera/version obsoleta no deja cambios parciales.

Implementacion y bootstrap posterior observado en [evidencia F3](03-estado-actual-y-roadmap.md#9-nucleo-operativo-f3-local). Fechas ISO YYYY-MM-DD estrictas, timestamps UTC; listas limit1..100/cursor/next_cursor y filtros antes de paginar. Historia created_at/id con cursor de misma tarea. Status-changes admite reason opcional; periodos/fechas/asignacion/decisiones lo exigen. GET auth/me anuncia solo facultades F1-F3; ningun agregado para C. No repetir/sobrescribir bootstrap existente ni confundir ready con configuracion completa.

### Autorizacion F4 del 2026-11-24

El titular autoriza sistema visual y flujos Angular RF-01..05/RF-11 y RN-01..06 de interfaz, incluidos configuracion explicita, solicitudes de fecha y perfil. F4 debe poder presentar una instalacion vacia para que admin la configure: no se inventan ni precargan valores/filas de negocio. Access y CSRF solo en memoria; refresh/logout coordinados entre pestanas mediante Web Locks, sin fallback concurrente inseguro. Origin lo genera el navegador; GET csrf mismo origen envia Referer verificable. Conflictos409 conservan formulario y exigen recarga explicita/version nueva, nunca reenvio automatico de comandos.

Se mantienen backend/head0003, migraciones/helpers/legacy/releases historicas, bootstrap existente y restricciones locales/sinteticas. La excepcion hasta2026-12-24 bajo LUIS ANGEL VALLEJO - DESARROLLADOR cubre esta F4 expresamente autorizada, sin renovacion ni remediacion implicita. F5-F7 no autorizados: ninguna UI Kanban/Timeline/carga de evidencia/analitica/evaluaciones/exports/nube. Evidencia y limites F4 se registran en roadmap10; muestras visuales y tipografia/Material se verifican durante este incremento, no se presumen aprobadas por autorizarlo.

### Autorizacion F5 del 2026-11-24

El titular autoriza expresamente implementar y verificar RF-06/RF-07/RF-08 local/sintetico, incluida revision aditiva0004 bajo backup/migracion/no-op/restauracion aislada. Conserva responsable LUIS ANGEL VALLEJO - DESARROLLADOR y excepcion hasta2026-12-24, sin produccion/nube ni entradas no confiables. No altera0001/0002/0003, helpers, legacy ocote, releases validas ni bootstrap/configuracion de negocio. F6-F7 no autorizados. Autorizar desarrollo no afirma que el operador haya completado configuracion/aceptacion F4.

Contratos F5: GET /api/v1/kanban conserva carriles activos vacios/ordenados, filtros y paginacion por etapa con alcance previo al conteo; C solo sus propias tareas, nunca conteos ajenos. Transicion sigue POST /tasks/{id}/stage-transitions con expected_version/motivo/evidence_ids y sin orden manual persistido. GET /api/v1/timeline pagina proyecciones por tipo plan/objective/task/subtask con mismos filtros; C solo tareas/subtareas asignadas y contexto minimo, no agregados ni consultas de modulos de planificacion. Fechas civiles no se convierten por zona del navegador; cierre UTC se presenta en America/Mexico_City. Sin drag de fechas.

GET/POST /tasks/{id}/evidence y GET /evidence/{id}/content usan autorizacion de tarea; subida solo A/L/C con tarea/plan abiertos y version capturada. Contenido binario acotado, nombre informativo saneado, MIME/extension/firma PDF/PNG/JPEG concordantes y SHA-256; limite vigente evidence_max_bytes leido de BD. Almacen privado y scanner son configuracion tecnica explicita, nunca catalogos/settings sembrados. Cuarentena antes de escanear, publicar solo resultado limpio confirmado; scanner ausente/error/timeout/desconocido devuelve503, malware422, tipo415/tamano413, sin fila disponible ni transicion parcial. No se simula un antivirus real con una comprobacion de firmas. El entorno de pruebas puede inyectar dobles sinteticos identificados como tales, no habilitan cargas operativas por si solos.

Conservacion RN-04/D05: no DELETE ni purga de evidencias publicadas en MVP, tampoco por admin; gestion significa adjuntar/listar/descargar con alcance, no borrar historia. Evidencias validas se conservan al cerrar; descarga autenticada attachment/nosniff sin rutas internas/storage_key. Registro de archivo+version+task_history/audit_events en una transaccion con compensacion del archivo nuevo si falla commit. Solo evidence_files en F5 (18 tablas incluyendo alembic_version); la tabla restante del objetivo19 corresponde a F6 y no se adelanta.

Estado tecnico F5 en [roadmap11](03-estado-actual-y-roadmap.md#11-kanban-timeline-y-evidencias-f5-local):0004 aplicada con protocolo y datos conservados, API/UI verificadas local/sintetico. Raiz privada **fuera del checkout/releases**, ACL nativa Windows/POSIX y subdirectorios quarantine/objects existentes, ClamAV loopback explicitamente configurado. No existen aun esa configuracion/servicio verificados en el entorno: cargas operativas cerradas, no afirmar antivirus real por los dobles de prueba. Guardar scan_engine=clamav, scan_version y scanned_at <= created_at como atestacion tecnica privada append-only; no exponerlos en metadata publica. GET timeline incluye organization_timezone desde BD; UI transforma el instante de cierre a esa zona, no usa override de entorno. Descarga registra solicitud auditada sin ruta/contenido. Aceptacion/configuracion F4/F5 y ensayo D05 real pendientes, no cierre operativo ni autorizacion F6/F7.

MVP: autenticacion, configuracion en BD, planes/objetivos, tareas/subtareas con prioridad, solicitudes/aprobaciones de fecha, evidencia, auditoria, Kanban/Timeline, analitica, exportacion interna y evaluacion. Interfaz en espanol, responsive y accesible.

Fuera de MVP: multiples empresas, SSO, aplicaciones moviles nativas, notificaciones externas, chat, registro de horas, dependencias criticas tipo Gantt, tareas recurrentes, pesos personalizados, IA predictiva, ranking de empleados y reapertura de tareas completadas. Timeline no implica un motor de planificacion automatica.

| Capacidad                                               | admin  | gerente        | lider                                                   | colaborador                               |
| ------------------------------------------------------- | ------ | -------------- | ------------------------------------------------------- | ----------------------------------------- |
| Catalogos, roles, etapas y transiciones                 | Global | No             | No                                                      | No                                        |
| Planes y objetivos                                      | Global | Global         | Lectura filtrada propia                                 | Solo contexto minimo en tarea             |
| Crear tareas, reasignar, programar, gestionar subtareas | Global | Lectura global | Su departamento                                         | No                                        |
| Mover etapa y adjuntar evidencia                        | Global | Lectura global | Su departamento                                         | Solo tareas asignadas                     |
| Completar subtarea existente                            | Global | Lectura global | Su departamento                                         | Solo tareas asignadas                     |
| Solicitar/cancelar cambio de compromiso                 | Global | Global         | Solicita en su departamento; cancela propias pendientes | No                                        |
| Aprobar/rechazar o ejecutar cambio de compromiso        | Global | Global         | No                                                      | No                                        |
| Kanban, Timeline e historial de tarea                   | Global | Global         | Su departamento                                         | Solo tareas asignadas, sin totales ajenos |
| Analitica y metricas agregadas/exportaciones            | Global | Global         | Su departamento                                         | No                                        |
| Evaluar y finalizar evaluaciones                        | Global | Global         | Lectura propia final                                    | No                                        |

`admin` es una facultad excepcional auditada, no una identidad para trabajo cotidiano. La API calcula alcance desde la identidad; ningun `department_id` enviado por el cliente concede permisos. Un colaborador ve el objetivo y plan minimos de sus tareas, pero no agregados que revelen trabajo ajeno. Recursos inexistentes o fuera de alcance devuelven 404; acciones no permitidas sobre recursos visibles devuelven 403.

### Navegacion, rutas, pantallas y proyecciones

Rutas SPA objetivo, aun no implementadas. A=admin, G=gerente, L=lider, C=colaborador; oculto significa sin enlace de menu ni precarga de datos. El servidor aplica la misma politica a URL directa y API.

| Ruta/pantalla                                                                       | A                                                               | G                                     | L                                                          | C                                                     |
| ----------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------- |
| /login y /perfil                                                                    | Login publico; perfil propio                                    | Igual                                 | Igual                                                      | Igual                                                 |
| /planes y /planes/:id                                                               | Global; CRUD autorizado                                         | Global; CRUD autorizado               | Planes con objetivos propios; proyeccion filtrada          | Oculto; contexto minimo dentro de tarea               |
| /objetivos y /objetivos/:id                                                         | Global; crear/editar/periodos                                   | Global; crear/editar/periodos         | Lectura del departamento                                   | Oculto; contexto minimo dentro de tarea               |
| /tareas y /tareas/:id                                                               | Global; acciones operativas                                     | Lectura global y comandos de fecha    | Crear/gestionar en su departamento                         | Solo asignadas; etapa, subtarea existente y evidencia |
| /kanban y /timeline                                                                 | Global; editar segun accion                                     | Global; lectura, fecha por formulario | Departamento; mover segun arista                           | Asignadas; mover segun arista, sin editar fecha       |
| /solicitudes-fecha                                                                  | Global; decidir/cancelar                                        | Global; decidir/cancelar              | Departamento; solicitar, leer, cancelar propias pendientes | Oculto                                                |
| /analitica                                                                          | Global                                                          | Global                                | Departamento                                               | Oculto y API 403                                      |
| /evaluaciones y /evaluaciones/:id                                                   | Global; draft/final y comandos                                  | Global; draft/final y comandos        | Solo finales propias                                       | Oculto y API 403                                      |
| /administracion/departamentos y /administracion/usuarios                            | Catalogos/roles; proteger ultimo admin                          | Oculto                                | Oculto                                                     | Oculto                                                |
| /administracion/etapas y /administracion/transiciones                               | Configuracion global auditada                                   | Oculto                                | Oculto                                                     | Oculto                                                |
| /administracion/parametros, /administracion/prioridades, /administracion/horizontes | Parametros/catalogos segun RN-07                                | Oculto                                | Oculto                                                     | Oculto                                                |
| /administracion/releases y /administracion/auditoria                                | Lectura global sanitizada; sin secretos ni backups descargables | Oculto                                | Oculto                                                     | Oculto                                                |

- Lider recibe en cada plan solo objetivos de su departamento y metricas sobre ese subconjunto; un plan compartido no concede visibilidad a otros objetivos. Catalogos de responsables solo incluyen usuarios elegibles del departamento.
- Colaborador no usa listados completos de planes/objetivos: el detalle de su tarea incluye solo id/titulo/horizonte/fechas del objetivo y plan, sin descripcion gerencial, otras tareas, evaluaciones, nombres de companeros o porcentajes del objetivo/plan. Contadores Kanban y paginacion se calculan sobre sus tareas, no son metricas departamentales.
- Listados no incluyen items, conteos ni facetas ajenos; consultar un ID ajeno retorna 404 RESOURCE_NOT_FOUND. Accion prohibida sobre recurso visible: 403 FORBIDDEN. Si el modulo completo esta prohibido (analitica para C, administracion para G/L/C), retorna 403 sin consultar la existencia del ID. JWT ausente/invalido: 401 antes de datos.
- Ocultar acciones que el rol nunca puede usar. Deshabilitar solo acciones visibles temporalmente imposibles (version obsoleta, tarea cerrada, evidencia faltante), con explicacion accesible asociada, no solo tooltip o color. Foco/lector anuncian error; guards Angular no sustituyen autorizacion.
- Catalogos operativos para una sesion son proyecciones minimas de prioridades/horizontes/etapas, no acceso al panel ni a system_settings completo. Auditar descargas y denegaciones relevantes sin datos sensibles en el error.

## 3. Lenguaje del dominio y reglas

### RN-01. Plan, pertenencia y alcance

- `annual_plans` conserva su nombre tecnico y la ruta `/annual-plans` por estabilidad documental; en la UI se llama Planes. Cada plan tiene `start_date`, `due_date`, `horizon_type` y `status = draft | active | closed`; transiciones unidireccionales `draft -> active -> closed`.
- Planes y objetivos usan `horizon_type = annual | semiannual | quarterly | monthly | custom` (Anual, Semestral, Trimestral, Mensual, Personalizado). Es una clasificacion declarada: no fuerza calendario ni una cantidad fija de dias; el rango explicito siempre manda. La UI puede proponer rangos, nunca reemplazarlos silenciosamente.
- `start_date <= due_date`, extremos inclusivos; se admite un solo dia, cruces de mes/anio y planes con fechas iguales o solapadas identificados por UUID. No hay `year` obligatorio ni unicidad por anio. Una meta anual calendario se expresa, por ejemplo, con annual y 2027-01-01..2027-12-31; tambien se admite un anual movil.
- `objectives`: pertenecen a un plan y a un departamento, tienen su propio `horizon_type`, `start_date` y `due_date`, contenidos en el intervalo del plan. Su horizonte puede diferir del padre (objetivo trimestral dentro de plan anual). Una tarea hereda plan/departamento via objetivo; no se repiten en `tasks`.
- `admin` o `gerente`, como responsables de planificacion, especifican estos periodos. Cambios posteriores usan comandos `period-changes` con `reason` y `expected_version`, en draft/active; se registran en `audit_events` con antes/despues. No hay cascada de fechas a hijos ni cambios por PATCH generico.
- Contraer o desplazar un plan exige contener objetivos y periodos de evaluaciones existentes; un objetivo debe contener las fechas start_date, original_due_date y due_date de todas sus tareas. Si excluye un hijo o foto existente: 409 DEPENDENCY_CONFLICT, sin cambios. Primero se ajustan rangos en el orden valido; las fechas originales de tareas nunca se reescriben.
- Se crean objetivos y se editan titulo/descripcion en planes `draft` o `active`; se crean y ejecutan tareas solo en `active`. En `closed` no se permiten cambios operativos, incluidos evidencias y subtareas; si se necesitan correcciones, se registran como nueva decision fuera de MVP.
- Activar requiere al menos un objetivo y departamentos activos; cerrar requiere todas sus tareas completadas. No se exige que todos los objetivos tengan tareas, pero se muestran como sin datos.
- El fin del periodo no cierra automaticamente el plan ni impide registrar una entrega tardia; el cierre es un comando explicito. No se reabre un plan cerrado en MVP.
- Responsable obligatorio: usuario activo del departamento del objetivo. Trasladar un usuario exige primero resolver sus tareas abiertas; no se trasladan objetivos ni tareas con actividad entre departamentos o planes.
- No se eliminan tareas, subtareas, planes ni objetivos en MVP. Catalogos y usuarios se desactivan; nunca se rompe historia. Un titulo o descripcion se puede corregir mientras el plan este activo y la tarea no este completada; se audita.
- Una tarea completada es de solo lectura, incluidas reasignacion y nuevas evidencias. No se desactiva ni se cambia a otro rol al ultimo `admin` activo; esta proteccion tambien se verifica bajo concurrencia.

### RN-02. Fechas y puntualidad

- `start_date`, `original_due_date` y `due_date` son fechas civiles `YYYY-MM-DD`, no limitadas por anio calendario. En tareas, las tres deben estar dentro del intervalo de su objetivo, que esta contenido en su plan. `start_date <= due_date` y `start_date <= original_due_date`. La fecha real de cierre puede superar estos horizontes: debe reflejar la entrega tardia, no rechazarse ni falsearse.
- `original_due_date` se copia de `due_date` al crear tarea o subtarea y nunca cambia. `completed_at` es un instante UTC del servidor, solo presente al completar. `created_at`, `updated_at` y auditoria tambien usan UTC.
- Una entrega vence al terminar `due_date` en la zona IANA de `system_settings.organization_timezone` (RN-07). Igualdad de fecha es a tiempo. El backend usa reloj confiable; el navegador no decide resultados. Fines de semana/festivos son dias naturales en MVP.
- El cambio de compromiso usa exclusivamente la operacion `due-date-changes`, autorizada para `admin` o `gerente`, con `reason` no vacio. No se admiten fechas en un PATCH generico. `due_date` puede adelantarse o aplazarse; `original_due_date` permanece intacta. Cambios tras completar o cerrar plan: 409.
- Lider solicita desde tarea/subtarea con fecha propuesta y motivo; due_date_requests no altera la fecha ni version de tarea. Admin/gerente revisa contexto e historial y aprueba/rechaza con motivo. Aprobar verifica versiones de solicitud, tarea y subtarea y ejecuta el mismo service de due-date-changes; fecha, task_history y decision/audit_events se confirman atomicamente. Gerente tambien puede cambiar fecha directamente con motivo sin solicitud ficticia.
- Solo una solicitud pending por tarea o subtarea destino. Si el recurso cambio, aprobar devuelve 409 VERSION_CONFLICT sin modificar ni marcar aprobada; cancelar/rechazar y presentar una nueva propuesta con datos actuales. Rechazo/cancelacion no cambian fechas; lider solo cancela su propia pending, admin/gerente cualquiera visible. Estados approved/rejected/cancelled finales. Solicitante y aprobador deben ser personas distintas.
- Cambiar `start_date` requiere motivo y auditoria, no modifica `original_due_date`; no puede dejar fechas inconsistentes. No se cambia silenciosamente la programacion de subtareas.
- Para una tarea con subtareas: `task.start_date <= subtask.start_date <= subtask.original_due_date <= task.original_due_date` y `subtask.start_date <= subtask.due_date <= task.due_date`. Al reprogramar el padre, si alguna subtarea queda fuera de rango, se rechaza toda la operacion con 409; primero se reprograman las hijas o el padre segun la direccion necesaria. No hay cascada automatica.

Campos calculados de lectura, nunca editables:

| Campo                         | Formula                                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `punctuality_status`          | Con `completed_at`: `on_time` si fecha local de cierre <= `due_date`; si no `late`. Sin cierre: `overdue` si hoy local > `due_date`; si no `pending` |
| `baseline_punctuality_status` | La misma formula, comparando con `original_due_date`                                                                                                 |
| `is_overdue`                  | Sin cierre y hoy local > `due_date`, aunque la etapa sea bloqueada                                                                                   |
| `due_date_delta_days`         | `due_date - original_due_date` en dias civiles, firmado                                                                                              |
| `delay_days`                  | Maximo de 0 y diferencia entre fecha local de cierre (o hoy) y `due_date`                                                                            |
| `baseline_delay_days`         | La misma formula contra `original_due_date`                                                                                                          |

Etiquetas: `on_time` = A tiempo; `late` = Con retraso; `overdue` = Vencida; `pending` = Pendiente. `blocked` significa Bloqueada y es una clase de etapa, no un valor de puntualidad. La UI prioriza la etiqueta Bloqueada, pero conserva Vencida como indicador adicional si corresponde. Una reprogramacion puede mejorar puntualidad vigente, nunca borrar retraso original ni el historial.

### RN-03. Avance, subtareas y cierre

- `workflow_stages.kind = open | blocked | completed`. `stage_id` identifica la etapa; el nombre visible no determina semantica. Solo una etapa activa es `is_initial`; solo una es de clase `completed`. Una etapa inicial debe ser `open`.
- Sin subtareas: tarea abierta/bloqueada = 0%; completada = 100%. Con subtareas: `progress_percent = 100 * subtareas completadas / total de subtareas`.
- `subtasks.status = pending | completed`; completar fija `completed_at` del servidor. No hay reapertura ni workflow propio de subtarea en MVP. Su puntualidad sigue RN-02.
- Todas las subtareas completas producen 100%, pero no cierran automaticamente la tarea: se conserva la etapa hasta validar evidencia/motivo y mover explicitamente a `completed`. `pending_closure = true` si tiene subtareas, avance 100% y aun no esta completada.
- No se puede cerrar una tarea con subtareas pendientes, agregar subtareas a una completada ni modificar o reabrir subtareas completadas. Agregar una subtarea pendiente a una tarea abierta puede reducir el avance; el evento se audita.
- Avance de objetivo = promedio simple del avance de sus tareas. Avance de plan = promedio simple de todas sus tareas, no promedio de promedios departamentales. Departamentos y filtros usan la misma base de tareas. Sin tareas: `null`, etiqueta Sin datos, nunca 0% ni 100%.
- Redondeo a dos decimales solo para representacion; agregaciones con precision completa. `completion_rate` cuenta tareas cerradas/total y no se confunde con `progress_percent`.
- `position` ordena visualmente etapas, no pondera trabajo ni define porcentaje. Un grafo puede ramificarse, saltar o volver a etapas abiertas; por ello no se usa el indice de etapa ni `position / (cantidad - 1)` como avance. Se conserva la formula anterior y la separacion etapa/avance/puntualidad; un cambio de metrica requeriria decision normativa expresa, no un ajuste de interfaz.

### RN-04. Etapas configurables y evidencia

- Etapas globales con `code` estable, `name`, `position`, `kind`, `requires_evidence`, `requires_reason` e `is_active`. todo/in_progress/blocked/completed son ejemplos de diseno, NO seeds aprobados. F2 inicia vacio; admin define etapas y transiciones en apartados separados. Antes de tareas/evaluaciones se permite construir el catalogo por pasos, conservando unicidad y semanticas inicial/terminal; no habilita operacion hasta completar el grafo. La configuracion atomica sigue disponible en Configuracion.
- La etapa inicial no exige evidencia ni motivo: el alta entra en ella antes de que exista evidencia. Las reglas se validan sobre la etapa destino de cada transicion y no se aplican retroactivamente a tareas ya ubicadas alli.
- `workflow_transitions` define aristas permitidas y roles habilitados; la matriz de permisos y el alcance se comprueban ademas. No se permiten autoaristas ni salidas de `completed`. La secuencia visual no concede una transicion.
- Una transicion a etapa con `requires_reason` exige texto de 10 a 2000 caracteres; `requires_evidence` exige al menos un `evidence_id` valido y disponible de esa tarea. Es configurable por etapa, sin asumir que una URL externa demuestra entrega.
- El minimo estructural operativo son dos etapas activas distintas: inicial `open` y terminal `completed`, con un camino permitido hasta la terminal para cada etapa activa. No se imponen cinco etapas, nombres ni etapas intermedias; cumplir una cantidad por si sola no valida el grafo. Esta aclaracion no crea ni modifica configuracion existente.
- El selector de evidencia de una transicion enumera archivos previamente adjuntos/verificados de esa misma tarea, recorriendo todas sus paginas autorizadas; no es un campo de carga ni acepta una URL como sustituto. Si esta vacio, la UI explica que debe adjuntarse desde el detalle y mantiene el requisito obligatorio. Si la respuesta anuncia `uploads_configured=false`, informa que falta configurar almacenamiento privado y/o ClamAV y remite al operador; el flag no acredita salud/frescura del antivirus ni habilita una excepcion al cierre fail-closed.
- Evidencia: archivo privado PDF/PNG/JPEG verificado por contenido, maximo 10 MiB. Se descarga solo con autorizacion de tarea; se rechazan HTML, SVG, ejecutables, discrepancias MIME y nombres/rutas enviados para acceso al disco. El backend decide nombre de almacenamiento.
- Cambiar reglas de una etapa aplica a nuevas entradas, no invalida cierres previos; queda auditado. No se cambia `kind`, `code` ni `is_initial` despues de referenciarla. No se desactiva una etapa ocupada, la inicial ni la terminal. Reordenar no mueve tareas. No hay borrado de historia ni evidencia en MVP.

### RN-05. Auditoria y concurrencia

- Cada creacion, modificacion de campos, movimiento, reasignacion, cambio de fechas, evidencia y cierre de tarea/subtarea genera `task_history` append-only con actor, instante, motivo, evento, antes/despues y `request_id`. Subtareas incluyen `subtask_id`.
- Administracion y seguridad se registran en `audit_events`; no se fuerzan eventos de configuracion dentro de una tarea inexistente. Nunca se almacenan contrasenas, tokens o contenido binario en bitacoras.
- Mutacion de negocio e historia se confirman en una misma transaccion. Un error revierte ambas. No hay endpoint para editar/eliminar historia. El rol de aplicacion no tiene UPDATE/DELETE sobre bitacoras; esto no vuelve invulnerable a un superusuario de base de datos.
- Recursos mutables incluyen `version` entero. Comandos de actualizacion usan `expected_version`; un desfase devuelve 409 y no altera datos ni agrega eventos de exito. Se bloquean filas padre/hijas segun el comando para evitar cierres, subtareas y fechas concurrentes inconsistentes.
- Cambios de periodo de plan/objetivo van a `audit_events`; no generan task_history artificial si no cambiaron tareas. Actualizaciones del cliente preservan IDs, FK, task_history, audit_events y fotos finales mediante migraciones versionadas y protocolo de respaldo/contingencia; ver arquitectura y guia operativa. El arranque local no aplica migraciones ni seeds.

### RN-06. Medicion y evaluacion

- Los tableros muestran conteos, avance, tasa de cierre, puntualidad original/vigente, dias de retraso, bloqueos y reprogramaciones. Toda grafica muestra filtros y denominador; no oculta pendientes para inflar puntualidad.
- Conjunto de tareas `C` segun plan/departamento y rango inclusivo de `original_due_date`; sin rango, todas las tareas del plan visibles. `N = |C|`. `completion_rate = 100 * cerradas / N`; `baseline_on_time_rate = 100 * cerradas a tiempo original / N`; `on_time_rate = 100 * cerradas a tiempo vigente / N`. Si N=0, tasas y avance son `null`.
- Puntualidad usa tareas, no subtareas como unidades adicionales. Un porcentaje de avance no prueba calidad de un resultado. No hay score automatico compuesto ni penalizacion numerica oculta.
- Evaluacion por departamento, plan y periodo elegido; fechas inclusivas contenidas en start_date..due_date del plan, incluso entre anios, y sin solapamientos para el mismo departamento/plan. `status = draft | final`. Horizon_type no altera las formulas ni el denominador.
- La cohorte se fija por `original_due_date` en el periodo; cambiar `due_date` no saca tareas del denominador. Se capturan metricas y detalle por tarea en `snapshot_at` UTC al crear o recalcular el borrador. El borrador puede recalcularse con comando explicito y control de version.
- El corte representa lo conocido en `snapshot_at`, NO una reconstruccion historica al fin del periodo: una entrega tardia posterior al periodo puede aparecer completada, pero sigue tarde frente al compromiso original. La UI y los informes muestran periodo y fecha de corte por separado.
- Finalizar exige periodo concluido en zona organizacional, `summary` de 10 a 4000 caracteres y cohorte no vacia. Recalcula y sella la foto en la misma transaccion consistente; queda inmutable. Informes y evaluaciones finales leen la foto, no el estado actual. No hay reapertura o reemplazo silencioso.
- Las series mensuales usan claves YYYY-MM y recortan por el rango solicitado, no reinician ni mezclan anios. Comparaciones muestran inicio, fin y denominador de cada periodo; no normalizan periodos de diferente duracion a un score de productividad. Consultas multiplan cuentan cada task_id una sola vez.

### RN-07. Parametrizacion, no reglas arbitrarias

- `system_settings` es la fuente unica de parametros operativos; solo admin los edita por clave permitida, motivo y version. El esquema tipado/limites pertenece a codigo versionado; no se ejecuta JSON, SQL, JavaScript o expresiones guardadas. No se admiten claves libres ni CRUD destructivo.
- Claves MVP: `organization_name` (string 1..160), `organization_timezone` (zona IANA valida, oficial America/Mexico_City D01), `evidence_max_bytes` (entero 1..10485760), `export_max_rows` (entero 1..10000). Sin valores insertados por F2: 5000 era referencia, no default operativo. Admin crea las cuatro claves explicitamente. Nombre/limites cambian para nuevas operaciones al commit; cada peticion lee BD sin cache divergente. Reducir limite no elimina evidencia previa. Cuerpo HTTP tiene techo independiente.
- Zona: se elige explicitamente al instalar; `ORGANIZATION_TIMEZONE` es solo entrada inicial, no override runtime. Tras la primera tarea o evaluacion queda bloqueada para edicion ordinaria (409); correccion excepcional requiere mantenimiento, analisis historico, aprobacion y revision versionada, nunca reescribir originales/fotos. Evaluaciones guardan zona y calculation_version propias.
- Prioridades en `priorities`: admin configura nombre, orden y activo; codes estables, `normal` obligatoria/no desactivable, FK `tasks.priority_id` obligatoria. Prioridad no cambia formulas, denominadores, permisos ni puntualidad; no hay prioridad propia de subtarea. Cambiar/desactivar etiqueta no reescribe task_history ni fotos.
- `horizon_types` requiere los cinco codes RN-01 como claves estables referenciables (UUID PK, code UNIQUE/FK). No hay filas iniciales: admin puede crear explicitamente solo esos codes, nunca otros ni DELETE/renombre de code. Edita nombre/orden/disponibilidad; `custom` permanece activo. Desactivar no invalida planes/objetivos existentes: sin cambio de code se permiten correcciones de rango; fotos conservan codigo/etiqueta capturada. Configuracion vacia es incompleta, no error de migracion.
- Configuracion existente del cliente prevalece sobre seeds. Departamentos, usuarios, etapas, transiciones, prioridades, horizontes y parametros son datos de BD; roles, estados, formulas, autorizacion y contrato son codigo versionado. Paleta OCOTE no es un editor de temas en MVP.
- DSN, passwords, claves JWT, CA/rutas de secretos y credenciales de almacenamiento quedan en entorno/gestor de secretos, nunca system_settings, SPA, exports o auditoria. `release_history` contiene metadatos de despliegue, no secretos ni archivos de backup; solo herramienta operativa registra intentos, admin consulta proyeccion sanitizada.

## 4. Requisitos y aceptacion verificable

| ID / modulo                       | Criterios de aceptacion                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| RF-01 Administracion              | Admin crea/desactiva departamentos y usuarios y configura etapas/transiciones; email canonico y codigos duplicados dan 409. Un colaborador recibe 403 al administrarlos. No se desactiva ni degrada de rol al ultimo admin activo, ni se desactiva un departamento con objetivos de planes no cerrados o usuarios activos                                                                        |
| RF-02 Autenticacion               | Login valido emite access token y cookie refresh; refresh rota una sola vez; reutilizarlo revoca la familia. Logout invalida la sesion; desactivar usuario o cambiar rol/contrasena invalida todas. Token vencido 401; acceso cruzado a tarea 404                                                                                                                                                |
| RF-03 Plan y objetivos            | Permite dos planes en el mismo anio y uno custom 2027-11-15..2028-02-20; objetivo con rango/horizonte propio contenido en padre. Rango invertido/fuera del padre: 422; contraccion que excluye hijos/evaluaciones: 409. Cambio de periodo requiere motivo, version y audit_events. Plan draft no acepta tareas; activar sin objetivos/cerrar con tareas abiertas: 409; closed rechaza mutaciones |
| RF-04 Tareas y subtareas          | Responsable de otro departamento da 422; tarea sin subtareas pasa de 0 a 100 al cierre; 1 de 4 subtareas da 25%; 4 de 4 da 100% y pendiente de cierre; cerrar con una pendiente da 409                                                                                                                                                                                                           |
| RF-05 Fechas                      | Con original 2027-03-10, vigente 2027-03-15 y cierre local 2027-03-12: `on_time`, `baseline_punctuality_status=late`, delta 5, retraso original 2; cambiar fecha conserva original y evento. A medianoche del dia siguiente una tarea abierta pasa a overdue sin escritura programada                                                                                                            |
| RF-06 Workflow y evidencia        | Solo transiciones configuradas; falta de motivo/evidencia requerida da 422; una etapa ocupada no se desactiva. Archivo ajeno da 404, invalido 415, demasiado grande 413. Ningun fallo mueve la tarjeta                                                                                                                                                                                           |
| RF-07 Kanban                      | Carriles por etapas activas ordenadas; se mantienen columnas vacias. Filtros de plan, departamento, responsable y puntualidad; conteos y cursor por carril. Drag/drop y alternativa por menu usan el mismo comando; 409 restaura estado y anuncia conflicto; no se persiste un orden manual de tarjetas en MVP                                                                                   |
| RF-08 Timeline                    | Mismos filtros, permisos y formulas del Kanban; grupos por departamento o responsable; barras start_date/due_date, marcador original y cierre con leyenda textual. No permite arrastrar fechas en MVP: usa formulario autorizado con motivo y confirma con respuesta API                                                                                                                         |
| RF-09 Tableros                    | Comparacion departamental y tendencias mensuales por fecha original, filtros compartidos y tabla equivalente. Fixture con 4 tareas, 2 cerradas, una a tiempo original: cierre 50%, puntualidad original 25%; sin tareas muestra Sin datos. Un lider no obtiene agregados globales                                                                                                                |
| RF-10 Evaluacion                  | Cohorte por compromiso original en el periodo elegido, incluso entre anios; fuera del plan: 422. Foto final y detalle no cambian al reprogramar/entregar despues. Solapamiento 409; final sin datos o periodo abierto 409; colaborador no accede                                                                                                                                                 |
| RF-11 Auditoria                   | Mover, reasignar, completar subtarea o cambiar fecha produce exactamente un evento de negocio correspondiente con antes/despues en la misma transaccion; fallo no produce evento exitoso. Historia ordenada por instante e id, paginada y autorizada                                                                                                                                             |
| RF-12 Experiencia y accesibilidad | Navegacion por teclado y lector, foco visible, estados vacio/carga/error/sin permisos/conflicto; sin solapamiento a 360, 768 y 1440 px, zoom 200%. Cumple contrastes de seccion 5 y reduced-motion; nunca depende solo del color                                                                                                                                                                 |
| RF-13 Parametros/catalogos        | Admin edita claves tipadas, prioridades y cinco horizontes con version/motivo/audit_events; tipo/limite invalido 422, version obsoleta 409, clave no editable 403. Dos procesos observan mismo valor tras commit; zona bloqueada tras primer uso; seeds repetidos no pisan valores; referencia a catalogo inactivo se conserva pero no se selecciona para alta                                   |
| RF-14 Solicitudes de fecha        | Lider solicita en su departamento; C recibe 403; duplicada pending 409. Aprobar por otra persona verifica versiones y contencion, preserva original y produce cambio+historia+decision atomicos; carrera con cierre/edicion da 409 sin aprobacion parcial; rechazo/cancelacion preservan fecha                                                                                                   |
| RF-15 Exportacion interna         | Solo A/G global y L propio; C 403 incluso por URL. JSON/CSV de tareas y evaluaciones finales usan filtros, proyeccion y corte autorizados; limite, formula-injection, cero filas y auditoria de exito/fallo probados; sin descarga de secretos/binarios/backups ni filtros que amplien alcance                                                                                                   |

Pruebas de borde obligatorias: anio bisiesto, cruces de anio, anual movil, rango de un dia y multiples planes solapados; objetivo fuera de plan y contraccion ante fecha original inmutable/evaluacion final; fin de dia y horario de verano; fecha adelantada/aplazada; bloqueada y vencida; 0 subtareas; denominador vacio; responsable desactivado; doble refresh; actualizaciones simultaneas; cierre concurrente con alta de subtarea; evidencia ajena; acceso directo a IDs y agregados fuera de alcance.

## 5. Identidad visual y Material Theme Custom

### Tokens normativos

La tabla es el registro canonico de valores. Los otros documentos remiten a esta seccion. F4 implementa tokens `--ocote-*` y estilos SCSS/Material; Kanban, Timeline y ECharts futuros los reutilizaran. No se duplican hexadecimales dispersos en componentes.

| Token CSS propuesto         | Nombre / rol           | Valor     | Uso                                              |
| --------------------------- | ---------------------- | --------- | ------------------------------------------------ |
| `--ocote-primary`           | Resina de Ocote        | `#B85A1E` | Acciones primarias, progreso y revision          |
| `--ocote-primary-dark`      | Resina oscura          | `#7A3810` | Hover/pressed y enlaces sobre tintes             |
| `--ocote-primary-tint`      | Resina clara           | `#FDECE0` | Seleccion y contenedores primarios               |
| `--ocote-secondary`         | Bosque de Altura       | `#2E5A44` | Rol secundario de producto                       |
| `--ocote-tertiary`          | Bosque de Altura       | `#2E5A44` | Rol terciario Material, misma familia            |
| `--ocote-accent`            | Rescoldo Dorado        | `#D98A1C` | Enfasis y comparaciones, no texto blanco pequeno |
| `--ocote-background`        | Niebla de Sierra       | `#F6F4F0` | Fondo general                                    |
| `--ocote-surface`           | Madera Clara           | `#FFFFFF` | Tablas, superficies y dialogos                   |
| `--ocote-surface-secondary` | Arena de Bosque        | `#ECE7DF` | Carriles Kanban, cabeceras secundarias           |
| `--ocote-border`            | Tronco Suave           | `#D8CFC2` | Divisores decorativos                            |
| `--ocote-text`              | Carbon de Ocote        | `#1F1A16` | Texto principal y texto sobre dorado             |
| `--ocote-text-secondary`    | Musgo Gris             | `#5C534A` | Texto secundario y bordes de controles           |
| `--ocote-success`           | Completado / a tiempo  | `#2E7D5B` | Estado favorable                                 |
| `--ocote-in-progress`       | En progreso / revision | `#B85A1E` | Estado en curso                                  |
| `--ocote-series-contrast`   | Serie de contraste     | `#2B5B84` | Serie comparativa, no redefinir exito            |
| `--ocote-warning`           | En riesgo / aplazado   | `#D98A1C` | Alerta con texto oscuro                          |
| `--ocote-danger`            | Vencido / bloqueado    | `#B83227` | Error y excepciones operativas                   |
| `--ocote-on-primary`        | Texto sobre primario   | `#FFFFFF` | Etiquetas y botones                              |
| `--ocote-on-secondary`      | Texto sobre bosque     | `#FFFFFF` | Etiquetas y botones                              |
| `--ocote-on-warning`        | Texto sobre dorado     | `#1F1A16` | Alertas y chips                                  |
| `--ocote-focus`             | Contorno de foco       | `#2B5B84` | Foco de al menos 2 px con separacion clara       |

### Mapeo SCSS de Angular Material 18.2

- Se adopta Material 3, coherente con `mat.define-theme` ya presente en el scaffold; no mezclar con APIs de paletas Material 2 ni con APIs de futuras versiones.
- F4 define [tokens](../src/_ocote-tokens.scss) y [paletas tonales completas](../src/_ocote-palettes.scss), generadas por el schematic instalado @angular/material:m3-theme18.2 con primary Resina, secondary/tertiary Bosque y neutral Musgo. Incluyen tonos, neutros, neutral-variant y error, no un solo hexadecimal.
- Configuracion conceptual: `color.theme-type = light`, `color.primary = paleta Resina`, `color.tertiary = paleta Bosque`, tipografia y densidad explicitas. Incluir `mat.core()` una sola vez y emitir los temas usados en un solo punto global.
- `secondary` es un rol de diseno; no es una opcion raiz `color.secondary` de `mat.define-theme`. Alinear secondary M3 con Bosque mediante el mapa tonal compatible y los roles de sistema/overrides admitidos en 18.2. Verificarlo en un prototipo compilable, sin depender de una opcion inexistente.
- Material calcula roles a partir de tonos; no se promete que su tono primario generado sea exactamente el hexadecimal de marca. Los tokens de marca mantienen los valores exactos y los roles efectivos/on-colors se documentaran en la matriz visual F4. Ningun override privado `--mdc-*` sin API publica.
- [styles.scss](../src/styles.scss) exporta variables CSS bajo :root, emite mat.core una vez y el tema global; conserva mapas tonales generados y tokens de marca como superficies distintas, no los sobrescribe para forzar un tono. Material, librerias y vistas no mantienen copias independientes. button-overrides/dialog-overrides publicos18.2 limitan container-shape a8px, sin variables privadas.
- Source Sans3 variable autoalojada, base16px/tablas14px, fallback sans-serif, densidad0; jerarquia compacta, sin espaciado negativo ni escalado por viewport. Licencia OFL en [Source-Sans-LICENSE.md](../public/fonts/Source-Sans-LICENSE.md); iconos Material Icons Apache2.0 en [Material-Icons-LICENSE](../public/fonts/Material-Icons-LICENSE). No solicitudes a Google Fonts en runtime.

Matriz efectiva F4 (contraste relativo sRGB):

| Pareja | Contraste | Uso |
| --- | --- | --- |
| Blanco / primary de marca #B85A1E | 4.65:1 | Marca/progreso; no sustituir tono Material |
| Blanco / primary M3 tono40 #9B4505 | 6.47:1 | Accion primaria Material |
| Blanco / secondary y tertiary M3 tono40 #3B6750 | 6.48:1 | Roles Bosque del mapa publico |
| Blanco / Bosque de marca #2E5A44 | 7.89:1 | Navegacion |
| Carbon / blanco; Musgo / Niebla | 17.25:1; 6.85:1 | Texto principal/secundario |
| Blanco / success; blanco / danger | 5.00:1; 5.96:1 | Estado con etiqueta |
| Carbon / warning; foco / blanco | 6.24:1; 7.16:1 | Alerta y contorno3px/separacion blanca2px |

La revision tecnica F4 cubre teclado/foco/dialogos, capturas360/768/1440, fuentes/iconos/imagen y zoom CSS200% sin desbordamiento de pagina. No equivale a auditoria WCAG exhaustiva, lector de pantalla ni aceptacion de negocio; limites en roadmap10.

### Aplicacion y accesibilidad

- Interfaz operativa, no landing promocional. Navegacion estable con Plan, Ejecucion, Analitica, Evaluaciones y Administracion segun permisos. Sin secciones flotantes innecesarias ni tarjetas dentro de tarjetas.
- Tablas con cabeceras semanticas, orden anunciado, paginacion, filtros etiquetados y desplazamiento horizontal contenido. Numeros alineados; originales y fechas vigentes claramente diferenciados.
- Kanban usa superficie secundaria por carril y tarjetas blancas; icono, etiqueta y fecha acompanan el color. Timeline distingue baseline con trazo/patron, actual con barra y cierre con marcador. ECharts usa etiquetas, patrones y tabla equivalente accesible.
- Series categoricas: primary, series-contrast, secondary, accent y danger, con nombres/patrones. Si el color codifica puntualidad o estado, se usa exclusivamente su token semantico; no se asigna danger a una categoria neutra.
- `open` no implica riesgo: En riesgo es una lectura de reprogramacion positiva (`due_date_delta_days > 0`) y se etiqueta Aplazada; no hay prediccion automatica de riesgo en MVP. Bloqueada y vencida usan danger, diferenciadas por icono/texto.
- ECharts resuelve variables con estilos computados y recibe colores concretos al construir/refrescar opciones; no se asume soporte de `var(...)` en canvas. Mismos tokens para CSS de Timeline y componentes del Kanban. Proveer descripcion accesible y alternativa tabular de todos los datos.
- WCAG 2.2 AA: texto normal >= 4.5:1; texto grande >= 3:1; controles/indicadores esenciales y foco >= 3:1 respecto a adyacentes. Blanco sobre primary, secondary, success y danger se verificara; dorado siempre con texto oscuro. Dorado sobre blanco y `--ocote-border` no bastan como unica frontera de un control o serie esencial: agregar borde oscuro, patron o etiqueta.
- En botones sobre primario el foco tendra separacion blanca antes del contorno azul. Estado no disponible se comunica tambien semanticamente. No se reduce opacidad de texto informativo hasta perder contraste. Tooltips no son la unica etiqueta accesible; Material Icons para acciones familiares con nombre accesible.
- Respetar `prefers-reduced-motion`; animaciones breves de transicion sin ocultar errores. Errores de formulario junto al campo y resumen enfocable. Objetivos tactiles al menos 24x24 CSS px, preferentemente 44x44 en movil.

## 6. Contrato API propuesto v1

Base `/api/v1`, JSON UTF-8, nombres `snake_case`, UUID como cadenas, instantes ISO 8601 UTC y fechas civiles separadas. Es contrato objetivo, no API existente. `Authorization: Bearer <access_token>` salvo login/refresh y comprobacion publica minima de salud. Esquemas Pydantic v2 con campos extra prohibidos, sin coerciones ambiguas de booleanos/numeros; fechas UUID y timestamps se validan desde sus representaciones JSON estandar.

`title` 1..200 caracteres, `description` hasta 10000, nombres 1..120, `reason` 10..2000, email normalizado, password 12..128 sin truncar ni recortar espacios. Campos calculados, `original_due_date`, `completed_at`, actor y timestamps son solo lectura. El esquema rechaza intentos de asignarlos.

Listados: `limit` 1..100, predeterminado 50, cursor opaco y orden estable `(created_at, id)` salvo orden de catalogo `(position, id)`; el cursor vincula filtros/orden. Respuesta `items`, `next_cursor`, `total`; `total` siempre restringido por alcance. Filtros no autorizados no amplian visibilidad. Listas Kanban usan `stage_id` y paginacion por carril. Fechas de filtro de compromiso siempre sobre `original_due_date`; ventanas Timeline filtran por solapamiento de start_date/due_date sin alterar la cohorte analitica.

### Operaciones principales

| Metodo y ruta relativa                                                                                                 | Entrada / resultado                                                                                      | Permiso                                                          |
| ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| POST `/auth/login`                                                                                                     | email, password; access token, perfil y cookie refresh; 200                                              | Publico limitado                                                 |
| GET `/auth/csrf`                                                                                                       | Cookie refresh valida y origen verificado; csrf_token; 200                                               | Recuperacion de CSRF tras recarga, sin emitir credenciales       |
| POST `/auth/refresh`                                                                                                   | Cookie + CSRF; token nuevo y cookie rotada; 200                                                          | Sesion valida                                                    |
| POST `/auth/logout`                                                                                                    | Cookie + CSRF; revoca familia y limpia cookie; 204                                                       | Idempotente                                                      |
| GET `/auth/me`                                                                                                         | Perfil, rol y alcance; 200                                                                               | Autenticado                                                      |
| POST `/auth/change-password`                                                                                           | current_password, new_password; revoca sesiones; 204                                                     | Usuario propio                                                   |
| GET/POST `/departments`, `/users`, `/workflow-stages`                                                                  | Lista / alta; 200 / 201                                                                                  | Admin; proyecciones operativas separadas en /catalogs            |
| PATCH `/departments/{id}`, `/users/{id}`, `/workflow-stages/{id}`                                                      | Campos autorizados + expected_version; 200                                                               | Admin                                                            |
| GET/POST `/workflow-transitions`                                                                                       | Lista / alta de from_stage_id, to_stage_id, allowed_roles; 200 / 201                                     | Admin; aristas operativas minimas por /catalogs/workflow         |
| PATCH `/workflow-transitions/{id}`                                                                                     | allowed_roles, is_active, expected_version; 200                                                          | Admin                                                            |
| POST `/workflow` | Grafo completo por code; reason y expected_version en filas existentes; 201 | Admin; configuracion atomica sin seeds ni eliminaciones |
| POST `/users/{id}/reset-password` | new_password, expected_version, reason; 204, revoca todas las sesiones | Admin; canal seguro, sin password en logs |
| GET `/catalogs/departments`, `/catalogs/assignees`, `/catalogs/workflow`, `/catalogs/priorities`, `/catalogs/horizons` | Proyecciones minimas elegibles; 200, no metadata administrativa                                          | Autenticado segun rol/alcance; C sin catalogo de personas ajenas |
| GET/PATCH `/settings/{key}`                                                                                            | value, reason, expected_version al editar; 200                                                           | Admin; RN-07, sin secretos                                       |
| GET `/settings`, `/priorities`, `/horizon-types`                                                                       | Listado administrativo; 200                                                                              | Admin                                                            |
| POST `/priorities`, `/horizon-types` | code, name, position, reason; 201 | Admin; horizontes solo cinco codes RN-01 |
| POST `/settings` | key permitida, value tipado, reason; 201 | Admin; sin claves libres ni defaults |
| POST `/priorities/reorder`, `/horizon-types/reorder` | items id/position/expected_version, reason; 200 | Admin; atomico, 409 sin cambios parciales |
| GET `/configuration-status` | Faltantes de settings/horizontes/normal/grafo y complete; workflow_error contiene codigo de validacion o null si el grafo es valido; 200 | Admin; no crea datos ni habilita F3 con grafo incompleto |
| PATCH `/priorities/{id}`, `/horizon-types/{id}`                                                                        | name, position, is_active, reason, expected_version; 200                                                 | Admin; code/id/semantica inmutables                              |
| GET `/releases`, `/releases/{id}`, `/audit-events` | Metadata sanitizada, limit 1..100/cursor UUID/next_cursor; 200 | Admin, solo lectura; sin ruta/hash/credencial de backup. /release-history es alias local |
| GET/POST `/annual-plans`                                                                                               | Lista / title, horizon_type, start_date, due_date; 200 / 201                                             | GET admin/gerente/lider filtrado; POST admin/gerente; C 403      |
| GET `/annual-plans/{id}`, `/objectives/{id}`                                                                           | Detalle filtrado; 200                                                                                    | Admin/gerente o lider propio; C sin acceso al modulo (403)       |
| PATCH `/annual-plans/{id}`                                                                                             | title, expected_version; 200                                                                             | Admin o gerente                                                  |
| POST `/annual-plans/{id}/period-changes`                                                                               | horizon_type, start_date, due_date, reason, expected_version; 200                                        | Admin o gerente                                                  |
| POST `/annual-plans/{id}/status-changes`                                                                               | status, expected_version; 200                                                                            | Admin o gerente                                                  |
| GET/POST `/objectives`                                                                                                 | Lista / annual_plan_id, department_id, title, description, horizon_type, start_date, due_date; 200 / 201 | GET admin/gerente/lider propio; POST admin/gerente; C 403        |
| PATCH `/objectives/{id}`                                                                                               | title, description, expected_version; 200                                                                | Admin o gerente                                                  |
| POST `/objectives/{id}/period-changes`                                                                                 | horizon_type, start_date, due_date, reason, expected_version; 200                                        | Admin o gerente                                                  |
| GET/POST `/tasks`                                                                                                      | Lista / alta de tarea; 200 / 201                                                                         | Alcance / admin o lider                                          |
| GET/PATCH `/tasks/{id}`                                                                                                | Detalle / title, description, priority_id, expected_version; 200                                         | Alcance / admin o lider                                          |
| POST `/tasks/{id}/assignments`                                                                                         | assignee_id, reason, expected_version; 200                                                               | Admin o lider                                                    |
| POST `/tasks/{id}/stage-transitions`                                                                                   | to_stage_id, reason opcional, evidence_ids, expected_version; 200                                        | Admin, lider o asignado segun arista                             |
| POST `/tasks/{id}/due-date-changes`                                                                                    | due_date, reason, expected_version; 200                                                                  | Admin o gerente                                                  |
| POST `/tasks/{id}/schedule-changes`                                                                                    | start_date, reason, expected_version; 200                                                                | Admin o lider                                                    |
| GET/POST `/tasks/{id}/subtasks`                                                                                        | Lista / title, start_date, due_date, expected_version del padre; 200 / 201                               | Alcance / admin o lider                                          |
| PATCH `/subtasks/{id}`                                                                                                 | title, expected_version, expected_task_version; 200                                                      | Admin o lider                                                    |
| POST `/subtasks/{id}/completion`                                                                                       | expected_version, expected_task_version; 200                                                             | Admin, lider o asignado                                          |
| POST `/subtasks/{id}/due-date-changes`                                                                                 | due_date, reason, expected_version, expected_task_version; 200                                           | Admin o gerente                                                  |
| POST `/subtasks/{id}/schedule-changes`                                                                                 | start_date, reason, expected_version, expected_task_version; 200                                         | Admin o lider                                                    |
| POST `/tasks/{id}/due-date-requests`                                                                                   | proposed_due_date, reason, expected_task_version; 201                                                    | Admin/gerente/lider propio                                       |
| POST `/subtasks/{id}/due-date-requests`                                                                                | Igual + expected_subtask_version; 201                                                                    | Admin/gerente/lider propio                                       |
| GET `/due-date-requests`, `/due-date-requests/{id}`                                                                    | Solicitudes/detalle segun alcance; 200                                                                   | Admin/gerente global; lider departamento; C 403                  |
| POST `/due-date-requests/{id}/approve`, `/due-date-requests/{id}/reject`                                               | reason, expected_version de solicitud; approve verifica versiones capturadas de destino; 200             | Admin/gerente; approve nunca solicitante                         |
| POST `/due-date-requests/{id}/cancel`                                                                                  | reason, expected_version; 200                                                                            | Solicitante lider propio o admin/gerente                         |
| POST `/tasks/{id}/evidence`                                                                                            | multipart file, expected_version del padre; 201                                                          | Admin, lider o asignado                                          |
| GET `/tasks/{id}/evidence`, `/evidence/{id}/content`                                                                   | Metadatos / descarga protegida; 200                                                                      | Mismo alcance de tarea                                           |
| GET `/tasks/{id}/history`                                                                                              | Eventos paginados; 200                                                                                   | Mismo alcance de tarea                                           |
| GET `/analytics/summary`, `/analytics/series`                                                                          | plan, departamento, responsable, periodo; 200                                                            | Admin/gerente global, lider departamento; C 403                  |
| GET/POST `/evaluations`                                                                                                | Lista / plan, departamento, periodo; 200 / 201                                                           | Admin o gerente; lider solo finales propias                      |
| GET `/evaluations/{id}`                                                                                                | Foto, items y summary; 200                                                                               | Igual alcance de evaluaciones                                    |
| POST `/evaluations/{id}/recalculate`                                                                                   | expected_version; 200                                                                                    | Admin o gerente, solo draft                                      |
| POST `/evaluations/{id}/finalize`                                                                                      | summary, expected_version; 200                                                                           | Admin o gerente, solo draft                                      |
| POST `/exports/tasks`                                                                                                  | format json/csv y filtros tipados; 200 archivo, 413 exceso de limite                                     | Admin/gerente global, lider departamento; C 403                  |
| POST `/exports/evaluations/{id}`                                                                                       | format json/csv; 200 archivo desde foto final                                                            | Igual alcance de lectura de evaluaciones; C 403                  |

No se exponen DELETE de dominio en v1. Los POST de comandos no son automaticamente idempotentes: clientes no reintentan a ciegas; tras respuesta perdida consultan recurso/version/historial. El control de version evita duplicar mutaciones del mismo recurso. Logout es la excepcion idempotente explicita.

Los campos `position` de catalogos, etapas y reordenamientos son enteros estrictos entre 0 y 2147483647, compatibles con INTEGER PostgreSQL. Strings, booleanos, fracciones y valores fuera de rango devuelven 422 antes de escribir; no se truncan ni convierten ambiguamente. Las posiciones repetidas se rechazan conforme al contrato de cada comando.

En formularios cuyo comando admite `reason`, el motivo justifica la operacion actual: comienza vacio y no se precarga desde la creacion ni desde historia/auditoria. Se valida tras quitar espacios exteriores (10..2000 caracteres) y se envia separado de la informacion historica de solo lectura. Los demas datos vigentes si se conservan al editar. Un 409 mantiene los valores, bloquea el reenvio y exige descarte/recarga explicitos; una recarga secundaria no elimina ese bloqueo. No se agrega `reason` a DTO que no lo admiten ni se normalizan contrasenas.

Tablas F4/F5: administracion, planes, objetivos, tareas, solicitudes, subtareas y tabla de Timeline presentan cinco filas por defecto y selector 5/10/20/50. Es estado local de interfaz, no un parametro ni dato de negocio insertado en BD. Cada consulta envia el `limit` elegido y conserva filtros; cambiar tamano/filtros reinicia cursores. Navegacion primera/anterior/siguiente con historial local de cursores y numero de pagina, sin inventar total ni ultima pagina. Los controles se deshabilitan durante carga, tienen etiquetas/tooltips y anuncio de pagina para tecnologias de asistencia; se adaptan a 360px CSS y conservan scroll interno de tablas anchas. Paginar subtareas no modifica tarea, version ni avance; Timeline conserva tabla y grafico sobre la misma pagina. Selectores/reordenamientos siguen recorriendo catalogos completos autorizados mediante paginas de hasta 100; no se limitan a cinco opciones. Kanban conserva sus carriles y limite 25; historia y evidencia siguen siendo listas con su paginacion existente, no tablas nuevas.

Etapas crea exclusivamente registros mediante POST `/workflow-stages`; Transiciones usa POST `/workflow-transitions`. Sin tareas ni evaluaciones, las altas/ediciones administrativas pueden dejar temporalmente el grafo incompleto: inicial abierta activa sin requisitos, a lo sumo una inicial/terminal activa, extremos/roles validos y restricciones de BD siempre vigentes. `/configuration-status` informa `workflow_valid=false` y la configuracion operativa falla cerrada hasta tener inicial, terminal y camino a terminal para cada etapa activa. Tras el primer uso no se permite dejar un grafo invalido; se prepara un cambio completo mediante la configuracion atomica existente. POST `/workflow` sigue exigiendo grafo completo y versionado, accesible solo desde Configuracion; nunca se mezcla en los modales de Etapas/Transiciones. No se crean filas ni requisitos por defecto.

Altas de catalogo: departamento recibe `code`, `name`; usuario recibe `email`, `display_name`, `password`, `role`, `department_id` nullable segun rol; etapa recibe `code`, `name`, `position`, `kind`, `is_initial`, `requires_evidence`, `requires_reason`. Banderas omitidas usan defaults documentados y no se permite cambiar identificadores estructurales mediante PATCH. En usuarios, PATCH admite `display_name`, `role`, `department_id`, `is_active` y `expected_version`, nunca password_hash/token_version; provision de password solo en alta y cambio por endpoint especifico. Cambiar rol/alcance revoca sesiones.

CRUD /departments, /users, /workflow-stages y /workflow-transitions es administrativo; la lectura operativa minima se separa en /catalogs, no abre esos CRUD a todos. Respuestas administrativas devuelven id/timestamps/version y campos permitidos, nunca password/hash, token_version o sesion. Assignees para lider: solo id/display_name/departamento elegibles; C solo identidad propia. /catalogs/departments para C no enumera otros departamentos. GET /auth/me incluye identidad, role, department_id y permisos efectivos.

Alta de tarea F3 acepta priority_id activo opcional: omitirlo resuelve normal obligatorio; detalle devuelve id/code/name y version de prioridad. PATCH no admite null ni altera prioridad de subtareas. Cambios de catalogo/setting incluyen reason; reordenamiento atomico con items id/position/expected_version (POST /priorities/reorder o /horizon-types/reorder), admin y lock global, sin renumeracion silenciosa. F2 permite altas explicitas de los cinco horizontes y cuatro claves settings tipadas, no otros codes/claves. Instalacion vacia no habilita operaciones F3.

Solicitudes: respuesta contiene destino, propuesta/fecha previa, versiones capturadas, solicitante, estado y decision segun arquitectura; id/version propios. Aprobar devuelve request y task (y subtask si procede) actualizados; rechazar/cancelar solo request. Consultar tras respuesta perdida antes de reintentar. Exportaciones no son API de integracion: corte, limites, CSV seguro, cabeceras, auditoria y exclusiones normativas en seccion 6 de guia de entrega.

### Ejemplos normativos

Alta de plan personalizado (POST `/annual-plans`); la respuesta 201 incluye estos campos, UUID, status=draft, timestamps y version=1:

```json
{
  "title": "Cierre e inicio de operacion",
  "horizon_type": "custom",
  "start_date": "2027-11-15",
  "due_date": "2028-02-20"
}
```

Alta de objetivo contenido en ese plan (POST `/objectives`); los UUID son ilustrativos:

```json
{
  "annual_plan_id": "77777777-7777-4777-8777-777777777777",
  "department_id": "55555555-5555-4555-8555-555555555555",
  "title": "Conciliar cierre de diciembre",
  "description": "Validacion operativa del periodo",
  "horizon_type": "monthly",
  "start_date": "2027-12-01",
  "due_date": "2027-12-31"
}
```

Cambio explicito de periodo de objetivo (POST `/objectives/{id}/period-changes`); devuelve recurso completo con version incrementada y evento auditado, sin mover tareas:

```json
{
  "horizon_type": "custom",
  "start_date": "2027-12-01",
  "due_date": "2028-01-15",
  "reason": "Ampliar ventana operativa para conciliacion de cierre",
  "expected_version": 1
}
```

Plan/objetivo sin alguno de los tres campos temporales, enum desconocido o rango invalido devuelven 422 VALIDATION_ERROR. No se acepta un year aislado como sustituto de fechas; no hay clientes desplegados de ese contrato anterior. Si existiera una instalacion legacy, se aplicaria la transicion expand/backfill/contract de arquitectura, nunca conversion implicita destructiva.

Alta de tarea en otro objetivo cuyo intervalo contiene marzo de 2027, no el objetivo de diciembre anterior; el servidor asigna etapa inicial y copia compromiso original:

```json
{
  "objective_id": "11111111-1111-4111-8111-111111111111",
  "title": "Conciliar inventario de marzo",
  "description": "Conciliacion y validacion departamental",
  "assignee_id": "22222222-2222-4222-8222-222222222222",
  "start_date": "2027-03-01",
  "due_date": "2027-03-10"
}
```

Respuesta 201 (extracto del recurso; el detalle completo tambien incluye objetivo y timestamps):

```json
{
  "id": "33333333-3333-4333-8333-333333333333",
  "stage_id": "44444444-4444-4444-8444-444444444444",
  "priority": {
    "id": "88888888-8888-4888-8888-888888888888",
    "code": "normal",
    "name": "Normal",
    "version": 1
  },
  "original_due_date": "2027-03-10",
  "due_date": "2027-03-10",
  "completed_at": null,
  "progress_percent": 0,
  "punctuality_status": "pending",
  "baseline_punctuality_status": "pending",
  "is_overdue": false,
  "pending_closure": false,
  "due_date_delta_days": 0,
  "delay_days": 0,
  "baseline_delay_days": 0,
  "version": 1
}
```

Cambio de compromiso (POST `/tasks/{id}/due-date-changes`):

```json
{
  "due_date": "2027-03-15",
  "reason": "Proveedor entregara conciliacion el siguiente lunes",
  "expected_version": 1
}
```

Devuelve el recurso actualizado con `version=2`, fecha original intacta y evento `due_date_changed`. En operaciones de subtarea se devuelve `{ "subtask": {...}, "task": {...} }` para sincronizar versiones y avance; la creacion usa 201. Comandos de tarea devuelven la tarea; alta de evidencia devuelve `{ "evidence": {...}, "task": {...} }` con 201. Las respuestas GET no incrementan versiones.

Login 200 (el refresh token NO aparece en JSON):

```json
{
  "access_token": "<jwt-access>",
  "token_type": "bearer",
  "expires_in": 600,
  "csrf_token": "<valor-csrf-no-autenticante>",
  "user": {
    "id": "22222222-2222-4222-8222-222222222222",
    "role": "lider",
    "department_id": "55555555-5555-4555-8555-555555555555"
  }
}
```

Refresh devuelve el mismo contrato, `user` actualizado y CSRF vigente ligado a familia/expiracion; rotar cookie no obliga cambiar el valor CSRF. Evaluacion F6 recibe `annual_plan_id`, `department_id`, `period_start`, `period_end`; respuesta 201 incluye `status=draft`, `snapshot_at`, `metrics`, `items`, `version`. Analitica devuelve `generated_at`, `organization_timezone`, filtros efectivos, `task_count`, `completed_count`, `baseline_on_time_count`, tasas y avance; series devuelve `items` por mes/departamento con los mismos denominadores. Sin datos conserva conteos0/porcentajes null; no implementado por F2.

### Errores uniformes

Todas las respuestas de error de API usan `application/problem+json` con `type`, `title`, `status`, `code`, `detail`, `instance`, `request_id` y `errors` opcional; sin stack traces. Adaptar tambien errores de validacion de FastAPI y limites del proxy. `WWW-Authenticate: Bearer` en 401.

```json
{
  "type": "urn:ocote:problem:version-conflict",
  "title": "Conflicto de version",
  "status": 409,
  "code": "VERSION_CONFLICT",
  "detail": "La tarea cambio; recarga antes de continuar.",
  "instance": "/api/v1/tasks/33333333-3333-4333-8333-333333333333/stage-transitions",
  "request_id": "66666666-6666-4666-8666-666666666666"
}
```

| HTTP      | Codigos estables previstos                                                                                                | Tratamiento                                                                  |
| --------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 400       | `INVALID_CURSOR`, `INVALID_FILTER`                                                                                        | Corregir peticion                                                            |
| 401       | `INVALID_CREDENTIALS`, `TOKEN_EXPIRED`, `SESSION_REVOKED`, `REFRESH_REUSED`                                               | Login generico sin enumerar cuentas; reiniciar sesion cuando aplique         |
| 403       | `FORBIDDEN`, `CSRF_FAILED`                                                                                                | No conceder accion                                                           |
| 404       | `RESOURCE_NOT_FOUND`                                                                                                      | Inexistente o fuera de alcance                                               |
| 409       | `VERSION_CONFLICT`, `DUPLICATE_RESOURCE`, `INVALID_TRANSITION`, `PLAN_LOCKED`, `DEPENDENCY_CONFLICT`, `EVALUATION_LOCKED` | Refrescar o resolver conflicto; no reintento automatico                      |
| 413 / 415 | `FILE_TOO_LARGE`, `EXPORT_TOO_LARGE` / `UNSUPPORTED_MEDIA_TYPE`                                                           | Rechazar evidencia excesiva/invalida o exportacion sobre limite, sin truncar |
| 422       | `VALIDATION_ERROR`, `EVIDENCE_REQUIRED`, `REASON_REQUIRED`                                                                | errors con field y message; no eco de secretos                               |
| 429       | `RATE_LIMITED`                                                                                                            | Retry-After y espera controlada                                              |
| 500 / 503 | `INTERNAL_ERROR` / `SERVICE_UNAVAILABLE`                                                                                  | Mensaje seguro y request_id para soporte                                     |

## 7. Condicion de cierre documental

El comportamiento del MVP, sus criterios de prueba y sus limites estan especificados. El cierre documental no certifica implementacion, accesibilidad real ni seguridad operativa. Solo se abre una fase al satisfacer las confirmaciones D01-D08 que le correspondan y la Definition of Done de su predecesora.
