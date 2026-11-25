# OCOTE

Gestion de Planes con horizontes configurables, Ejecucion Operativa y Evaluacion Gerencial. Monorepo ocoteApp: Angular 18.2 SPA/SCSS en raiz y base tecnica backend Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic.

Planes y objetivos admiten start_date/due_date/horizon_type: anual, semestral, trimestral, mensual o personalizado, incluidos cruces de anio. El nombre tecnico annual_plans no limita el calendario ni impone un solo plan por anio. Reglas y metricas canonicas en la SDD.

## Retomar el proyecto

Leer [AGENTS.md](AGENTS.md), entrada comun para desarrolladores y agentes de IA, y despues:

1. [docs/01-spec-driven-development.md](docs/01-spec-driven-development.md): alcance, reglas, contratos, aceptacion e identidad visual OCOTE.
2. [docs/02-arquitectura.md](docs/02-arquitectura.md): arquitectura, seguridad y modelo de datos.
3. [docs/03-estado-actual-y-roadmap.md](docs/03-estado-actual-y-roadmap.md): evidencia, decisiones abiertas y fases F0-F7.
4. [docs/04-entorno-y-portabilidad.md](docs/04-entorno-y-portabilidad.md): PostgreSQL, credencial exclusivamente local, Git y otra computadora.
5. [docs/05-paquetizacion-instalacion-y-actualizaciones.md](docs/05-paquetizacion-instalacion-y-actualizaciones.md): paquete cliente, instalaciones local/nube, bootstrap, exports/integraciones y protocolo central de release/contingencia.

Estado al 2026-11-24 local: **F5 autorizada, implementada y verificada tecnicamente local/sintetico; cierre operativo pendiente**. [Evidencia F5](docs/03-estado-actual-y-roadmap.md#11-kanban-timeline-y-evidencias-f5-local): Kanban, Timeline y evidencia privada fail-closed; 59 pruebas ChromeHeadless/build y backend105 passed/Ruff/pip. Head20261124_0004/18 tablas/cinco releases terminales, datos y cuatro releases previas preservados. Sin seeds ni configuracion inventada. Aceptacion funcional/configuracion del operador y almacenamiento/ClamAV real pendientes: cargas operativas deshabilitadas. Excepciones D06 sin suplente y D07 soporte Angular/61 alertas hasta **2026-12-24**, responsable LUIS ANGEL VALLEJO - DESARROLLADOR, solo Windows/PG18.4 local/sintetico. F6-F7 no autorizados; no produccion/nube.

Fundacion documental 2.0 con incrementos F2-F5: 19 tablas objetivo y permisos por rol/alcance; API/UI, solicitudes y evidencia implementadas, exports/evaluacion futuras. Colaborador nunca recibe agregados ajenos/evaluaciones. Integraciones externas fuera de MVP. America/Mexico_City solo bootstrap, formulas del nucleo/cierre ratificados; D03/D08 gerenciales pendientes F6. D05/D06 son base/objetivos de diseno, no SLA ni aprobacion productiva.

Cliente objetivo: PostgreSQL 18 local portable/contenedor o gestionado remoto; guia 05 exige roles separados, TLS/red/pooling, paquete firmado, backup y restore ensayados. No hay proveedor/SO cliente homologado ni instalador/ocote-admin disponible; no usar helper de desarrollo para produccion o nube.

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

## Frontend F4-F5 local

Node compatible con Angular 18.2 y npm; dependencias y lockfile conservados. No ejecutar npm ci salvo instalacion necesaria y revisada bajo D07. Usar la API local existente en 127.0.0.1:8000; [arranque backend](backend/README.md#salud-y-arranque) solo si no esta ya activa y esta autorizado. No repetir bootstrap ni cambiar AUTH_ORIGIN para sortear errores.

```bash
npm start -- --host 127.0.0.1 --port 8443 --ssl --no-open
npm run build
CHROME_BIN='C:/Program Files/Google/Chrome/Application/chrome.exe' npm test -- --watch=false --browsers=ChromeHeadless --progress=false --reporters=dots
```

Abrir **https://localhost:8443/login**, no la URL con IP: es el origen HTTPS exacto ya configurado por el operador. [proxy.conf.json](proxy.conf.json) conserva Origin y envia /api a loopback:8000. El certificado autofirmado de ng serve requiere confianza/aceptacion local del operador; no cambiar cookies Secure ni afirmar TLS productivo. HTTP:4200 no sirve para probar sesion. Solo loopback, sin red compartida.

Access/CSRF solo memoria, refresh HttpOnly del navegador, Web Locks obligatorios para rotacion entre pestanas; sin Web Locks falla cerrado. Guardas y acciones siguen auth/me, sin sustituir el alcance del servidor. Administracion presenta estado incompleto y formularios vacios, nunca configura por defecto. UI conserva originales/versiones y un 409 requiere descartar/recargar explicitamente. Tema/fuentes/licencias F4 se reutilizan. Kanban conserva columnas vacias y ofrece arrastre y boton equivalentes; Timeline muestra fechas inclusivas/original/cierre y tabla, sin editar por drag. Evidencias se adjuntan explicitamente en detalle y se descargan como adjuntos; sin DELETE. [Configuracion privada y limites](backend/README.md#evidencias-y-vistas-f5).

## Siguiente fase

Operador confirma [custodia/bootstrap y configuracion](backend/README.md#bootstrap-y-configuracion-f2) existentes sin sobrescribir y completa parametros/catalogos/grafo por administracion. Configura almacenamiento externo al checkout y ClamAV mantenido; prueba carga limpia/rechazo/indisponibilidad reales y acepta los recorridos F4/F5 con su sesion antes del cierre operativo. Las pruebas sinteticas no sustituyen esa puerta. **F6 requiere nueva autorizacion expresa** y ratificacion D03/D08; conservar RN-07 y excepciones hasta 2026-12-24 sin renovacion automatica. No repetir apply F5: ya ejecutado; usar solo check-migration aislado del runbook.
