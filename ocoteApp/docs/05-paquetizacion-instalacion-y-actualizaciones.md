# OCOTE: paquetizacion, instalacion y actualizaciones

Version documental: 2.1 con F6 local del2026-11-25. Especificacion objetivo, NO instalador/despliegue certificado. Backend/UI F6 implementados/migrados local/sintetico con exports internos; cierre operativo F5/aceptacion/configuracion y ClamAV reales pendientes. Sin paquete firmado/ocote-admin/actualizador cliente ni F7 autorizado. Seccion9 amplia entrega empresarial futura sin archivos operativos; no migracion ejecutada. [Estado/excepciones/evidencia F6](03-estado-actual-y-roadmap.md#17-analitica-evaluaciones-y-exports-f6-local-2026-11-25). El ensayo local no homologa protocolo cliente ni produccion/nube.

## 1. Autoridad, alcance y modalidades

Leer [SDD](01-spec-driven-development.md), [arquitectura/modelo](02-arquitectura.md), [roadmap](03-estado-actual-y-roadmap.md) y [entorno de desarrollo](04-entorno-y-portabilidad.md). Este documento es fuente unica del protocolo de entrega/actualizacion del cliente; la guia 04 conserva el arranque portable de desarrollo. Reglas y permisos no cambian por modalidad.

| Modalidad objetivo | Topologia                                                                                                 | Condicion de soporte                                                                     |
| ------------------ | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| A local            | Proxy HTTPS, SPA compilada, FastAPI y PostgreSQL 18 portable Windows o contenedor con volumen persistente | SO/arquitectura, distribucion/minor PG, gestor de servicios y disco homologados en F1/F7 |
| B gestionada       | Proxy/SPA/API en host aprobado y PostgreSQL 18 remoto/gestionado por red privada                          | Proveedor, region, TLS/CA, extension, limites, backup y restore homologados en F1/F7     |

Ninguna incluye BD dentro de Angular ni acceso SQL desde el navegador. Nube no exige llevar frontend/API a nube ni usar multiples origenes. Solo HTTPS publico; servicios y BD privados. Un despliegue puede ser offline respecto a Internet si distribuye dependencias/certificados/actualizaciones de seguridad por canal autorizado.

Estado vigente segun acta F6: PG18.4 Windows local/head20261125_0005,19 tablas dominio/20 contando Alembic y seis releases terminales; datos operativos/bootstrap/configuracion previos conservados, evidencia/evaluaciones/items vacios al cierre. Roles separados y backup/restore/migracion/no-op F6 registrados, CREATE temporal revocado. No homologa cliente/contenedor/otro SO/nube/perdida de host; protocolo cliente es contrato y esta tarea no reconecta BD.

F4 aporta UI/sesion/admin/operacion; F5 Kanban/Timeline/evidencia y F6 analitica/evaluaciones/exports internos. Cinco revisiones0001..0005 y herramientas de sus evidencias permanecen inmutables. Bundle con fuentes/licencias locales, proxy HTTPS autofirmado solo loopback. Operador configura explicitamente, sin defaults/demos; pruebas de navegador/scanner sinteticos no equivalen a aceptacion ni antivirus real. F5 conserva raiz privada/ClamAV reales pendientes/cargas cerradas y cierre operativo pendiente. Solo evolucion documental F7..F12, sin desarrollo ni ampliacion de exposicion autorizados.

## 2. Paquete de cliente reproducible

Repositorio fuente y paquete distribuible son distintos. CI construira desde commit/lock revisados, sin depender de node_modules o .venv del desarrollador. Angular permanece en raiz del repo; el artefacto separa componentes sin mover su fuente.

| Contenido objetivo    | Requisito                                                                                                                                                        |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| frontend/             | Solo salida Angular de build produccion verificada; assets/fonts licenciados y locales, sin secretos ni sourcemaps publicos no aprobados                         |
| backend/              | Paquete Python/app, pyproject y lock, Alembic/env/versions, seeds y herramienta administrativa versionados; sin .venv copiada                                    |
| runtime/ o imagenes   | Wheels/dependencias Python 3.12 por SO/arquitectura o imagenes fijadas por digest; no reutilizar wheels Windows en Linux                                         |
| deploy/               | Plantillas proxy/TLS, servicio o contenedores/volumenes, healthchecks y configuracion sin secretos; instalacion sin privilegios excesivos                        |
| manifest.json y firma | Version app, commit, hashes, destino/SO, revisiones origen/destino, dependencias, esquema/config y compatibilidad; firma verificable por clave confiable externa |
| SBOM/licencias        | Inventario de dependencias, procedencia, licencias y avisos de redistribucion; incluir PostgreSQL solo si distribucion/legal lo aprueban                         |
| contrato de configuracion | Registry tipado/esquema de BD y asistente; sin .env/YAML operativo para cliente. Bootstrap conexion/sellado generado por instalador; claves/CA materializadas automaticamente bajo ACL cuando dependencia lo requiera |
| docs/ y evidencia     | Manuales, checklist de instalacion/upgrade/restore, pruebas de release, cambios/riesgos y soporte; sin datos de cliente                                          |

Excluir .git, node_modules, .venv, caches, data/logs/backups, evidencias privadas, dumps, .env, passwords, claves JWT/TLS, certificados privados y tokens. Nunca distribuir cluster del desarrollador ni credencial publica holamundo. Binarios PG se obtienen por canal aprobado o paquete opcional separado y verificado, no se extraen del checkout local.

Build futuro: npm ci y npm run build con lock revisado, Python con lock y hashes, tests unitarios/integracion/contrato, SAST/analisis de dependencias y SBOM, escaneo de secretos y empaquetado. Node/npm son herramientas de construccion, no runtime obligatorio del cliente. Python debe estar instalado o incluido como runtime/imagen aprobado; no instalar paquetes desde Internet al arrancar. Resolver D07 antes de certificar Angular 18; un build exitoso no demuestra soporte de seguridad.

Ejemplo de estructura del manifest, ilustrativo y no una release publicada (hashes/revisiones deben reemplazarse en el build):

```json
{
  "application": "OCOTE",
  "application_version": "0.1.0",
  "commit": "<commit-inmutable>",
  "target": "windows-x64",
  "python": "3.12",
  "postgresql_major": 18,
  "database_name": "ocoteAppDatabase",
  "compatible_source_revisions": [null, "<revision-origen>"],
  "target_revision": "<head-unica>",
  "settings_schema_version": 1,
  "seed_version": "<version>",
  "files": [{ "path": "backend/package.whl", "sha256": "<sha256>" }],
  "contingency_runbook": "docs/05-paquetizacion-instalacion-y-actualizaciones.md"
}
```

Cada archivo/digest se verifica contra manifest firmado, firma contra clave de confianza aprovisionada por canal distinto. Un checksum adjunto a un paquete no autentica por si solo al emisor. Conservar artefactos anterior/nuevo inmutables fuera de datos persistentes. SemVer de aplicacion no sustituye revision Alembic ni compatibilidad de datos.

## 3. Preflight comun y responsabilidades

Gerencia aprueba D01-D04/D08; seguridad/legal D05; TI/operacion D06/D07 con lider tecnico. Registrar nombres, fechas y evidencia, no firmas ficticias. Antes de instalar: hardware/capacidad, SO, zona IANA, nombre organizacion, DNS/origen HTTPS, responsables, region/residencia, politicas de retencion, RPO/RTO y plan de soporte. La base F1 de seccion 3.1 no sustituye esas aprobaciones productivas ni constituye un SLA.

- Verificar firma/checksums, version/destino, espacio para paquete+backup+restore aislado+backfill, acceso a secretos y conectividad. Registrar identidad del cliente/instancia/base exacta, nunca inferir por nombre solamente; operador confirma endpoint y entorno.
- Identidad SO dedicada para API y ACL privadas; PostgreSQL separado cuando corresponda. Puertos API/BD privados; proxy unico origen y SPA fallback solo fuera de /api. DNS, TLS valido, NTP, disco y alertas habilitados.
- Provisionar rol propietario sin login si procede, rol migrador con DDL acotado al esquema de app, rol runtime sin DDL/superusuario/creacion de extensiones y permisos minimos de backup/operacion probados. Retirar CREATE de PUBLIC en esquema aplicativo. Ningun navegador/usuario de negocio recibe credencial SQL. RLS no se presume implementada: API es unica entrada runtime y aplica politicas.
- Provisionar secretos unicos por entorno y rol por canal seguro, no argumentos de CLI/historial ni chat: prompt protegido, descriptor o gestor de secretos/archivo con ACL. DSN runtime y migracion separados, passwords SCRAM donde aplique, claves RS256/JWT y TLS con rotacion. No .env servido por proxy ni valores por defecto productivos.
- Comprobar PostgreSQL 18 y minor homologada, encoding UTF8, timezone tecnica UTC, permisos, btree_gist y limites. Nombre exacto ocoteAppDatabase; alta administrativa autorizada con identificador correctamente citado, sin renombrar/copiar/borrar ocote u otras bases. No crear base alternativa para sortear errores.
- Mantenimiento sin escritores para instalar/actualizar esquema; un solo operador/herramienta mantiene lock persistente. Preflight sin cambios por defecto; inicializar/aprovisionar requiere confirmacion explicita del destino vacio. Nunca initdb como reparacion de una falla.

Interfaz administrativa propuesta, NO ejecutable actualmente: ocote-admin preflight (solo verifica), install (alta sobre destino vacio confirmado), upgrade (seccion 7), verify (revision/integridad/smoke), bootstrap-admin (primer usuario) y restore-verify (solo destino aislado aprobado). Cada accion debe fallar cerrada, retornar codigo no cero, request_id y diagnostico sanitizado. Sin prompts de secretos enviados a agentes y sin elevacion silenciosa. F1 prepara base/automatizacion, F2 bootstrap de usuario y F7 valida paquete integral.

### 3.1 Base aprobada de privacidad y recuperacion D05/D06

Aprobacion expresa del titular del proyecto el 2026-11-24 como base F1 y objetivos de diseno, NO como homologacion legal, seguridad productiva o implementacion de F5/F7. Responsable operativo y de seguimiento: **LUIS ANGEL VALLEJO - DESARROLLADOR**. La zona oficial D01 es **America/Mexico_City**, exclusivamente entrada inicial de bootstrap segun RN-07, nunca override runtime de system_settings.

| Ambito | Politica aprobada y puerta de implementacion |
| ------ | ------------------------------------------ |
| Clasificacion/minimizacion | Usuarios/asignaciones/ejecucion/evaluaciones son informacion interna/personal restringida por rol Y alcance; evidencia/backups potencialmente sensibles. No datos reales en F1-F5 local. Sin datos extra ni contenido de archivos/tokens/DSN/passwords/cuerpos en logs. |
| Evidencia privada | Volumen u object storage privado fuera del directorio publico y de releases, claves generadas por servidor, minimo privilegio y descarga autenticada/autorizada. PDF/PNG/JPEG hasta 10 MiB, verificar extension/MIME/firma y SHA-256 sin considerar eso prueba antimalware. No enlaces publicos permanentes ni nombres/rutas elegidos por el cliente. |
| Cuarentena y escaneo | Antes de habilitar cargas F5, probar antivirus mantenido: cuarentena privada no descargable/publicable ni valida para completar tarea hasta limpio confirmado. Error/timeout/indisponibilidad/desconocido: fail-closed, evidencia tecnica sanitizada y tratamiento por operador autorizado, sin fallback. Adaptador F5 implementado; configuracion/servicio reales pendientes, dobles sinteticos no los certifican. |
| Cifrado y custodia | Para datos reales, cifrado en reposo de evidencia/backups y en transito cuando cruza host, claves separadas con rotacion y acceso auditado. Probar restauracion con sus claves. Los dumps tecnicos locales actuales tienen ACL privada, NO cifrado ni copia off-host; no trasladar a ellos datos reales ni afirmar cumplimiento productivo. |
| Historia y retencion | No purga automatica ni borrado/reescritura de originales, task_history, audit_events, solicitudes/releases terminales, fotos finales o evidencia. Antes de produccion, seguridad/legal/negocio fijan plazos por categoria, residencia, obligaciones y tratamiento de solicitudes de acceso/supresion; no inventar un plazo legal ni prometer CRUD destructivo. Mantener acceso restringido durante conservacion. |
| Respaldos | Diarios y antes de cada release; retencion minima 30 dias, sin habilitar purgas en esta tarea. Conjunto consistente BD+evidencia y configuracion, manifest/hash, cifrado/copia fuera del dominio de fallo y claves por canal separado antes de datos reales. Fallo de respaldo o restore previo bloquea migracion conforme seccion 7. Programacion, copia off-host y alertas aun no implementadas. |
| Recuperacion | RPO <=24 h y RTO <=4 h aprobados como objetivos de diseno, no SLA ni resultados de produccion. Restore aislado mensual y por release, con revision, integridad, historia, archivos y duracion documentadas. El ensayo local de 0.482 s de la seccion 7 del roadmap prueba solo recuperacion logica de dos tablas en el mismo cluster, no fallo de host, carga o RPO operacional. |
| Continuidad | Excepcion **sin suplente hasta 2026-12-24**, conservada por F5 solo local/sintetico; sustituto inicialmente propuesto coincidia con responsable. Sin responsable suspender migraciones/restores, no delegar credenciales informalmente. Designar/capacitar persona/cargo independiente antes de vencer o de datos reales/produccion. |

Runbook/evidencias en [backend/README.md](../backend/README.md#evidencias-y-vistas-f5) y [F5](03-estado-actual-y-roadmap.md#11-kanban-timeline-y-evidencias-f5-local). No comandos historicos F1-F3 ni repetir apply F5 sobre origen0004. f5_local hizo ensayo restaurado previo/no-op origen y cuatro backups/restores, sin seeds ni archivos publicados, no release firmada. Fallo conserva mantenimiento/bitacora, sin reset. API/escritores deben detenerse por operador: herramienta rechaza sesiones ajenas y no las termina. Evidencia publicada futura exige backup/restore coherente BD+archivos adicional; dump F5 vacio de archivos no lo acredita. Almacen fuera del checkout, cuarentena y adaptador ClamAV fail-closed existen pero servicio/configuracion reales pendientes; sin muestras no confiables/datos reales bajo excepcion. F6/F7 exigen autorizacion nueva.

## 4. Instalacion A: PostgreSQL local

1. TI obtiene PostgreSQL 18 para SO/arquitectura homologados y verifica firma/checksum, permisos y licencia. Elegir portable como servicio de usuario dedicado o imagen fijada por digest con volumen persistente; no montar data en carpeta sincronizada. Usuario de servicio sin administrador; control de inicio/apagado y recuperacion documentado.
2. Solo si no existe cluster y destino esta confirmado vacio: inicializacion expresa con password fuerte por prompt y SCRAM. Nunca trust, password de ejemplo, borrar PID o reutilizar datos de otro major. Si existe cluster/base, detener el flujo de instalacion nueva y seguir inventario/actualizacion o recuperacion autorizada.
3. Configurar loopback/interfaz privada, HBA minimo y firewall. Si BD cruza host, TLS verify-full/CA; para mismo host restringido loopback se admite conexion local sin TLS solo con aprobacion de seguridad/ACL. No publicar 5432 al mundo ni en contenedor por defecto; volumen no equivale a backup.
4. Provisionar roles/base exacta mediante administracion autorizada, nunca con runtime. Verificar identidad, UTF8, conectividad por cada rol, btree_gist y restricciones. No usar init-dev del repositorio para instalacion productiva: es exclusivamente desarrollo con credencial publica.
5. Instalar paquete inmutable, configurar secretos y almacenamiento privado fuera del directorio de releases; validar permisos/espacio. Con todos los escritores detenidos, recorrer Alembic desde cero con el migrador y head del manifest. No create_all ni stamp. Base no vacia sin revision conocida: abortar para diagnostico, nunca marcar como nueva.
6. Crear esquema vacio mediante revisiones autorizadas. **F2 no ejecuta seeds** de usuarios/departamentos/workflow/catalogos/settings. Registrar intento/resultado externo y release_history; instalacion vacia marca backup no aplicable, nunca omite backup de datos previos. Futuras releases solo seeds expresamente aprobados conforme seccion 7.
7. F2 dispone de [CLI local](../backend/README.md#bootstrap-y-configuracion-f2), no ocote-admin cliente: init-auth con origen HTTPS explicito/claves privadas sin overwrite; bootstrap-admin por operador identificado con email/nombre y password getpass, Argon2id/auditoria, cero usuarios y lock exclusivo. Repetir no duplica/resetea; si ya hay usuarios, recuperacion aprobada. Custodia/entrega reales pendientes, no inventadas por herramienta. Luego admin configura nombre/zona/limites, prioridades/cinco horizontes y grafo atomico por API; configuration-status debe estar completo antes de uso posterior.
8. Verificar ready/revision/roles, configuracion, login/rotacion/logout y permisos con cuentas de prueba autorizadas; no dejar cuentas de demostracion. Probar evidencia si fase disponible, backup y restore aislado. Activar servicios/proxy y abrir solo con aprobacion; registrar version, duraciones, evidencia, responsable y entrega de runbook. Feature no implementada no se declara probada.

## 5. Instalacion B: PostgreSQL remoto gestionado

Cumplir preflight comun y pasos 5..8 de A; sustituir aprovisionamiento local por estas comprobaciones. No se distribuye ni administra data_directory, pg_ctl, HBA o binarios del servidor gestionado.

| Area         | Condicion obligatoria                                                                                                                                                                         |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Servicio     | PostgreSQL 18/minor homologada, region/residencia y mantenimiento acordados; probar permisos y btree_gist antes de comprometer proveedor                                                      |
| Red          | Endpoint privado/VPN o allowlist minima desde backend, DNS resoluble y firewall; sin acceso directo de SPA ni allowlist universal                                                             |
| TLS          | sslmode=verify-full, hostname del certificado y CA valida; archivo CA publicable no incluye clave privada; rotacion y expiracion probadas; no saltarse validacion                             |
| Roles        | Separar runtime/migrador/backup; permisos de extension aprobados con DBA del proveedor si no se concede CREATE EXTENSION; no exigir superusuario a runtime                                    |
| Conexiones   | Pool por proceso acotado y reserva operativa; suma de todos los workers/instancias bajo cuota; pool/statement/lock/connect timeouts, reciclaje y pre_ping validados                           |
| Migracion    | Endpoint directo separado de pooler transaccional; conexion persistente dedicada para lock de release; probar psycopg/prepared statements si runtime usa PgBouncer                            |
| Persistencia | Evidencias privadas con versionado/backup consistente y cifrado; no confiar en disco efimero de API                                                                                           |
| Recuperacion | Backups/PITR proveedor con retencion, permisos y restore aislado medidos; pg_dump portable por release y copia de evidencia fuera del dominio de fallo; verificar salida futura del proveedor |

Crear base con nombre exacto via interfaz/DBA permitido y verificar identidad/encoding/revision. Si proveedor impide nombre/extension/major requeridos, bloquear homologacion y registrar D06; no cambiar contrato silenciosamente. Timeouts por latencia no autorizan reintentos de mutaciones a ciegas: consultar version/resultado por request_id. Caida/failover/reconexion y vencimiento/rotacion CA se ensayan sin duplicar historia.

Nunca ejecutar init-dev ni fallback local contra nube. El helper solo entiende 127.0.0.1 y data_directory local; no es una herramienta remota configurable. No copiar holamundo a secretos del proveedor. Failover gestionado no reemplaza restore de una mala migracion ni garantiza consistencia con archivos externos.

## 6. API, exportaciones e integraciones

### Frontera MVP

API REST interna /api/v1 con OpenAPI versionado, esquemas/errores SDD y mismo origen HTTPS. Cada accion exige sesion vigente, rol y alcance, request_id y validacion; no es API publica anonima. UUID no autoriza. Cuentas humanas no sirven como cuentas de integracion ni se reutilizan refresh/access tokens en scripts de terceros. OpenAPI/Swagger en produccion queda restringido a responsables autenticados o no expuesto; health publico solo live sin detalles.

Exportacion interna sin job o tabla adicional en MVP: POST /exports/tasks y POST /exports/evaluations/{id} con format json/csv y filtros tipados. Admin/gerente global, lider solo departamento (evaluaciones finales), colaborador 403. Export de evaluacion solo final y siempre lee foto; export tareas usa proyeccion operativa autorizada sin binarios ni informacion administrativa. No existe export masivo de users/settings/audit/backups desde estas rutas.

- Servidor aplica alcance antes de filtros/joins/limite. Lectura consistente REPEATABLE READ con snapshot_at, zona y filtros efectivos; verifica identidad vigente antes de generar payload. Materializa resultado acotado antes de enviar headers, sin transaccion abierta durante descarga lenta. Sin datos: JSON items vacio/CSV cabecera; limite export_max_rows con lectura de limite+1: 413 EXPORT_TOO_LARGE, nunca truncar silenciosamente.
- Metadatos de JSON: schema_version, generated_at/snapshot_at UTC, organization_timezone, calculation_version cuando aplique, filtros, scope y row_count. CSV UTF-8 RFC 4180 con columnas estables y fechas ISO; contexto/corte/zona/version en columnas explicitas. No depende del separador regional de Excel.
- CSV usa serializador estandar: quoting correcto y neutralizacion formula-injection de cadenas que comiencen, incluso tras blancos/controles, por =, +, -, @ o tab/CR/LF; prefijar apostrofo antes de quoting, probar reimportacion segura sin ejecutar formulas. JSON conserva texto como dato escapado, nunca HTML activo.
- Content-Disposition attachment con nombre generado/saneado, MIME correcto, Cache-Control no-store y nosniff; sin enlaces publicos permanentes ni archivos temporales accesibles por proxy. Limites de frecuencia/tamano/tiempo probados con volumen. Cancelar descarga no altera tareas/fotos.
- audit_events registra export_requested y export_prepared o export_failed/denied con actor, filtro sanitizado, corte, filas y request_id; fallo de auditoria bloquea preparacion. No almacenar contenido exportado. Prepared significa respuesta preparada, no prueba de entrega/lectura; desconexion detectada se registra como fallo de transporte independiente sin fingir recepcion. Cliente usa descarga autenticada, no Bearer en URL.

### Fuera de MVP y condiciones para evolucionar

| Integracion                      | Motivo de exclusion                                       | Condiciones previas a autorizar                                                                      |
| -------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| ERP/contabilidad/inventarios     | Mapeos, PII y propiedad de datos no acordados             | Contrato versionado, responsables, alcance y reconciliacion                                          |
| Correo/mensajeria/notificaciones | Entrega, consentimiento y credenciales externos           | Proveedor aprobado, opt-in/politica, retries y observabilidad                                        |
| SSO/OIDC/SAML                    | Cambia identidad/provision/revocacion                     | Threat model, IdP, mapeo de roles y recuperacion local aprobados                                     |
| Webhooks/API terceros            | SSRF, firmas, reintentos y secretos nuevos                | Credenciales de servicio con scopes, rotacion, firma/replay, egress allowlist                        |
| IA externa                       | Transferencia/retencion de datos y metricas no gobernadas | Evaluacion legal/seguridad y autorizacion expresa, nunca ranking automatico                          |
| Importacion masiva               | Puede reescribir originales, duplicar o ampliar alcance   | Staging/preview, esquema/limites, validacion por fila, politica atomica, idempotency key y auditoria |

Futuro: definir autenticacion no humana separada, versionado/deprecacion, rate limits, errores trazables y revocacion; no asumir que JWT de una persona es diseno de integracion. Para mensajes externos, outbox transaccional con reintentos acotados/deduplicacion e idempotencia en consumidor; nunca llamada de red dentro del commit de negocio. Tablas/outbox/jobs/importadores se especifican solo al autorizar ese alcance, no se agregan a las 19 tablas MVP ni se declaran implementados.

## 7. Actualizacion controlada

Obligatoria en A y B para cada release con datos, incluso sin cambio de esquema. F1 prepara el ensayo local; automatizacion integral y homologacion cliente pendientes F7. La aplicacion nunca migra al arrancar; init-dev no participa. Operador autorizado conserva bitacora externa protegida, identidad, request_id y evidencia. release_history registra intentos; alembic_version solo revision. Si BD/tabla no existe, la bitacora externa preserva fallos y luego se incorpora sin falsear timestamps/resultados.

1. **Preflight y lock persistente.** Validar paquete firmado, instancia/cliente/base exactos, revision origen soportada, head unica exacta y compatibilidad de configuracion/PG. Guardar version anterior y nueva; espacio/cuotas para dump, restore y conversion. Un solo actualizador toma lock en conexion directa persistente durante TODO el protocolo, distinto al lock del helper o de cada transaccion. Si falla conexion/lock/revision, abortar sin mutar esquema.
2. **Mantenimiento sin escritores.** Aprobacion/aviso de ventana; proxy muestra mantenimiento, drenar y detener API, workers, schedulers y cualquier escritor externo. Confirmar cese de escrituras sin matar procesos indiscriminadamente. BD permanece disponible al operador/migrador. Registrar conteos/IDs/hashes de invariantes, revision y configuracion, incluido estado de archivos.
3. **Backup automatico previo y recuperabilidad.** Herramienta ejecuta pg_dump custom de base exacta con rol autorizado, codigo salida, tamano, SHA-256, manifest, cifrado/copia fuera del host; captura evidencias coherentemente sin escritores y configuracion/roles, claves por canal separado. pg_restore --list es solo inspeccion. Restaurar automaticamente a destino aislado autorizado con version/roles/extensiones compatibles, comprobar revision, FK/conteos/auditoria/fotos y archivos, duracion y checksum. Fallo/espacio insuficiente/no destino aislado: abortar SIN migrar. Snapshot/PITR gestionado complementa, no sustituye esta prueba por release. No usar --clean sobre cliente ni sobrescribir data. Aprobar retencion/coste de ensayo y limpieza del destino aislado antes de operarlo.
4. **Alembic forward.** Migrador y endpoint directo, artefacto inmutable: comprobar alembic current y alembic heads; ejecutar alembic upgrade head desde backend/ solo si head coincide con manifest. No DDL manual, create_all ni stamp para esconder divergencias. Cada revision publicada es inmutable; repetir upgrade ya aplicado debe ser no-op. Registrar pasos y revision real; un fallo detiene seeds/apertura.
5. **Configuracion conservadora, sin precargas de negocio.** F2 y evolucion empresarial mantienen catalogos/usuarios/plantillas/festivos/canales sin seeds ni demos. Operador configura explicitamente por UI; upgrade conserva valores/versiones/secretos/referencias existentes y registra solo cambios tecnicos aprobados por code/key mediante revision/backfill conservador. Conflictos de codigo/posicion/semantica detienen para resolucion, sin renumerar ni restaurar defaults. Nuevas claves requieren contrato tipado y faltantes quedan pendientes de captura; bootstrap admin solo instalacion nueva, nunca upgrade. La repeticion no duplica filas ni fabrica eventos.
6. **Integridad y smoke.** Revision igual destino y una head, todas las constraints/FK validas; comparar IDs/conteos esperados y task_history/audit_events/fotos finales/fechas originales contra invariantes. Nuevos eventos operativos se distinguen de hechos previos; no exigir hash total identico de tabla append-only que legitimamente crecio. Verificar evidencias, limites/settings, ready y permisos de las funciones entregadas. Fixtures sinteticos aislados o transacciones revertidas, sin alterar datos reales para simular una prueba.
7. **Reapertura aprobada.** Si todo pasa, activar componentes compatibles manteniendo proxy en mantenimiento hasta ready. Operacion aprueba, cambia proxy y permite escrituras gradualmente; monitoriza y registra fase/resultado terminal, duraciones, backup/restore y aprobacion por request_id. Fallo de registro antes de abrir bloquea apertura; si ocurre despues, bitacora externa registra el hecho y se reconcilia, no inventar rollback. Liberar lock al terminar controladamente. Sin DDL pendiente: upgrade no-op, pero backup/restore, integridad y smoke siguen obligatorios.

### Cambios de esquema con datos

- Revisiones Git exclusivamente en backend/alembic/versions; autogenerate es borrador a revisar. Una sola head por artefacto, revisiones origen compatibles enumeradas. No modificar revisiones ya publicadas ni apuntar a head de rama flotante.
- Expand/backfill/validate/contract: columna nullable/estructura paralela, backfill por lotes reanudables, comprobar conversion/ausencia de nulos, validar constraints y solo entonces NOT NULL/tipo final. Renombres con compatibilidad temporal; contract en release posterior con consumidores antiguos retirados y aprobacion. Nada de truncar o eliminar datos para hacer pasar constraint.
- Transacciones por revision cuando posible; no asumir que un error revierte revisiones ya confirmadas. CREATE INDEX CONCURRENTLY y pasos no transaccionales requieren plan/checkpoints/reanudacion probados. Registrar estado parcial sin stamp para ocultarlo.
- Preservar UUID/FK, fechas originales, task_history, audit_events, solicitudes terminales, release_history terminal y evaluation_items/fotos finales. Nuevas formulas usan calculation_version; no recalcular fotos historicas. Seeds nunca sustituyen backfill versionado o un cambio de negocio autorizado.

### Contingencia, no rollback universal

| Fallo                         | Accion autorizable                                                                                                                                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backup/preflight              | No migrar; conservar diagnostico, mantener o retirar mantenimiento solo con decision de operacion si version vigente sigue sana                                                                             |
| Revision transaccional falla  | Rollback de esa revision, inspeccionar current/estado real; anteriores pueden seguir aplicadas. Mantener mantenimiento y preferir fix-forward probado                                                       |
| DDL parcial/seeds/smoke falla | Conservar estado/logs/backup, seguir checkpoints probados; nuevo artefacto correctivo. Aplicacion anterior solo si esquema/datos siguen compatibles                                                         |
| Downgrade considerado         | Solo revision reversible ensayada, sin perdida/incompatibilidad y aprobacion expresa; nunca downgrade base automatico                                                                                       |
| Restore necesario             | Recuperar en base/cluster NUEVO aislado, validar BD/evidencia/roles y reconciliar bitacora de intentos; switchover aprobado, preservar origen fallido, no sobrescribir data ni restaurar --clean en cliente |
| Nuevas escrituras tras abrir  | Volver a mantenimiento, capturar estado y reconciliar/replay con responsables y RPO aprobado; backup previo puede perder cambios, no prometer rollback sin perdida                                          |
| Corte del actualizador        | Bitacora durable + release_history detectan intento running incompleto; nuevo operador verifica lock/procesos/estado, crea intento ligado por retry_of_id, no marca exito por version de binario            |

## 8. Aceptacion y entrega operativa

F1 demuestra base tecnica/revision, backup bloqueante y restore aislado; F2 parametros/usuarios/catalogos y bootstrap; F3 solicitudes/fechas; F6 exports; F7 paquete/instalacion/actualizacion completos en ambas modalidades. Una prueba local no homologa nube ni otra arquitectura.

Checklist de liberacion: firma/SBOM/licencias y vulnerabilidades; soporte D07; instalacion limpia; upgrade desde cada origen admitido y segundo upgrade no-op; seeds repetidos conservan configuracion; fallo de backup, revision, seed, red/CA y corte de proceso mantienen integridad; recuperacion aislada y switchover; RBAC negativo por ruta/API/export/evidencia; historial/fotos inmutables; TLS/pools/espacio/alertas; cuentas/secretos sin defaults; RPO/RTO medidos y responsables capacitados. Guardar evidencia fuera de Git si contiene datos privados.

Acta incluye: cliente/instancia/modalidad, version/commit/hash/revision, inventario de datos persistentes y secretos bajo custodia, responsables/soporte, resultados y limites, duraciones, ubicacion protegida de backups y aprobaciones. No cerrar con "instalado" por arrancar PostgreSQL ni con "migracion probada" por validar Markdown. La evidencia F1 es solo ensayo tecnico local, no ejecucion completa de estos procedimientos cliente.

## 9. Entrega empresarial sin archivos operativos

Contrato futuro D09..D16/RF-16..35; no instalador disponible ni autorizacion de ejecutar. Esta seccion concreta experiencia cliente y seccion7 sigue siendo el unico protocolo de release/contingencia, no se crea un segundo actualizador. [SDD/formularios](01-spec-driven-development.md#8-evolucion-empresarial-propuesta), [modelo](02-arquitectura.md#8-arquitectura-empresarial-proyectada), [portabilidad](04-entorno-y-portabilidad.md#9-portabilidad-empresarial-proyectada) y [F7..F12](03-estado-actual-y-roadmap.md#18-evolucion-empresarial-documental) son contratos coordinados.

### Frontera de configuracion

Secciones3..5 conservan requisitos de plataforma y antecedentes CLI F2, no obligan a que el cliente futuro edite .env/archivos/SQL. En F7 el instalador/supervisor sustituye esos pasos manuales por formularios y operaciones acotadas, preservando validaciones y permisos. Todo lo funcional/visual/seguridad/limites/modulos/almacenamiento/antivirus/correo/mensajeria/SSO/integraciones se guarda en PostgreSQL una vez accesible. Unicamente conexion PG/CA inicial/credenciales por identidad y raiz o referencia MASTER_ENCRYPTION_KEY quedan selladas fuera de BD; sin ese minimo no se puede descifrar ni alcanzar la fuente de configuracion. No prometer guardar la llave que abre la BD exclusivamente dentro de ella.

Instalador genera raiz256bits de forma segura por equipo/instancia y la protege en almacen SO; API no recibe clave migrador ni password administrativa PG. Registro sellado no es .env para editar. Claves JWT/TLS/SMTP/S3/IdP/tokens reversibles se guardan en boveda cifrada; hashes de password/API keys/feeds no se convierten en texto reversible. Material de recuperacion de raiz/certificados por canal independiente, custodia y suplente aprobados antes de operar. Backup de BD sin claves disponibles no acredita recuperacion.

### First-Run Setup Wizard

Estados persistentes: unpaired -> paired -> connection_verified -> schema_ready -> admin_created -> configured -> sealed. Antes de BD, instalador guarda checkpoint durable sellado; despues enlaza deployment_instances/job_runs/release_history con request_id sin borrar evidencia previa. Cualquier fallo queda failed/maintenance con paso recuperable aprobado; no volver a unpaired automaticamente. Estado es control tecnico del instalador, no fila de negocio precargada.

| Paso de UI futura | Campos/accion | Validacion, evidencia y salida |
| --- | --- | --- |
| 1. Emparejar equipo | Instalador firmado abre canal HTTPS local y entrega capacidad de un uso al operador presencial; expira<=15min, ligada a instancia/navegador/CSRF | No secreto en query/log/telemetria. Por defecto solo loopback; uso remoto requiere tunel autenticado/aprobado, no publicar wizard. GET /setup/status tambien exige capacidad o admin vigente; no enumera roles/DSN |
| 2. Elegir PostgreSQL | Local portable incluido o externo/gestionado; host/port/database, usuarios/passwords separados, SSL/CA y confirmacion de identidad segun SDD | Local aprovisiona binarios/cluster solo nuevos confirmados, nunca cluster del desarrollador. Externo exige roles/base preparados por DBA y red aprobada; no captura superusuario remoto ni cambia nombre ocoteAppDatabase silenciosamente |
| 3. Probar conexion y permisos | POST /setup/connection-tests, ambos DSN, config_hash/version y origen de prueba | Probar identidad PG18/UTF8/nombre/SSL/CA/hostname/revision/extension/grants, timeouts y permisos negativos runtime; devolver resultados sanitizados por rol. verify-full obligatorio remoto; require/verify-ca solo diagnostico, nunca downgrade automatico. Prueba expira10min y ante cualquier cambio de campo |
| 4. Sellar y preparar release | Confirmar destino/instalacion nueva o upgrade; registrar manifest firmado/custodia y generar/sellar raiz si es primera instalacion | No regenerar si ya existe raiz. Base no vacia/sin head conocida bloquea instalacion nueva; origen0005 sigue upgrade seccion7, no initdb ni stamp. btree_gist lo instala revision autorizada con permiso de DBA limitado, no concesion general automatica |
| 5. Migrar controladamente | POST /setup/install devuelve202/job id, frontend consulta estado autenticado sin mantener password en formulario | Agente separado usa migrador/endpoint directo/lock persistente, sin escritores. Base virgen confirmada puede registrar backup no aplicable; cualquier dato previo exige backup+restore aislado bloqueantes. Revision desde manifest y upgrade/no-op, grants/integridad/ledger; fallo mantiene maintenance, runtime nunca ejecuta Alembic |
| 6. Primer admin | Email/nombre/password+confirmacion, nombre organizacion y zona IANA propuesta America/Mexico_City confirmada, origen HTTPS institucional | Capacidad temporal y lock usuarios=0, Argon2id y audit; exactamente un admin elegido, sin identidad/password por defecto. Con usuarios existentes no crear ni resetear; usar recuperacion formal. No copiar password de conexion como password admin |
| 7. Configurar y aceptar | Autenticar admin, completar parametros/catalogos/workflow vacios y configuracion tecnica local/ClamAV disponible; probar, guardar/activar versionada | Sin catalogos/departamentos/plantillas/defaults demo; complete=false bloquea operacion dependiente. F7 migra a BD configuracion de capacidades F1-F6 existentes; F8+ solo ofrece provedores/modulos instalados por fase. Prueba no activa ni certifica seguridad productiva |
| 8. Sellar cierre | POST /setup/complete, confirmar custodia, backup/restore/smoke y runbook de instancia | Guardar setup_state=sealed, revocar capacidades, retirar rutas mutantes de setup (403/410 segun contrato), recibo SO sellado impide reabrir por borrar usuarios/tabla. Recuperacion solo flujo local supervisado/reautenticado, nunca endpoint de reset publico |

La capacidad setup no es access token de negocio ni se persiste en storage SPA; vive en memoria temporal, se borra al cerrar y se renueva solo por emparejamiento local. API de setup no entrega DSN/password/clave ni screenshots de credenciales. Tramo inicial sin auditoria BD deja bitacora externa protegida y reconciliacion posterior con timestamps/request_id reales; fallo no desaparece por reintentar.

### Operacion diaria y cambios sensibles

Admin opera centro de configuracion e integraciones de SDD: secretos write-only, boton Reemplazar, indicador configurado/ultima rotacion; guardar/activar/desactivar con reason/expected_version y prueba ligada a version. No enlaces publicos a evidencia/logo/backups ni red de prueba para G/L/C. Revision atomica se recarga automaticamente en API/workers/proxy mediante supervisor; los procesos comparan revision y fallan cerrados ante incoherencia. Un cambio que requiere drenar TLS/pools se aplica como job supervisado, no solicita reinicio manual del servidor al cliente.

Cambiar conexion PG/ca/credenciales minimas usa formulario local de mantenimiento, prueba ambos roles, conserva bootstrap anterior sellado para contingencia compatible, y cambia unicamente tras backup/restore/confirmacion. Nunca redirigir una instancia con escrituras a una base aparentemente vacia; validar instance_id/head/invariantes. MASTER_ENCRYPTION_KEY no es campo del panel: rotacion por asistente de custodia genera epoch nuevo, verifica nuevas versiones y conserva claves antiguas necesarias para backups; no se imprime ni exporta por web. Cambios de IdP o autenticacion requieren ultimo admin local probado; mantener cookies/CSRF/Web Locks, no usar emergencia como bypass sin auditoria.

### Actualizacion incremental con configuracion cifrada

Se ejecutan exactamente gates de seccion7. El manifest futuro agrega settings_schema_version, bootstrap_schema_version, vault_format_version, key_epochs compatibles, integration_adapter_versions y funcionalidades instaladas, ademas de head/commit/firma/SBOM/SO. Estas son propiedades del paquete, no secretos ni parametros que sobreescriban la BD. Una revision no soportada o raiz no accesible bloquea antes de DDL. No editar0001..0005 ni tools/f1_local..f6_local/f6_visual para crear la proxima release: nuevo artefacto/herramienta bajo autorizacion propia.

| Elemento a preservar | Requisito incremental y prueba futura |
| --- | --- |
| Valores/flags/politicas/branding/catalogos | Snapshot semantico antes/despues, IDs/versiones/ambitos conservados. Registry nuevo no rellena defaults; claves nuevas requeridas se presentan pendientes y operaciones dependientes permanecen cerradas hasta captura |
| Secretos cifrados y bootstrap | Copia consistente de ciphertext/key_refs/epoch y bootstrap sellado recuperable por canal separado; no descifrado en dump plano ni log. Cambiar formato con expand/dual-read temporal autorizado/validate, nunca doble autoridad indefinida ni fallback a .env |
| Claves/JWT/sesiones | Rotacion explicita/ventana compatible con kid y revocacion; no regenerar secretos al arrancar/actualizar, no ampliar expiracion de familias existentes |
| Objetos/evidencia/fotos | Manifest/hash y backend/version de storage preservados; lectura de objetos antiguos verificada y no mover a proveedor activo sin migracion de objetos aprobada; evaluaciones/items originales se leen con su calculation_version |
| Colas/schedules/entregas | Pausar/reanudar con fencing/leases e idempotencia; sandbox de restore inhibe egress antes de arrancar. No reemitir evento ya terminal ni generar ocurrencia duplicada tras cambiar binario |
| Historia/releases | Nuevos eventos operativos distinguibles, append-only y terminales intactos; comparar invariantes, reconciliar bitacora externa sin alterar resultados historicos |

Fallos siguen contingencias de seccion7: maintenance, evidencia, fix-forward preferido; downgrade solo ensayado/autorizado. Restore siempre aislado, requiere BD+objetos+raiz/epochs/ACL/roles y deshabilita egress/schedulers antes del smoke; switchover requiere aprobacion propia y unico escritor. No garantizar recuperacion por pg_restore --list, checksum o Markdown valido.

### Entrega al cliente y limites

Acta F7 incluye plataforma/proveedor efectivamente ensayados, clave publica de firma por canal independiente, inventario de configuracion BD sin secretos, custodios/suplente, runbook de emergencia, evidencias de wizard/TLS/roles/upgrade0005/no-op/backup/restore con archivos+claves y operacion de UI. F8..F12 agregan solo capacidades autorizadas y probadas de roadmap18; no se declara soporte universal S3/IdP/chat por un selector.

La consola RF-35 usa job_runs/backup_records/retention_policies, muestra salud/latencia/ultimo respaldo/estado release sin rutas/claves. Agente local admite backup/update/restore-verify sobre destinos aprobados, no SQL/shell/ruta libre. En gestionado, API proveedor/PITR requieren adaptador y permisos homologados, no root remoto. Retencion no purga originales/historia/fotos/evidencia; copia off-host/cifrado/restores medidos y responsables antes de produccion. Las excepciones locales vencen2026-12-24 sin renovacion automatica y no autorizan datos reales, integraciones o red compartida.
