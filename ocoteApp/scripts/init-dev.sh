#!/usr/bin/env bash
set +x
set -euo pipefail

check_only=false
for argument in "$@"; do
  case "$argument" in
    --check) check_only=true ;;
    --help|-h)
      printf '%s\n' \
        'Uso: bash scripts/init-dev.sh [--check]' \
        'Solo desarrollo/test. Prepara o verifica PostgreSQL y ocoteAppDatabase.' \
        '--check no arranca, crea bases ni prepara directorios.' \
        'No instala dependencias, inicializa clusters ni ejecuta migraciones/seeds.'
      exit 0
      ;;
    *) printf 'ERROR: argumento desconocido: %s\n' "$argument" >&2; exit 1 ;;
  esac
done

case "${APP_ENV:-development}" in
  development|test) ;;
  *) printf 'ERROR: init-dev solo permite APP_ENV=development/test.\n' >&2; exit 1 ;;
esac
if [[ -n "${OCOTE_DB_NAME:-}" && "$OCOTE_DB_NAME" != ocoteAppDatabase ]]; then
  printf 'ERROR: init-dev requiere OCOTE_DB_NAME=ocoteAppDatabase; revisa tu entorno anterior. No se renombra ni copia otra base.\n' >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
project_dir=$(cd -- "$script_dir/.." && pwd -P)
export OCOTE_DB_NAME=ocoteAppDatabase
export PGPASSWORD="${PGPASSWORD:-holamundo}"
trap 'unset PGPASSWORD' EXIT
helper_args=()
if [[ "$check_only" == true ]]; then
  helper_args+=(--check)
fi
bash "$script_dir/db-start.sh" "${helper_args[@]}"
if [[ "$check_only" == false ]]; then
  mkdir -p -- "$project_dir/database/logs"
fi

printf '\nResumen OCOTE (desarrollo)\n'
printf 'PostgreSQL: listo en 127.0.0.1:%s; cluster local verificado.\n' "${OCOTE_PG_PORT:-5432}"
printf 'Base: ocoteAppDatabase accesible; datos existentes conservados.\n'
for directory in backend/.venv backend/alembic node_modules; do
  if [[ -d "$project_dir/$directory" ]]; then
    printf '%s: presente\n' "$directory"
  else
    printf '%s: pendiente/no encontrado\n' "$directory"
  fi
done
printf '%s\n' \
  'No se instalaron dependencias ni se aplicaron migraciones o seeds.' \
  'Siguiente paso: revisar docs/03-estado-actual-y-roadmap.md y autorizar/completar F1.' \
  'Antes de migrar: seguir el protocolo de respaldo, versionado y contingencia de docs/04-entorno-y-portabilidad.md.'