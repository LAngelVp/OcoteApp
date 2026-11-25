# OCOTE

Gestion de Planes con horizontes configurables, Ejecucion Operativa y Evaluacion Gerencial. Monorepo ocoteApp: Angular 18.2 SPA/SCSS en raiz y base tecnica backend Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic.

Planes y objetivos admiten start_date/due_date/horizon_type: anual, semestral, trimestral, mensual o personalizado, incluidos cruces de anio. El nombre tecnico annual_plans no limita el calendario ni impone un solo plan por anio. Reglas y metricas canonicas en la SDD.

## Retomar el proyecto

Leer [AGENTS.md](AGENTS.md), entrada comun para desarrolladores y agentes de IA, y despues:

1. [docs/01-spec-driven-development.md](docs/01-spec-driven-development.md): alcance, reglas, contratos, aceptacion e identidad visual OCOTE.
2. [docs/02-arquitectura.md](docs/02-arquitectura.md): arquitectura, seguridad y modelo de datos.
3. [docs/03-estado-actual-y-roadmap.md](docs/03-estado-actual-y-roadmap.md): evidencia F0-F6, F7 bloqueada y fases empresariales F8..F12 propuestas.
4. [docs/04-entorno-y-portabilidad.md](docs/04-entorno-y-portabilidad.md): PostgreSQL, credencial exclusivamente local, Git y otra computadora.
5. [docs/05-paquetizacion-instalacion-y-actualizaciones.md](docs/05-paquetizacion-instalacion-y-actualizaciones.md): paquete cliente, instalaciones local/nube, bootstrap, exports/integraciones y protocolo central de release/contingencia.

