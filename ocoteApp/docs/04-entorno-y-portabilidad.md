# OCOTE: entorno local y portabilidad

Version documental: 2.0 con cierre F1 local, 2026-11-24. Guia de entorno/retoma local; instalacion del cliente y protocolo normativo de release se centralizan en [guia 05](05-paquetizacion-instalacion-y-actualizaciones.md), homologacion cliente pendiente F7. Complementa [SDD](01-spec-driven-development.md), [arquitectura](02-arquitectura.md), [roadmap](03-estado-actual-y-roadmap.md) y [AGENTS.md](../AGENTS.md). Estado vigente y excepciones en [acta F1](03-estado-actual-y-roadmap.md#7-cierre-formal-f1-local).

## 1. Estado real y limites

| Elemento       | Estado comprobado                                                                                                           |
| -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Frontend       | Angular 18.2 SPA/SCSS en raiz; Material/CDK, ngx-echarts/ECharts y vis-timeline con prototipo/build probados; pantalla inicial, no modulos OCOTE |
| Backend        | Python 3.12 + FastAPI + SQLAlchemy 2.0 + psycopg 3 + Alembic tecnicos existentes; solo health y revision                       |
| Binarios       | database/postgres/bin; postgres --version devuelve PostgreSQL 18.4 Windows                                                  |
| Cluster        | database/data, inicializado previamente; PG_VERSION contiene 18                                                             |
| Logs           | database/logs/postgres.log; no versionados                                                                                  |
| Endpoint       | 127.0.0.1:5432 por defecto; comprobado listen_addresses=127.0.0.1 y autenticacion host SCRAM-SHA-256                        |
| Base objetivo  | ocoteAppDatabase, nombre exacto con mayusculas; solo alembic_version y release_history; revision 20261124_0001                 |
| Usuario local  | postgres, superusuario SOLO para preparacion/desarrollo local                                                               |
| Password local | `holamundo`, credencial conocida y debil, EXCLUSIVA de desarrollo local; NUNCA produccion, red compartida o datos reales    |

La propuesta documental anterior mencionaba PostgreSQL 16; la evidencia es 18.4/cluster 18. Se actualiza D06, no se hizo upgrade ni se edito PG_VERSION. Usar binarios de la misma version mayor que el cluster; decidir y validar actualizaciones minor en F1, nunca descargar versiones automaticamente sobre esta instalacion.

La base anterior ocote permanece intacta: no se renombra, copia, importa ni borra automaticamente. En otro equipo puede no existir. Si contiene datos utiles, inventariar y planificar su traslado con respaldo/aprobacion; crear ocoteAppDatabase no migra su contenido. Libpq/createdb reciben el nombre exacto; en SQL manual de administracion un identificador de esta base requeriria comillas dobles ("ocoteAppDatabase"), nunca asumir que un nombre sin comillas conserva mayusculas.

F1 cerrado para desarrollo local/sintetico, no produccion/nube: backend/roles tecnicos, revision/no-op, backup y restore aislado probados; no usuarios/roles de negocio, login ni tablas/endpoints de dominio. El superusuario postgres no es el usuario administrador de negocio `admin` de RF-01 ni cuenta runtime. Excepciones hasta 2026-12-24: ausencia de suplente y D07 soporte/61 alertas, aceptadas separadamente; no exponer a red compartida ni procesar entradas no confiables. F2 no autorizado.

## 2. Credenciales y configuracion

- La password local se publica aqui por requisito explicito del proyecto: considerarla publica, no un secreto reutilizable. Nunca usarla en produccion ni como password de otros servicios. No inferir que este helper sea apto para produccion por cambiar una variable.
- [.env.example](../.env.example) contiene nombres de variables y valores no sensibles; copiarla a .env e introducir valores locales sin versionarlos. El helper NO carga ni ejecuta .env automaticamente; exportar variables deliberadamente. No hacer `source` de archivos recibidos de terceros.
- [init-dev.sh](../scripts/init-dev.sh) usa `PGPASSWORD="${PGPASSWORD:-holamundo}"` en su proceso, SOLO development/test. Si esta vacia/no definida, usa la credencial local conocida. No imprime la password ni la pasa en argumentos de psql/createdb; la del entorno prevalece.
- [db-start.sh](../scripts/db-start.sh) sigue disponible como helper inferior: solo activa ese fallback con --local-dev. Para PGPASSFILE protegido y sin fallback usar db-start.sh sin --local-dev y con PGPASSWORD sin definir. En init-dev, el fallback PGPASSWORD prevalece sobre PGPASSFILE: no usarlo como lector transparente de otro password file.
- PGPASSWORD es temporal al proceso, no una caja fuerte: un usuario privilegiado puede inspeccionar entornos. Evitar shell tracing (`bash -x`), capturas de entorno, logs y URLs con password. El helper deshabilita xtrace y nunca solicita credenciales interactivamente. Para una credencial real usar gestor de secretos/archivo de acceso restringido.
- F1 creo ocote_runtime sin superusuario y ocote_migrador separado, con passwords aleatorias diferentes. Backend carga solo backend/.env protegido (no ejecuta shell); plantilla [backend/.env.example](../backend/.env.example) sin secretos. No repetir provision ni sobrescribir configuracion existente; no hardcodear postgres/holamundo en Python, Angular, SQL o conexiones productivas.

Configuracion opcional sin escribir la password en historial de comandos:

```bash
read -r -s -p 'Password PostgreSQL local: ' PGPASSWORD
printf '\n'
export PGPASSWORD
bash scripts/db-start.sh --check
unset PGPASSWORD
```

Si se usa la credencial de ejemplo, introducir `holamundo` en ese prompt o usar explicitamente --local-dev. No enviar credenciales reales a agentes ni pegarlas en chats. Con PGPASSFILE, configurar permisos de usuario equivalentes a 0600/ACL privadas segun SO.

| Variable del helper | Default / significado                                                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| APP_ENV             | development; solo development/test permitidos                                                                                                      |
| OCOTE_PG_PORT       | 5432, valida 1..65535; debe coincidir con servidor ya activo                                                                                       |
| OCOTE_PG_USER       | postgres, usuario de preparacion local                                                                                                             |
| OCOTE_DB_NAME       | ocoteAppDatabase, respeta mayusculas; init-dev rechaza otro valor heredado, db-start admite identificadores ASCII validados para soporte explicito |
| PGPASSWORD          | init-dev: fallback local holamundo; db-start: sin default salvo --local-dev; entorno temporal, nunca argumento                                     |
| PGPASSFILE          | Opcional, soporte nativo libpq para archivo de passwords                                                                                           |

Host fijo 127.0.0.1: no existe parametro para BD remota. El helper ignora servicios/opciones libpq heredados que podrian redirigir conexion. DATABASE_URL es secreto del backend; ORGANIZATION_TIMEZONE=America/Mexico_City esta ratificada D01, solo entrada inicial para system_settings.organization_timezone, no override runtime. Helper no los consume. Parametros/catalogos operativos futuros en BD segun RN-07; passwords/DSN/claves en entorno protegido o gestor, nunca en system_settings.

Cliente local productivo, contenedor y PostgreSQL gestionado usan la guia 05, no init-dev. En nube se validan TLS verify-full/CA, endpoint privado, roles/extensiones, pool acotado y conexion directa de migracion. No extender informalmente el helper cambiando host ni aplicar su credencial conocida a otra instancia. El cierre F1 comprobo el cluster original ya activo y lo dejo activo, sin reiniciarlo ni homologar otra instancia.

## 3. Comprobar y arrancar desde Bash/Git Bash

Requisitos: Bash 4+ y herramientas basicas (incluidas en Git Bash), binarios PostgreSQL confiables para el SO y cluster local inicializado. En Windows ejecutar en Git Bash, no pegar sintaxis Bash directamente en PowerShell/CMD. No usar sudo ni ejecutar como administrador. En WSL usar binarios Linux y cluster compatible, no la instalacion Windows por simple suposicion.

Desde la raiz del checkout:

```bash
bash scripts/init-dev.sh --check
```

`--check` no inicia, crea, migra ni prepara directorios. Devuelve 0 solo si cluster esperado y base ya estan accesibles; devuelve 1 con diagnostico si no. Las conexiones de lectura pueden generar logs/estadisticas internos del servidor; no modifican datos de negocio.

Para iniciar solo cuando hace falta y asegurar la base:

```bash
bash scripts/init-dev.sh
bash scripts/init-dev.sh --check
```

El script resuelve las rutas desde su propia ubicacion, no desde el directorio actual; tambien admite invocacion por ruta absoluta con espacios entre comillas. No necesita chmod +x si se invoca con bash. [.gitattributes](../.gitattributes) fuerza LF en scripts .sh para evitar errores CRLF entre equipos.

init-dev delega arranque/identidad/creacion a db-start para no duplicar controles; en modo normal asegura database/logs incluso si el servidor ya corria. Presenta resumen PostgreSQL/base y existencia de backend/.venv, backend/alembic y node_modules, sin instalarlos ni ejecutarlos. Una carpeta presente no demuestra dependencias funcionales o migraciones aplicadas. Muestra siguiente paso F1; no lanza Angular/backend ni aplica seeds o Alembic al retomar.

### Algoritmo y garantias del helper

1. Rechaza APP_ENV distinto de development/test, argumentos/identificadores invalidos, binarios faltantes, cluster no inicializado y diferencias de version mayor. Nunca ejecuta initdb ni crea un data vacio.
2. En modo normal toma un lock de directorio local `database/.ocote-start.lock` para serializar dos helpers; si existe, falla sin borrarlo. En check no crea ese lock.
3. Usa pg_ctl status contra data. Si ya corre, NO reinicia ni cambia opciones. Si esta detenido, rechaza un postmaster.pid inesperado y comprueba pg_isready para detectar otra instancia en el puerto antes de arrancar.
4. Solo con puerto sin respuesta, crea logs/ si hace falta y arranca con pg_ctl -w (hasta 30 s). El equivalente conceptual desde raiz es:

```bash
./database/postgres/bin/pg_ctl -D ./database/data -l ./database/logs/postgres.log -o '-h 127.0.0.1 -p 5432' -w -t 30 start
```

5. Espera disponibilidad y autentica sin prompts con psql -X -w y ON_ERROR_STOP. Compara SHOW data_directory con la ruta canonica local; si la conexion corresponde a otro cluster, aborta sin crear bases.
6. Consulta pg_database con parametro SQL escapado por psql. Si ocoteAppDatabase existe, la conserva. Si no, usa createdb con UTF8/template0 y nombre exacto, sin tablas ni seeds. Si otro proceso la crea entre consulta y alta, vuelve a verificar el catalogo y conserva la base existente.
7. Prueba SELECT 1 en la base objetivo y libera solo su propio lock. Nunca borra archivos del cluster, modifica pg_hba.conf/postgresql.conf, migra, restaura, hace DROP/TRUNCATE ni detiene el servicio. Si arranco PostgreSQL y un paso posterior falla, lo deja corriendo para inspeccion; no intenta revertir datos.

Garantia limitada: un servicio no PostgreSQL en el puerto podria parecer sin respuesta a pg_isready; en ese caso el propio arranque fallara por bind ocupado, no se mata el proceso. pg_isready por si solo no valida password ni identidad; por eso se usa tambien pg_ctl y SHOW data_directory. El lock protege otros helpers de este checkout, no a operadores externos; no elimina carreras de administracion fuera del helper.

Para inspeccion manual de solo lectura (no sustituyen la comprobacion autenticada):

```bash
./database/postgres/bin/pg_ctl -D ./database/data status
./database/postgres/bin/pg_isready -h 127.0.0.1 -p 5432 -t 3
```

### Diagnostico seguro

| Situacion                                  | Accion                                                                                                                                                                            |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Falta postgres/bin                         | Obtener distribucion oficial/confiable para SO/arquitectura, verificar firma/checksum, no descargar automaticamente desde scripts                                                 |
| Falta data/PG_VERSION                      | Un clon no trae datos. Pedir backup o aprovisionar conscientemente un cluster nuevo; el helper se negara a inicializarlo                                                          |
| PG_VERSION distinto de binarios            | Detener la operacion; conseguir binarios compatibles o planificar migracion logica/pg_upgrade; nunca editar PG_VERSION                                                            |
| Puerto ocupado / otro data_directory       | Identificar proceso/cluster; no detenerlo automaticamente. Elegir puerto explicito solo si se aprobo y no se cambia a ciegas un servidor activo                                   |
| Password erronea / acceso denegado         | Revisar PGPASSWORD/PGPASSFILE y politicas; no activar trust ni resetear el cluster                                                                                                |
| postmaster.pid o lock de helper inesperado | Verificar procesos y logs manualmente. Nunca borrar postmaster.pid para forzar arranque. Retirar solo el lock del helper con rmdir tras comprobar que no queda otro helper activo |
| Cluster no arranca tras mover carpeta      | Revisar rutas absolutas, permisos, tablespaces, logs, version y arquitectura; conservar datos originales intactos                                                                 |

Cambiar puerto de un cluster detenido, de forma explicita:

```bash
OCOTE_PG_PORT=5433 bash scripts/init-dev.sh
```

No cambia configuracion persistente; futuras invocaciones deben usar el mismo puerto. En produccion esta utilidad no debe usarse.

## 4. Que versionar y que no

| Versionar                                                            | No versionar / distribucion aparte                                                       |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Angular fuente/configuracion y package-lock.json                     | node_modules/, dist/, caches y coverage                                                  |
| docs/, AGENTS.md, .github/copilot-instructions.md, README.md         | Historial de chats como dependencia del proyecto                                         |
| scripts/init-dev.sh, scripts/db-start.sh y scripts/db-start.test.cjs | database/postgres/ (binarios pesados y dependientes de SO)                               |
| .env.example sin secretos, .gitignore, .gitattributes                | .env, .env.\*, archivos de password, secretos de JWT/TLS                                 |
| Futuro backend fuente, pyproject/lock y migraciones Alembic          | .venv/, venv/, **pycache**/, caches Python                                               |
| Instrucciones y checksums de la distribucion aprobada                | database/data/, database/logs/, database/backups/, database/exports/ y evidencia privada |

Binarios y cluster no se guardan en Git LFS por defecto. Backups SQL/plain o custom pueden contener datos personales y credenciales de roles: mantenerlos cifrados fuera de Git y con acceso restringido, incluso si su tamano es pequeno. Solo fixtures sinteticos expresamente revisados podrian versionarse.

Verificar protecciones antes de agregar archivos:

```bash
git check-ignore database/data/PG_VERSION database/postgres/bin/pg_ctl.exe database/logs/postgres.log .env
git ls-files -- database .env
git status --short
```

El segundo comando no deberia mostrar datos/binarios/secretos. .gitignore no desrastrea ni borra historia existente: si ya se subio un secreto, revocarlo y acordar limpieza del indice/historia; un agente no debe ejecutar git rm/reset sobre datos sin autorizacion.

## 5. Retomar en otra computadora

1. Clonar el repositorio y leer README.md, AGENTS.md y docs/ en orden. Si la herramienta no descubre AGENTS.md, cargarlo explicitamente; no todos los agentes tienen el mismo mecanismo de instrucciones. Copilot lee su adaptador, que remite a la misma fuente.
2. Instalar Git/Bash y Node compatible con Angular 18.2 (equipo actual Node 22.21.1/npm 10.9.4). Instalar Python 3.12. Ejecutar npm ci solo cuando se necesite el frontend y desde locks revisados; no actualizar el lock para resolver peers sin revisar D07. ngx-echarts 18/ECharts 6 y demas librerias pasaron fixture Chrome real, build y peers, pero Angular sin soporte y alertas siguen bajo excepcion temporal; no procesar entradas no confiables ni asumir remediacion.
3. Obtener los binarios PostgreSQL para el SO/arquitectura, misma mayor 18 si se usa este cluster. En F1 registrar procedencia, archivo, checksum y minor aprobado: no estan certificados solo por pg --version.
4. Elegir instalacion nueva o restauracion. Si falta data, el helper debe fallar: aprovisionar expresamente un cluster nuevo con initdb --pwprompt y autenticacion SCRAM sobre un destino vacio confirmado, o restaurar backup en un cluster compatible aislado. No automatizar este paso ni sobrescribir una carpeta data existente. La password local aqui documentada no crea por si sola un usuario en otra maquina.
5. No copiar data en caliente. La opcion preferida entre rutas/maquinas/SO es backup logico + restauracion en cluster nuevo. Para un traslado fisico autorizado en mismo SO, parar limpiamente primero y copiar todo el cluster con permisos/tablespaces compatibles; conservar original y verificar rutas absolutas de configuracion. Nunca mover la carpeta de un servidor que aun corre.
6. Preparar .env privado y exportar solo variables necesarias: no se carga automaticamente. Ejecutar init-dev, repetirlo y ejecutar --check. Para autenticacion solo con PGPASSFILE usar el helper inferior sin --local-dev como explica seccion 2. Confirmar puerto y SHOW data_directory antes de cualquier migracion; no confundir arranque con actualizacion de esquema.
7. Leer fase/puertas y [runbook backend](../backend/README.md). Backend/Alembic ya existen: instalar lock en entorno nativo, revisar DSN/identidad y obtener autorizacion antes de provision/migracion/restore. No repetir instalacion virgen sobre la base actual ni copiar secretos del desarrollador. init-dev no demuestra que otro clon cumpla F1 ni autoriza F2.

Las rutas no deben depender de C:/Users de un desarrollador; el helper las deriva del checkout. No mover/copiar el checkout con PostgreSQL activo. Una instalacion en disco sincronizado/carpeta de red requiere evaluacion operativa: no es destino seguro por defecto para un cluster vivo.

## 6. Backup y restauracion portables

El ensayo F1 ejecuto backup y restore aislado tecnicos: evidencia y hashes en acta F1. Para repetir verificacion autorizada sobre la base tecnica existente usar verify-existing del runbook, no provision/rehearse. El fragmento manual siguiente es entrenamiento, no el gate automatico de release. Desarrollo usa pg_dump de la misma distribucion; el respaldo integral de producto debe coordinar BD y evidencias. Volumen persistente no equivale a backup.

Con credencial exportada temporalmente o PGPASSFILE, y desde raiz:

```bash
bash scripts/db-start.sh --check
mkdir -p database/backups
backup_dir=$(mktemp -d ./database/backups/ocoteAppDatabase-XXXXXX)
./database/postgres/bin/pg_dump -w -h 127.0.0.1 -p 5432 -U postgres -d ocoteAppDatabase --format=custom --file="$backup_dir/ocoteAppDatabase.dump"
./database/postgres/bin/pg_restore --list "$backup_dir/ocoteAppDatabase.dump"
unset PGPASSWORD
```

Comprobar el codigo de salida de cada paso: no considerar valido un archivo parcial si pg_dump falla. El directorio unico evita sobrescribir respaldos anteriores. Cifrar/copiar fuera del host con manifest/checksum y politicas D05/D06. `pg_restore --list` solo comprueba lectura del archivo, NO demuestra recuperacion. SQL plano via pg_dump --format=plain es alternativa portable para inspeccion controlada; nunca ejecutar SQL recibido de origen no confiable.

Restauracion: con autorizacion, crear una base NUEVA de nombre unico en un cluster compatible y ejecutar pg_restore --exit-on-error --no-owner --no-acl contra esa base, nunca --clean sobre ocoteAppDatabase ni contra produccion. Usar roles aprobados, revisar extensiones/owners y verificar tablas, revision Alembic, conteos y archivos de evidencia. No se da un comando automatico de restore para evitar sobrescribir destinos por copia/pegado.

RPO <=24 h/RTO <=4 h aprobados como objetivos de diseno, retencion minima 30 dias, backups diarios/por release y restore mensual/por release: [politica D05/D06](05-paquetizacion-instalacion-y-actualizaciones.md#31-base-aprobada-de-privacidad-y-recuperacion-d05d06). Responsable LUIS ANGEL VALLEJO - DESARROLLADOR, sin suplente por excepcion hasta 2026-12-24. Restore local+verificacion 0.482 s con solo dos tablas, no RTO/RPO productivos ni fallo de host; cifrado/copia off-host y scheduler pendientes, datos reales no autorizados. F7 debe demostrar operacion integral.

## 7. Protocolo de actualizacion por release del cliente

El procedimiento completo y unico esta en [guia 05, seccion 7](05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada), aplicable a cliente local y gestionado incluso sin DDL pendiente. Se traslada alli para evitar dos protocolos divergentes; esta referencia conserva el punto de entrada anterior.

Resumen obligatorio: artefacto firmado/head compatible y lock persistente -> mantenimiento sin escritores -> backup automatico y restore aislado verificado -> Alembic forward -> seeds conservadores -> integridad/FK/historia/fotos y smoke -> reapertura aprobada o contingencia. Fallo mantiene mantenimiento, fix-forward preferido; downgrade solo reversible/probado/autorizado y restore solo en destino aislado con switchover aprobado. Nuevas escrituras exigen reconciliacion, no rollback supuestamente sin perdida.

DDL/backfill solo en backend/alembic/versions versionado; expand/backfill/validate/contract, sin create_all, stamp, revision publicada alterada o cambios manuales. Nunca reescribir originales, task_history, audit_events o fotos finales. Seeds agregan faltantes por code/key, no pisan configuracion. release_history registra intentos y bitacora externa cubre fallos antes de que exista BD/tabla; alembic_version no es historial de despliegues.

init-dev NO implementa ese protocolo, no instala ni migra. El fragmento de backup de seccion 6 es entrenamiento manual, no el gate automatico. F1 preparo/probo ensayo tecnico local; no implementa paquete firmado ni protocolo cliente completo. F7 homologa ambas instalaciones y sus controles, sin extrapolar el resultado local.

## 8. Validaciones disponibles y siguiente paso

```bash
bash -n scripts/init-dev.sh
bash -n scripts/db-start.sh
node --test scripts/db-start.test.cjs
bash scripts/init-dev.sh --check
```

La suite usa mocks en carpetas temporales con espacios, no el cluster real: 16 pruebas de modo check, doble ejecucion, puerto/data_directory ajenos, versiones, falta de cluster/PID inesperado, fallos/carrera de createdb, lock, parametros invalidos y retoma desde otra carpeta. Comprueba nombre con mayusculas, resumen de directorios y ausencia de passwords en salida. Requiere Node 22.x/Bash; puede tardar varios minutos en Windows. No ejecutar con credenciales productivas.

Evidencia historica del helper, anterior a F1: PostgreSQL 18.4/cluster 18 ya activo en loopback. init-dev creo ocoteAppDatabase porque faltaba; repeticion y --check desde fuera del checkout exitosos, sin renombrar/borrar ocote. Entonces el objetivo estaba vacio y no habia backend ni restore. La evidencia posterior vigente de revision/roles/restore, sin leer datos legacy ni resetear el origen, esta en acta F1; no otros SO ni protocolo cliente homologados.

Siguiente paso exacto: aprobar D02/D04 y custodia/bootstrap seguro del primer admin, nombre organizacional y autorizacion expresa F2 dentro de las excepciones locales vigentes. F2-F7 y RF-\* conservan orden/criterios del roadmap; no crear negocio ni otras tablas por anticipado.
