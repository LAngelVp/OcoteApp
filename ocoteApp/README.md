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

Estado al 2026-11-24 local: scaffold Angular sin modulos OCOTE; base tecnica F1 en [backend/README.md](backend/README.md), PostgreSQL 18.4 con solo alembic_version y release_history, roles runtime/migrador y respaldo/restauracion aislada probados. Base anterior conservada. F0 consolidado; F1 integral NO cerrado por puertas formales y homologaciones pendientes. Evidencia y siguiente paso en [roadmap, seccion 6](docs/03-estado-actual-y-roadmap.md#6-ejecucion-local-de-la-base-tecnica-f1). No implementar negocio sin nueva autorizacion y puertas de fase.

Fundacion documental 2.0: permisos por menu/ruta/accion/datos, 19 tablas objetivo, parametros/catalogos en BD y secretos fuera de ella, solicitudes de fecha auditables y exports internos JSON/CSV. Colaborador solo tareas asignadas, nunca agregados o evaluaciones. Son especificaciones, NO funcionalidades instaladas. API externas/SSO/ERP/mensajeria/IA/importadores fuera de MVP. Aprobaciones D01-D08 y compatibilidad D07 pendientes segun fase.

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

El cierre documental previo comprobo referencias, ejemplos JSON, IDs, inventario/FK y coherencia de permisos/configuracion/entrega. La ejecucion F1 posterior verifico 31 pruebas backend, lint/dependencias, HTTP real y PostgreSQL real con roles, migracion/no-op y restauraciones aisladas. Los 16 mocks previos no se reejecutaron: sus helpers no cambiaron. Resultados y limites en el roadmap y README del backend.

## Frontend existente

Node compatible con Angular 18.2 y npm; revisar D07 antes de cambiar versiones o lockfile.

```bash
npm ci
npm start
```

Servidor de desarrollo por defecto: http://localhost:4200/ (muestra el scaffold, no una aplicacion OCOTE implementada). Comandos disponibles: npm run build y npm test; Karma requiere navegador. Esta entrega no ejecuto build ni pruebas Angular.

## Siguiente fase

La autorizacion expresa F1 produjo unicamente la base tecnica local; no identidad ni negocio. Falta ratificar D01 (America/Mexico_City es supuesto), D05, D06 y D07 y satisfacer las puertas restantes de F1 antes de declarar su cierre integral. Siguiente paso hacia F2: registrar esas decisiones y aprobar D02/D04 y la custodia/bootstrap del primer admin; autorizar F2 para identidad, permisos y administracion con migraciones propias. No crear el resto de las 19 tablas ni componentes funcionales Angular por anticipado. DoD/gates y orden F0-F7 en roadmap.
