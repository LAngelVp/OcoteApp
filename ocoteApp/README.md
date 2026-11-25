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

Estado al 2026-11-24 local: Angular sin modulos OCOTE; **F2 autorizado, implementado y verificado tecnicamente** en [backend/README.md](backend/README.md): identidad/permisos/administracion, head20261124_0002, nueve tablas F2 vacias mas release_history/alembic_version. Sin seeds ni admin inventado; bootstrap/configuracion reales pendientes del operador. Base anterior/historia preservadas. Solo Windows x64/PG18.4 local/sintetico, no produccion/nube: excepciones D06 sin suplente y D07 (Angular sin soporte/61 alertas) hasta **2026-12-24**, responsable LUIS ANGEL VALLEJO - DESARROLLADOR. [Evidencia F2](docs/03-estado-actual-y-roadmap.md#8-identidad-y-administracion-f2-local) y [excepciones F1](docs/03-estado-actual-y-roadmap.md#7-cierre-formal-f1-local). F3 no autorizado.

Fundacion documental 2.0: 19 tablas objetivo y permisos por rol/alcance; solo F1/F2 implementados, solicitudes de fecha/exports/operacion/evaluacion siguen futuros. Colaborador nunca recibe agregados/evaluaciones. Integraciones externas fuera de MVP. D01 oficial America/Mexico_City solo bootstrap; D02/D04 confirmadas para F2 sin catalogos sembrados, D03/D08 pendientes. D05/D06 base/objetivos de diseno y D07 bajo excepcion, no aprobacion productiva.

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

## Frontend existente

Node compatible con Angular 18.2 y npm; revisar D07 antes de cambiar versiones o lockfile.

```bash
npm ci
npm start
```

Servidor de desarrollo por defecto: http://localhost:4200/ (muestra el scaffold, no una aplicacion OCOTE implementada; no queda servidor iniciado). Comandos disponibles: npm run build y npm test; Karma requiere navegador. El cierre ejecuto build de produccion y `CHROME_BIN='<Chrome local>' npm test -- --watch=false --browsers=ChromeHeadless`: 6 passed. [Prototipo de compatibilidad](src/app/f1-compat.spec.ts) solo de pruebas, no pantalla ni feature productiva.

## Siguiente fase

Operador completa [bootstrap/custodia y configuracion F2](backend/README.md#bootstrap-y-configuracion-f2): origen HTTPS loopback, claves sin overwrite, admin por terminal/getpass, parametros/catalogos/grafo explicitos y configuration-status completo. No se ejecutaron esos pasos con identidad real ni se instalaron proxy/certificados. Despues resolver ejemplos temporales/D03/D08/reglas de cierre y solicitar autorizacion expresa F3. Mantener RN-07 y limites/excepciones hasta 2026-12-24 sin renovacion automatica; no crear negocio ni pantallas por anticipado.
