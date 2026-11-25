# OCOTE: paquetizacion, instalacion y actualizaciones

Version documental: 2.0, con cierre F1 local del 2026-11-24. Especificacion de entrega objetivo, NO instalador disponible ni despliegue certificado. Existen backend tecnico, revision Alembic y ensayo local; no empaquetador firmado, comandos ocote-admin ni actualizador cliente. Estado/evidencia en [acta F1](03-estado-actual-y-roadmap.md#7-cierre-formal-f1-local).

## 1. Autoridad, alcance y modalidades

Leer [SDD](01-spec-driven-development.md), [arquitectura/modelo](02-arquitectura.md), [roadmap](03-estado-actual-y-roadmap.md) y [entorno de desarrollo](04-entorno-y-portabilidad.md). Este documento es fuente unica del protocolo de entrega/actualizacion del cliente; la guia 04 conserva el arranque portable de desarrollo. Reglas y permisos no cambian por modalidad.

| Modalidad objetivo | Topologia                                                                                                 | Condicion de soporte                                                                     |
| ------------------ | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| A local            | Proxy HTTPS, SPA compilada, FastAPI y PostgreSQL 18 portable Windows o contenedor con volumen persistente | SO/arquitectura, distribucion/minor PG, gestor de servicios y disco homologados en F1/F7 |
| B gestionada       | Proxy/SPA/API en host aprobado y PostgreSQL 18 remoto/gestionado por red privada                          | Proveedor, region, TLS/CA, extension, limites, backup y restore homologados en F1/F7     |

Ninguna incluye BD dentro de Angular ni acceso SQL desde el navegador. Nube no exige llevar frontend/API a nube ni usar multiples origenes. Solo HTTPS publico; servicios y BD privados. Un despliegue puede ser offline respecto a Internet si distribuye dependencias/certificados/actualizaciones de seguridad por canal autorizado.

Estado vigente: PostgreSQL 18.4 Windows local con alembic_version/release_history, roles runtime/migrador, migracion inicial/no-op y restores en bases temporales del mismo cluster probados; ocote conservada. No hay prueba de instalacion cliente, contenedor, SO alternativo, nube ni recuperacion ante perdida del host. El protocolo cliente sigue siendo contrato de aceptacion, no evidencia de homologacion.

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
| configuracion ejemplo | Variables documentadas sin credenciales: DSN runtime/migracion, TLS/CA, claves JWT, almacenamiento, origen, timeouts/pool, nombre/zona de bootstrap              |
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
| Clasificacion/minimizacion | Usuarios, asignaciones, ejecucion y evaluaciones son informacion interna/personal de acceso restringido por rol Y alcance; evidencia y respaldos se tratan como potencialmente sensibles. No cargar datos reales en este entorno F1/F2. No recolectar datos extra ni contenido de archivos, tokens, DSN, passwords o cuerpos en logs. |
| Evidencia privada | Volumen u object storage privado fuera del directorio publico y de releases, claves generadas por servidor, minimo privilegio y descarga autenticada/autorizada. PDF/PNG/JPEG hasta 10 MiB, verificar extension/MIME/firma y SHA-256 sin considerar eso prueba antimalware. No enlaces publicos permanentes ni nombres/rutas elegidos por el cliente. |
| Cuarentena y escaneo | Antes de F5, integrar y probar antivirus mantenido: carga en cuarentena privada, no descargable/publicable ni valida para completar una tarea hasta resultado limpio confirmado. Error, timeout, indisponibilidad o resultado desconocido: fail-closed, conservar evidencia tecnica sanitizada y permitir tratamiento por operador autorizado; nunca publicar por fallback. No existe almacenamiento/escaneo implementado en F1. |
| Cifrado y custodia | Para datos reales, cifrado en reposo de evidencia/backups y en transito cuando cruza host, claves separadas con rotacion y acceso auditado. Probar restauracion con sus claves. Los dumps tecnicos locales actuales tienen ACL privada, NO cifrado ni copia off-host; no trasladar a ellos datos reales ni afirmar cumplimiento productivo. |
| Historia y retencion | No purga automatica ni borrado/reescritura de originales, task_history, audit_events, solicitudes/releases terminales, fotos finales o evidencia. Antes de produccion, seguridad/legal/negocio fijan plazos por categoria, residencia, obligaciones y tratamiento de solicitudes de acceso/supresion; no inventar un plazo legal ni prometer CRUD destructivo. Mantener acceso restringido durante conservacion. |
| Respaldos | Diarios y antes de cada release; retencion minima 30 dias, sin habilitar purgas en esta tarea. Conjunto consistente BD+evidencia y configuracion, manifest/hash, cifrado/copia fuera del dominio de fallo y claves por canal separado antes de datos reales. Fallo de respaldo o restore previo bloquea migracion conforme seccion 7. Programacion, copia off-host y alertas aun no implementadas. |
| Recuperacion | RPO <=24 h y RTO <=4 h aprobados como objetivos de diseno, no SLA ni resultados de produccion. Restore aislado mensual y por release, con revision, integridad, historia, archivos y duracion documentadas. El ensayo local de 0.482 s de la seccion 7 del roadmap prueba solo recuperacion logica de dos tablas en el mismo cluster, no fallo de host, carga o RPO operacional. |
| Continuidad | El nombre inicialmente propuesto para sustituto coincidia con el responsable; se aprobo expresamente excepcion **sin suplente hasta 2026-12-24**, solo F1/F2 local con datos sinteticos. Si el responsable no esta disponible, suspender migraciones/restores; no delegar credenciales informalmente. Designar/capacitar otra persona o cargo independiente antes del vencimiento o de datos reales/produccion. |

Runbook local, comandos y evidencias en [backend/README.md](../backend/README.md) y [acta F1](03-estado-actual-y-roadmap.md#7-cierre-formal-f1-local). No reejecutar provision/rehearse sobre una base existente: la verificacion de cierre usa verify-existing, no altera release_history ni sustituye una release firmada. Ante fallo, mantener mantenimiento y bitacora, diagnosticar sin reset y seguir contingencia de seccion 7. Esta politica no autoriza nuevas operaciones ni F2.

## 4. Instalacion A: PostgreSQL local

1. TI obtiene PostgreSQL 18 para SO/arquitectura homologados y verifica firma/checksum, permisos y licencia. Elegir portable como servicio de usuario dedicado o imagen fijada por digest con volumen persistente; no montar data en carpeta sincronizada. Usuario de servicio sin administrador; control de inicio/apagado y recuperacion documentado.
2. Solo si no existe cluster y destino esta confirmado vacio: inicializacion expresa con password fuerte por prompt y SCRAM. Nunca trust, password de ejemplo, borrar PID o reutilizar datos de otro major. Si existe cluster/base, detener el flujo de instalacion nueva y seguir inventario/actualizacion o recuperacion autorizada.
3. Configurar loopback/interfaz privada, HBA minimo y firewall. Si BD cruza host, TLS verify-full/CA; para mismo host restringido loopback se admite conexion local sin TLS solo con aprobacion de seguridad/ACL. No publicar 5432 al mundo ni en contenedor por defecto; volumen no equivale a backup.
4. Provisionar roles/base exacta mediante administracion autorizada, nunca con runtime. Verificar identidad, UTF8, conectividad por cada rol, btree_gist y restricciones. No usar init-dev del repositorio para instalacion productiva: es exclusivamente desarrollo con credencial publica.
5. Instalar paquete inmutable, configurar secretos y almacenamiento privado fuera del directorio de releases; validar permisos/espacio. Con todos los escritores detenidos, recorrer Alembic desde cero con el migrador y head del manifest. No create_all ni stamp. Base no vacia sin revision conocida: abortar para diagnostico, nunca marcar como nueva.
6. Ejecutar seeds conservadores versionados (seccion 7) y nombre/zona de bootstrap explicitos. Sin demos, personas, passwords o planes inventados. Registrar intento/resultado en bitacora externa y release_history al existir; instalacion vacia marca backup no aplicable, pero nunca omite backup de datos previos.
7. Cuando F2 este implementado, bootstrap del primer admin por operador local identificado: nombre/email y password fuerte introducida por canal seguro, hash Argon2id y auditoria; no imprimir password ni entregarla en logs. Exito requiere cero usuarios preexistentes y lock exclusivo; repetir no duplica ni resetea. Si ya hay usuarios, usar procedimiento de recuperacion de acceso aprobado, no crear un admin adicional a escondidas. D02 define custodia/entrega y cambio de credencial.
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
5. **Seeds conservadores.** Comando versionado, despues del upgrade: insertar faltantes por code/key sin pisar departamentos, workflow, prioridades/horizontes, parametros, usuarios ni credenciales del cliente. Validar conflictos de codigo/posicion/semantica y detener para resolucion aprobada, no renumerar/reemplazar silenciosamente. Repetir no duplica ni genera eventos ficticios de cambio. Nuevas claves requieren definicion tipada versionada; nombre/zona iniciales explicitos, no defaults inventados. Bootstrap admin solo instalacion nueva, nunca upgrade.
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
