# OCOTE: entorno local y portabilidad

Estado vigente: [incremento F7 acotado instalado/verificado local/sintetico](03-estado-actual-y-roadmap.md#cierre-del-incremento-f7-acotado). PG18.4/ocoteAppDatabase/head0006/26 tablas/siete releases, datos previos preservados. API127.0.0.1:8000 activa, live/ready200, mantenimiento retirado; relevo administrativo DPAPI eliminado, no exportado al runtime. Raiz de boveda separada sellada fuera del checkout, autenticacion/origen/cookies/bootstrap existentes preservados. Angular21/build171 pruebas/visual1280-360 CSS, PG0:105/73 omitidas, PG1:178, Ruff/pip aprobados. Custodia incompleta y proveedores vacios/cargas cerradas. Setup Wizard e instalador/empaquetador in-house diferidos al cierre final posterior a branding/F8..F12; fases aun no autorizadas. Inventarios F6/bloqueos documentales siguientes son historicos en el alcance sustituido por esta acta, no autorizan reset ni otra migracion.

Retoma F7: usar consola /administracion/infraestructura en origen HTTPS autorizado8443; API sigue loopback8000. La revision visual uso servidor independiente8444 y API100% interceptada: no es origen de autenticacion real y no se cambia AUTH_ORIGIN para usarlo. El proceso existente8443 servia compilacion previa; recargar/reiniciar su frontend con el codigo actual antes de operar la consola, sin publicar8444 ni fabricar Origin/Referer. Raiz actual en LOCALAPPDATA/OCOTE/vault/<instance_uuid>/master.dpapi, nunca copiar al chat/checkout; ligada al usuario/equipo Windows. Backups privados con copia DPAPI y bitacora se referencian en acta19. Mas ensayos UUID requieren nueva authorize privada visible; ausencia/caducidad falla cerrada. No repetir apply0006, helpers apply historicos ni inicializar otra raiz.

Version documental: 2.1 con F6 local,2026-11-25. Secciones1..8 describen desarrollo/retoma y referencias historicas, no instalador cliente; seccion9 especifica portabilidad empresarial futura, sin ejecucion autorizada. Entrega en [guia05](05-paquetizacion-instalacion-y-actualizaciones.md), homologacion pendiente F7. Complementa [SDD](01-spec-driven-development.md), [arquitectura](02-arquitectura.md), [roadmap](03-estado-actual-y-roadmap.md) y [AGENTS.md](../AGENTS.md). Estado/excepciones en [F6](03-estado-actual-y-roadmap.md#17-analitica-evaluaciones-y-exports-f6-local-2026-11-25).

## 1. Estado real y limites

Diagnostico de entorno tras actualizar Angular: el editor conserva errores de Language Service para standalone/imports Material incluso en vistas existentes; CLI21/build y171 tests, incluido template F7 real, aprobados. Reiniciar/refrescar servicio de lenguaje/editor antes de interpretar esos diagnosticos como fallos nuevos; no afirmar diagnosticos limpios ni cambiar imports validos para ocultarlos. El servidor8443 preexistente tambien servia build anterior;8444 fue exclusivamente revision sintetica, no origen auth alternativo.

| Elemento       | Estado comprobado                                                                                                           |
| -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Frontend       | Angular18.2 SPA/SCSS en raiz; F4-F6/analitica/evaluaciones/exports,164 ChromeHeadless/build y revision sintetica; aceptacion pendiente |
| Backend        | Python3.12/FastAPI/SQLAlchemy/psycopg/Alembic; F1-F3/F5/F6,30 pruebas focales F6; privado/ClamAV fail-closed sin configurar, F7 bloqueado |
| Binarios       | database/postgres/bin; postgres --version devuelve PostgreSQL 18.4 Windows                                                  |
| Cluster        | database/data, inicializado previamente; PG_VERSION contiene 18                                                             |
| Logs           | database/logs/postgres.log; no versionados                                                                                  |
| Endpoint       | 127.0.0.1:5432 por defecto; comprobado listen_addresses=127.0.0.1 y autenticacion host SCRAM-SHA-256                        |
| Base objetivo  | ocoteAppDatabase exacta; head20261125_0005,19 tablas dominio/20 contando Alembic/seis releases terminales; datos previos/bootstrap preservados |
| Usuario local  | postgres, superusuario SOLO para preparacion/desarrollo local                                                               |
| Password local | `holamundo`, credencial conocida y debil, EXCLUSIVA de desarrollo local; NUNCA produccion, red compartida o datos reales    |

La propuesta documental anterior mencionaba PostgreSQL 16; la evidencia es 18.4/cluster 18. Se actualiza D06, no se hizo upgrade ni se edito PG_VERSION. Usar binarios de la misma version mayor que el cluster; decidir y validar actualizaciones minor en F1, nunca descargar versiones automaticamente sobre esta instalacion.

La base anterior ocote permanece intacta: no se renombra, copia, importa ni borra automaticamente. En otro equipo puede no existir. Si contiene datos utiles, inventariar y planificar su traslado con respaldo/aprobacion; crear ocoteAppDatabase no migra su contenido. Libpq/createdb reciben el nombre exacto; en SQL manual de administracion un identificador de esta base requeriria comillas dobles ("ocoteAppDatabase"), nunca asumir que un nombre sin comillas conserva mayusculas.

F1-F3 consolidados y F4-F6 autorizadas/implementadas tecnicamente solo local/sintetico; aceptacion del operador/cierre operativo F5 pendientes. Bootstrap/configuracion/datos previos preservados, no repetir ni sobrescribir; [runbook](../backend/README.md#bootstrap-y-configuracion-f2). postgres no es admin RF-01 ni runtime. Excepciones sin suplente/D07 soporte/61 alertas extendidas a F6 hasta2026-12-24, sin red compartida/entradas no confiables. D03/D08 ratificados, F7 bloqueado; no produccion/nube. Almacenamiento externo/ClamAV son decisiones explicitas del operador, ausentes: cargas cerradas, [puerta y parametros](../backend/README.md#evidencias-y-vistas-f5). Artefactos F6 privados fuera del checkout en LOCALAPPDATA/OCOTE/f6-evidence. CREATE temporal para btree_gist se autorizo/revoco en release, sin permiso general ni runtime elevado; futuras migraciones requieren su protocolo/autorizacion.

## 2. Credenciales y configuracion

- La password local se publica aqui por requisito explicito del proyecto: considerarla publica, no un secreto reutilizable. Nunca usarla en produccion ni como password de otros servicios. No inferir que este helper sea apto para produccion por cambiar una variable.
- [.env.example](../.env.example) contiene nombres de variables y valores no sensibles; copiarla a .env e introducir valores locales sin versionarlos. El helper NO carga ni ejecuta .env automaticamente; exportar variables deliberadamente. No hacer `source` de archivos recibidos de terceros.
- [init-dev.sh](../scripts/init-dev.sh) usa `PGPASSWORD="${PGPASSWORD:-holamundo}"` en su proceso, SOLO development/test. Si esta vacia/no definida, usa la credencial local conocida. No imprime la password ni la pasa en argumentos de psql/createdb; la del entorno prevalece.
- [db-start.sh](../scripts/db-start.sh) sigue disponible como helper inferior: solo activa ese fallback con --local-dev. Para PGPASSFILE protegido y sin fallback usar db-start.sh sin --local-dev y con PGPASSWORD sin definir. En init-dev, el fallback PGPASSWORD prevalece sobre PGPASSFILE: no usarlo como lector transparente de otro password file.
- PGPASSWORD es temporal al proceso, no una caja fuerte: un usuario privilegiado puede inspeccionar entornos. Evitar shell tracing (`bash -x`), capturas de entorno, logs y URLs con password. El helper deshabilita xtrace y nunca solicita credenciales interactivamente. Para una credencial real usar gestor de secretos/archivo de acceso restringido.
- F1 creo ocote_runtime sin superusuario y ocote_migrador separado, passwords aleatorias diferentes. Backend carga backend/.env protegido; AuthSettings agrega backend/.local/auth.env generado por CLI, nunca ejecuta shell. [Plantilla](../backend/.env.example) sin secretos. No repetir provision, init-auth ni sobrescribir configuracion/claves existentes; no hardcodear postgres/holamundo en backend/SPA/SQL productivos.

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

Host fijo 127.0.0.1: no parametro para BD remota. Helper ignora servicios/opciones libpq heredados que redirijan conexion. DATABASE_URL es secreto; ORGANIZATION_TIMEZONE=America/Mexico_City ratificada D01, solo bootstrap, nunca override runtime. Helper no los consume. F2 crea estructuras de parametros/catalogos vacias: admin introduce datos explicitamente. Passwords/DSN/claves en entorno/gestor, nunca system_settings.

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

F1-F3/F5/F6 ejecutaron backups/restores aislados; evidencia vigente/hashes en [acta17](03-estado-actual-y-roadmap.md#17-analitica-evaluaciones-y-exports-f6-local-2026-11-25). Comandos F1-F3/F5 son historicos: no usarlos en origen F6 ni repetir provision/rehearse/verify-existing/apply. Revisiones0001..0005 y herramientas f1_local..f6_local/f6_visual inmutables. Ensayo F6 UUID solo con autorizacion PG; no se ejecuta por docs. Fragmento siguiente es entrenamiento historico, no gate de release ni instrucciones cliente. Dumps sin archivos publicados no prueban backup integral BD/evidencia; volumen no equivale a backup.

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

### SPA HTTPS local F4

API ya existente en127.0.0.1:8000; no iniciar otra ni regenerar auth.env. Si no esta activa y se autoriza arrancarla, seguir runbook backend. Con node_modules existente/revisado, sin reinstalar ni actualizar lock:

```bash
npm start -- --host 127.0.0.1 --port 8443 --ssl --no-open
```

Abrir https://localhost:8443/login: AUTH_ORIGIN observado es exactamente https://localhost:8443, no https://127.0.0.1:8443 ni HTTP:4200. Angular escuchaIPv4 para evitar el listenerIPv6 localhost inaccesible observado; conserva Host/Origin localhost en navegador. Proxy /api a loopback8000 con changeOrigin=false, sin logs de cuerpos/cabeceras. Certificado ng serve autofirmado requiere aceptacion/confianza local del operador; la automatizacion solo lo acepto en su sesion, sin instalar CA ni configurar TLS productivo. Si puerto ajeno ocupado, no matar proceso ni cambiar origen auth: coordinar puerto/certificado con operador. Web Locks requieren navegador compatible/contexto seguro; ausencia falla cerrada. Sin cookies/token por storage, sin bajar Secure ni CORS permisivo.

Siguiente paso instalado: operador confirma custodia/bootstrap sin overwrite y acepta recorridos F4-F6; cierre operativo F5/almacenamiento privado/ClamAV reales y ensayos D05 siguen pendientes. D03/D08 ya ratificados para F6; F7 requiere autorizacion nueva. Head instalado0005 segun acta17, Angular conserva origen8443; procesos no se consultan ni arrancan por esta tarea documental. Mensaje heredado del helper sobre F1 no sustituye ese estado. Sin seeds/cargas de prueba ni restore sobre origen.

## 9. Portabilidad empresarial proyectada

Solo RF-16..35/D09..16, pendiente F7..F12. El flujo completo de instalacion/actualizacion es fuente unica en [guia05,seccion9](05-paquetizacion-instalacion-y-actualizaciones.md#9-entrega-empresarial-sin-archivos-operativos) y conserva [protocolo de release](05-paquetizacion-instalacion-y-actualizaciones.md#7-actualizacion-controlada). Esta seccion define frontera de portabilidad/diagnostico, no nuevos comandos ni reemplazo de herramientas historicas. No tocar .env actuales, roles, directorios de BD o utilidades para implementar el ejemplo.

### Tres conjuntos persistentes

| Conjunto | Autoridad/ubicacion futura | Como trasladar sin archivos editables |
| --- | --- | --- |
| Bootstrap minimo | Almacen SO/registro sellado del instalador, fuera checkout; destino PG/SSL/CA inicial, credenciales de conexion por identidad y referencia MASTER_ENCRYPTION_KEY | Asistente local autorizado verifica host/destino y vuelve a sellar para identidad SO nueva; no copiar registro ligado a otro equipo ni editar DSN a mano |
| Configuracion y secretos | PostgreSQL: settings/perfiles/politicas/flags/revisiones y boveda AEAD; certs publicos y metadatos de activos privados | Backup/restore conserva UUID/version/referencias; descifrar exige material de recuperacion de raiz por canal independiente; no export de secretos en claro ni reconstruccion desde defaults |
| Datos/objetos/artefactos | BD, evidencia/cuarentena/objetos, respaldos cifrados y releases firmadas en almacenamiento privado homologado | Manifest consistente BD+objetos+hashes; restituir ACL/identidades/roles/certificados y verificar lectura; nunca copiar data PG activa ni confundir paquete con datos |

No se promete cero archivos fisicos: servicio/PG/objetos/backups/certificados materializados siguen existiendo. Se elimina la edicion operativa de .env, JSON, YAML, proxy, rutas o passwords por el cliente; el instalador/supervisor los administra si una dependencia requiere materializacion. No dejar copias editables como segunda fuente de verdad. API no puede resolver problemas de conexion usando credenciales migrador ni pasar a una BD alternativa.

### Destinos y certificado

Wizard ofrece PG local portable incluido o PostgreSQL18 externo/gestionado por red privada; formularios exactos en [SDD](01-spec-driven-development.md#formularios-de-instalacion-y-configuracion). Local solo inicia cluster nuevo si destino vacio se confirma; servidor existente se inventaria y exige flujo de adopcion/upgrade, sin initdb/reset/PID borrado. No copiar los binarios/cluster de desarrollo como paquete cliente ni usar holamundo. Postgres portable por SO/arquitectura debe redistribuirse con licencia/procedencia/parche verificados; otra mayor/proveedor no se homologa por aceptar host/puerto.

Remoto: host DNS/puerto/base exacta, roles distintos, sslmode/CA y verificacion de certificado por cada DSN. require cifra sin autenticar servidor y verify-ca no verifica hostname: se muestran para diagnostico aislado, no satisfacen activacion gestionada que exige verify-full. Un error CA/SAN/fecha bloquea instalacion; no fallback, desactivar validacion ni aceptar certificado por un clic. CA inicial publica se sella con conexion por necesidad de arranque; CA de proveedores posteriores vive en BD. Rotacion verifica nuevo/antiguo durante ventana aprobada y renueva pools automaticamente tras drenar sin perder transacciones.

Credenciales runtime/migrador se capturan write-only en canal wizard temporal HTTPS emparejado; pruebas separadas verifican nombre/identidad/encoding/revision/btree_gist/grants y negativa runtime DDL. SQL de prueba solo lectura o transaccion revertida/objeto tecnico aislado aprobado, nunca tabla/registro de negocio en origen existente. Permiso de extension lo prepara DBA con autorizacion propia, no se hereda de CREATE temporal ya revocado F6. Conectividad no certifica backup/proveedor/capacidad ni autoriza migracion inicial sin confirmacion del destino.

### Cambio de equipo o proveedor

1. Aprobar plan/ventana/responsables independientes y destinos aislados; comprobar soporte de paquete/SO/PG/IdP/proveedores y claves disponibles sin mostrarlas en consola o SPA.
2. Ejecutar mediante agente homologado protocolo guia05 seccion7, detener escritores/scheduler/colas y capturar BD+objetos+config y referencias de claves; guardar pendientes/leases, no descartar entregas para fingir continuidad.
3. Restaurar en destino nuevo y recuperar raiz bajo custodios; re-sellar credenciales/CA para nuevo SO sin hacer clone de identidad productiva activa. Entorno aislado inhibe egress, workers, webhooks, feeds y SSO productivos antes de cualquier arranque: una copia de configuracion active no autoriza enviar.
4. Verificar head/grants/FK/config_revision, hashes/objetos/fotos/originales, AEAD con claves correctas y rechazo de raiz errada, caducidad CA/JWT y ultimo admin local. Probar secretos solo con sandbox deliberado, no conexiones o correos heredados contra produccion.
5. Switchover aprobado garantiza un unico escritor/instancia emisora; conserva instance_id cuando es recuperacion controlada o crea clon aislado registrado con identidad distinta. Fencing/revision y revocacion de capacidades antiguas evitan duplicar recurrencia/webhooks. Reabrir tras smoke, sin cambiar fechas RN-02/RN-06 ni finales.

Si hubo nuevas escrituras, reconciliar antes de volver a copia anterior; no rollback sin perdida prometido. Un cambio de modalidad requiere nueva evidencia operativa, no solo formulario guardado.

### Fallos y recuperacion desde UI supervisada

| Fallo | Comportamiento futuro requerido |
| --- | --- |
| BD no disponible/rol sin permisos | Live minimo, ready503; no wizard abierto ni regeneracion de bootstrap; diagnostico local autenticado, retries de lectura acotados, sin mutacion duplicada |
| Almacen SO/raiz no recuperable | Servicio bloqueado/mantenimiento; restauracion de claves bajo custodia, no generar raiz nueva sobre ciphertext existente |
| Conexion probada pero version cambia antes de instalar | Invalidar prueba ligada a destino/version,409 y reconfirmacion; no usar test antiguo para otro host |
| Configuracion BD invalida o modulo no instalado | Rechazo422/409 sin aplicar revision parcial, admin ve campos seguros; no override de entorno ni defaults |
| Rotacion/upgrade cortado | Registrar intento durable, mantener maintenance y reanudar con fencing/lock/artefacto firmado; no stamp ni editar revision aplicada |
| Servicio/proxy exige reload | Supervisor aplica automaticamente revision compatible, drena y verifica; error conserva mantenimiento, no pide al cliente editar archivos/reiniciar manualmente |

RPO/RTO, custodia, retencion y soporte exigen ensayo medido con archivos/claves y suplente, no los acredita esta especificacion. Comprobaciones de esta sesion solo Markdown/IDs/modelo/diff; ni precheck PG, builds o conexiones a proveedores.
