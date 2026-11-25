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

Estado al 2026-11-24 local: scaffold Angular sin modulos OCOTE; base tecnica F1 en [backend/README.md](backend/README.md), PostgreSQL 18.4 con solo alembic_version y release_history, roles runtime/migrador y respaldo/restauracion aislada probados. Base anterior e historia preservadas. **F1 cerrado para desarrollo local con datos sinteticos**, no produccion/nube: excepciones expresas D06 sin suplente y D07 (Angular sin soporte y 61 alertas npm) hasta **2026-12-24**, responsable LUIS ANGEL VALLEJO - DESARROLLADOR. Evidencia, limites y salida de excepciones en [acta F1](docs/03-estado-actual-y-roadmap.md#7-cierre-formal-f1-local). F2 no iniciado ni autorizado.

Fundacion documental 2.0: permisos por menu/ruta/accion/datos, 19 tablas objetivo, parametros/catalogos en BD y secretos fuera de ella, solicitudes de fecha auditables y exports internos JSON/CSV. Colaborador solo tareas asignadas, nunca agregados o evaluaciones. Son especificaciones, NO funcionalidades instaladas. API externas/SSO/ERP/mensajeria/IA/importadores fuera de MVP. D01 oficial America/Mexico_City; D05/D06 aprobados como base/objetivos de diseno, D07 con compatibilidad probada y riesgo aceptado temporalmente. D02/D03/D04/D08 siguen sus puertas.

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

## Frontend existente

Node compatible con Angular 18.2 y npm; revisar D07 antes de cambiar versiones o lockfile.

```bash
npm ci
npm start
```

Servidor de desarrollo por defecto: http://localhost:4200/ (muestra el scaffold, no una aplicacion OCOTE implementada; no queda servidor iniciado). Comandos disponibles: npm run build y npm test; Karma requiere navegador. El cierre ejecuto build de produccion y `CHROME_BIN='<Chrome local>' npm test -- --watch=false --browsers=ChromeHeadless`: 6 passed. [Prototipo de compatibilidad](src/app/f1-compat.spec.ts) solo de pruebas, no pantalla ni feature productiva.

## Siguiente fase

F1 local cerrado con las excepciones/limites del acta, sin identidad ni negocio. Antes de iniciar F2: aprobar D02/D04, nombre organizacional y custodia/bootstrap seguro del primer admin, y autorizar expresamente identidad, permisos y administracion con migraciones propias. Mantener zona D01 solo bootstrap RN-07. Resolver/remediar o revisar expresamente las excepciones antes del 2026-12-24; no renovacion automatica. No crear el resto de las 19 tablas ni componentes funcionales Angular por anticipado. DoD/gates y orden F0-F7 en roadmap.