Estado al 2026-11-25 local: **F6 autorizada, implementada y migrada local/sintetico**, [evidencia y limites](docs/03-estado-actual-y-roadmap.md#17-analitica-evaluaciones-y-exports-f6-local-2026-11-25). Analitica, evaluacion departamental y exports internos JSON/CSV;30 pruebas backend F6 y164 ChromeHeadless correctas. Head20261125_0005,19 tablas de dominio/20 contando Alembic y seis releases terminales; datos previos/bootstrap/configuracion conservados. Sin seeds ni datos sinteticos insertados en origen. Cierre operativo F5 y aceptacion del operador pendientes; almacenamiento/ClamAV reales pospuestos, cargas cerradas. Excepciones D06 sin suplente y D07 soporte Angular/61 alertas extendidas a F6 hasta **2026-12-24**, responsable LUIS ANGEL VALLEJO - DESARROLLADOR; solo Windows/PG18.4 local/loopback/sintetico. F7 bloqueado; no produccion/nube.

Base documental2.1:19 tablas de dominio implementadas y permisos por rol/alcance. D03/D08 y RN-06 ratificados: pesos iguales, cohorte por original_due_date, calendario manual, sin ranking ni nota compuesta; finales inmutables al corte real. Colaborador sin analitica/evaluaciones/exports; lider solo departamento y finales propias. Integraciones externas fuera de MVP. America/Mexico_City solo bootstrap; D05/D06 son base/objetivos de diseno, no SLA ni aprobacion productiva.

Cliente objetivo: PostgreSQL 18 local portable/contenedor o gestionado remoto; guia 05 exige roles separados, TLS/red/pooling, paquete firmado, backup y restore ensayados. No hay proveedor/SO cliente homologado ni instalador/ocote-admin disponible; no usar helper de desarrollo para produccion o nube.

## Evolucion empresarial documentada

Solo especificacion futura: RF-16..35, RN-08..20, D09..16 y47 tablas nuevas proyectadas, ninguna creada. [Contratos y formularios](docs/01-spec-driven-development.md#8-evolucion-empresarial-propuesta), [modelo/grants](docs/02-arquitectura.md#8-arquitectura-empresarial-proyectada) y [fases/DoD](docs/03-estado-actual-y-roadmap.md#18-evolucion-empresarial-documental) son la fuente normativa; no paridad de mercado ni funcionalidades anunciadas como disponibles.

Configuracion Total en PostgreSQL tras conectar: politicas/limites/flags/branding, storage/antivirus, correo/chat, SSO e integraciones versionados desde UI. Boveda AES-256-GCM y secretos write-only, nunca GET en claro. Unica excepcion inevitable: bootstrap minimo de conexion/CA inicial/credenciales por rol y raiz MASTER_ENCRYPTION_KEY generada por instalador, sellados en almacen SO fuera de BD. Cero archivos operativos editables, no cero archivos fisicos. El .env/CLI actual permanece intacto hasta migracion F7 autorizada; no existe todavia el [wizard cliente](docs/05-paquetizacion-instalacion-y-actualizaciones.md#9-entrega-empresarial-sin-archivos-operativos).

Orden recomendado: **F7** endurecimiento, instalador y PG flexible -> **F8** configuracion ampliada/branding/storage -> **F9** calendarios/dependencias/plantillas/campos/colaboracion/busqueda -> **F10** notificaciones/correo/chat/feeds -> **F11** SSO/DevOps/API scopes/webhooks/calendarios externos -> **F12** importacion dry-run/reportes/consola avanzada. Cada fase requiere autorizacion propia, seguridad/aceptacion y evidencia nueva; F7 sigue bloqueada. Retencion no habilita borrar historia/evidencia/fotos y ninguna integracion altera RN-03/RN-06.

Esta ampliacion no ejecuta BD/servidores/proveedores ni modifica codigo, scripts, lock, utilidades F1-F6 o cinco migraciones aplicadas incluida0005. [Portabilidad futura](docs/04-entorno-y-portabilidad.md#9-portabilidad-empresarial-proyectada) exige restauracion aislada con objetos y claves; no copiar cluster/secretos del desarrollador ni usar credencial publica para cliente.

## Base de datos local

Binarios en database/postgres/bin, cluster mayor 18 en database/data y logs en database/logs. NO vienen en Git: en otra PC seguir la guia de portabilidad antes de ejecutar el helper. No inicializar encima de data existente.

En Bash/Git Bash, desde raiz, para el desarrollo local con la credencial conocida descrita en la guia:

```bash
bash scripts/init-dev.sh --check
```

Si esta detenido o falta ocoteAppDatabase, el script puede arrancar y crear solamente lo que falta:

```bash
bash scripts/init-dev.sh
```

Host fijo 127.0.0.1, puerto 5432; conserva el nombre con mayusculas y no renombra bases previas. init-dev usa PGPASSWORD o fallback conocido EXCLUSIVO local y muestra backend/.venv, backend/alembic y node_modules; no instala, migra, hace seeds, resetea o restaura. Para PGPASSFILE sin fallback usar el helper inferior segun la guia. [.env.example](.env.example) no contiene secretos y no se carga automaticamente.

Cada release local/gestionada sigue [guia 05, seccion 7](docs/05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada): lock/mantenimiento sin escritores, backup automatico/restore aislado, Alembic versionado, seeds conservadores e integridad/smoke; reapertura o contingencia aprobada. release_history registra intentos, alembic_version revision. No DDL manual/create_all/stamp ni confundir retoma con migracion; actualizador aun inexistente.

## Verificacion

```bash
bash -n scripts/init-dev.sh
bash -n scripts/db-start.sh
node --test scripts/db-start.test.cjs
git diff --check
```

Los tests del helper usan mocks y carpetas temporales, no el cluster real. Requieren Node 22.x/Bash en el entorno actual; no certifican otros SO, seguridad de produccion ni funcionalidad de negocio.

El cierre F1 verifico 33 pruebas backend (7 PostgreSQL), lint/pip check, backup/restore y dos nuevos no-op sin mutar historia; build produccion Angular y 6 pruebas ChromeHeadless, peers completos sin problemas. La auditoria npm reporto 61 alertas, no corregidas ni cubiertas por el build: aceptacion temporal separada en acta F1. Los 16 mocks previos no se reejecutaron: sus helpers no cambiaron. Comandos backend y resultados en el roadmap y README del backend.

F2 verifico **58 pruebas backend**, Ruff/pip check, upgrade/no-op y tres restores aislados; sin opt-in, 33 passed/25 skipped. Referencias/JSON/fences de documentacion validos, revision F1 y package-lock intactos. No build/tests Angular repetidos ni remediacion de D07; diagnostico de editor rootDir/TS6 en tsconfig no modificado registrado en acta F2.

## Frontend F4-F6 local

Node compatible con Angular 18.2 y npm; dependencias y lockfile conservados. No ejecutar npm ci salvo instalacion necesaria y revisada bajo D07. Usar la API local existente en 127.0.0.1:8000; [arranque backend](backend/README.md#salud-y-arranque) solo si no esta ya activa y esta autorizado. No repetir bootstrap ni cambiar AUTH_ORIGIN para sortear errores.

```bash
npm start -- --host 127.0.0.1 --port 8443 --ssl --no-open
npm run build
CHROME_BIN='C:/Program Files/Google/Chrome/Application/chrome.exe' npm test -- --watch=false --browsers=ChromeHeadless --progress=false --reporters=dots
```

Abrir **https://localhost:8443/login**, no la URL con IP: es el origen HTTPS exacto ya configurado por el operador. [proxy.conf.json](proxy.conf.json) conserva Origin y envia /api a loopback:8000. El certificado autofirmado de ng serve requiere confianza/aceptacion local del operador; no cambiar cookies Secure ni afirmar TLS productivo. HTTP:4200 no sirve para probar sesion. Solo loopback, sin red compartida.

Access/CSRF solo memoria, refresh HttpOnly del navegador, Web Locks obligatorios para rotacion entre pestanas; sin Web Locks falla cerrado. Guardas y acciones siguen auth/me, sin sustituir el alcance del servidor. Administracion presenta estado incompleto y formularios vacios, nunca configura por defecto. UI conserva originales/versiones y un 409 requiere descartar/recargar explicitamente. Tema/fuentes/licencias F4 se reutilizan. Kanban conserva columnas vacias y ofrece arrastre y boton equivalentes; Timeline muestra fechas inclusivas/original/cierre y tabla, sin editar por drag. Evidencias se adjuntan explicitamente en detalle y se descargan como adjuntos; sin DELETE. [Configuracion privada y limites](backend/README.md#evidencias-y-vistas-f5).

## Diagnostico Operativo Local

La [revision de habilitacion operativa del 2026-11-25](docs/03-estado-actual-y-roadmap.md#15-diagnostico-de-habilitacion-operativa-2026-11-25) confirma que capturar parametros y catalogos no basta si una etapa activa no tiene camino a la terminal. Configuracion muestra el motivo especifico (`workflow_error`) y accesos a Etapas/Transiciones, sin crear aristas ni roles por defecto. El titular decidio completar el grafo desde la UI; ese incremento no modifico su configuracion. Ver runbook para el orden plan/objetivo/activacion/tareas y el requisito independiente de almacenamiento/ClamAV para etapas con evidencia. La autorizacion posterior F6 no cierra esa aceptacion ni habilita F7.

La [revision de tablas y evidencia](docs/03-estado-actual-y-roadmap.md#16-paginacion-de-tablas-y-evidencia-explicita-2026-11-25) agrega cinco filas iniciales y selector 5/10/20/50 a todas las tablas, incluidos subtareas y Timeline, con primera/anterior/siguiente. La transicion distingue archivos ya adjuntos, selector vacio y cargas sin configurar; nunca omite evidencia. Se conservan avance RN-03 y Kanban, sin imponer cinco etapas ni cambiar el grafo del titular. Verificados 154 tests Angular, build y revision sintetica a 1280/360px CSS; no cambios backend/migraciones ni aceptacion operativa real implicita.

## Siguiente fase

Operador acepta los recorridos F4-F6 con su sesion/alcance: /analitica y /evaluaciones, filtros, cortes y denominadores, borrador/recalculo/final con conclusion y descargas. Sin periodos/evaluadores por defecto. Confirmar [custodia/configuracion](backend/README.md#bootstrap-y-configuracion-f2) sin sobrescribir; almacenamiento externo y ClamAV mantenido siguen pendientes de configuracion/ensayo real autorizado antes de habilitar cargas. **F7 requiere autorizacion nueva**. Conservar RN-07 y excepciones hasta2026-12-24 sin renovacion automatica. No repetir apply F5/F6 ni comandos historicos; usar solo ensayo F6 UUID aislado del runbook con autorizacion PG.
