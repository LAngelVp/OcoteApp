#!/usr/bin/env bash
set +x
set -euo pipefail

usage() {
  printf '%s\n' \
    'Usage: bash scripts/db-start.sh [--check] [--local-dev]' \
    'Local development only. Never initializes, resets, migrates or stops a cluster.' \
    '--check      Read-only: require a running local cluster and an existing database.' \
    '--local-dev  Use the documented local-development password if PGPASSWORD is unset.' \
    'Environment: APP_ENV=development|test, OCOTE_PG_PORT=5432,' \
    'OCOTE_PG_USER=postgres, OCOTE_DB_NAME=ocoteAppDatabase, PGPASSWORD or a libpq password file.'
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

check_only=false
local_dev=false
for argument in "$@"; do
  case "$argument" in
    --check) check_only=true ;;
    --local-dev) local_dev=true ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; fail "Unknown argument: $argument" ;;
  esac
done

case "${APP_ENV:-development}" in
  development|test) ;;
  *) fail 'This helper is restricted to development/test environments.' ;;
esac

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
project_dir=$(cd -- "$script_dir/.." && pwd -P)
database_dir="$project_dir/database"
binary_dir="$database_dir/postgres/bin"
[[ -f "$database_dir/data/PG_VERSION" ]] || fail 'Missing initialized cluster: database/data/PG_VERSION. Restore or provision it explicitly; no initdb is performed.'
data_dir=$(cd -- "$database_dir/data" && pwd -P)
log_dir="$database_dir/logs"
lock_dir="$database_dir/.ocote-start.lock"
port=${OCOTE_PG_PORT:-5432}
db_user=${OCOTE_PG_USER:-postgres}
db_name=${OCOTE_DB_NAME:-ocoteAppDatabase}
[[ "$port" =~ ^[0-9]{1,5}$ ]] || fail 'OCOTE_PG_PORT must be an integer between 1 and 65535.'
port=$((10#$port))
((port >= 1 && port <= 65535)) || fail 'OCOTE_PG_PORT is out of range.'
[[ "$db_name" =~ ^[a-zA-Z][a-zA-Z0-9_]{0,62}$ ]] || fail 'OCOTE_DB_NAME must be an ASCII SQL identifier of at most 63 characters; case is preserved.'
case "$db_name" in postgres|template0|template1) fail 'System databases cannot be the application database.' ;; esac
[[ "$db_user" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || fail 'OCOTE_PG_USER must be a lowercase SQL identifier.'

executable_suffix=''
if [[ -x "$binary_dir/pg_ctl.exe" ]]; then
  executable_suffix='.exe'
fi
for tool in postgres pg_ctl pg_isready psql createdb; do
  [[ -x "$binary_dir/$tool$executable_suffix" ]] || fail "Missing executable: database/postgres/bin/$tool$executable_suffix"
done

pg() {
  local tool=$1
  shift
  "$binary_dir/$tool$executable_suffix" "$@"
}

cluster_major=$(<"$data_dir/PG_VERSION")
cluster_major=${cluster_major//$'\r'/}
binary_version=$(pg postgres --version)
[[ "$binary_version" =~ PostgreSQL\)\ ([0-9]+) ]] || fail 'Cannot determine PostgreSQL binary version.'
[[ "${BASH_REMATCH[1]}" == "$cluster_major" ]] || fail 'Binary/cluster major-version mismatch. Do not initialize or upgrade the existing data directory.'

unset PGSERVICE PGSERVICEFILE PGOPTIONS
export PGHOSTADDR=127.0.0.1 PGCONNECT_TIMEOUT=5
if [[ "$local_dev" == true && -z "${PGPASSWORD:-}" ]]; then
  export PGPASSWORD=holamundo
fi

lock_owned=false
cleanup() {
  if [[ "$lock_owned" == true ]]; then
    rmdir -- "$lock_dir" || printf 'WARNING: cannot remove helper lock; inspect it manually.\n' >&2
  fi
  unset PGPASSWORD
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "$check_only" == false ]]; then
  mkdir -- "$lock_dir" 2>/dev/null || fail 'Another helper may be running (database/.ocote-start.lock). Inspect before retrying; never delete postmaster.pid.'
  lock_owned=true
fi

if pg pg_ctl -D "$data_dir" status >/dev/null 2>&1; then
  printf 'Cluster already running.\n'
else
  status=$?
  [[ "$status" == 3 ]] || fail "pg_ctl status failed (exit $status); no start attempted."
  [[ "$check_only" == false ]] || fail 'Cluster is stopped. Run without --check to start it.'
  [[ ! -e "$data_dir/postmaster.pid" ]] || fail 'Unexpected postmaster.pid in a stopped cluster; inspect processes and logs manually.'
  if pg pg_isready -q -h 127.0.0.1 -p "$port" -t 3; then
    fail 'The selected port already serves PostgreSQL, but not this running cluster. No start attempted.'
  else
    readiness=$?
    [[ "$readiness" == 2 ]] || fail "Port is not safely available (pg_isready exit $readiness)."
  fi
  mkdir -p -- "$log_dir"
  printf 'Starting local cluster on 127.0.0.1:%s.\n' "$port"
  pg pg_ctl -D "$data_dir" -l "$log_dir/postgres.log" \
    -o "-h 127.0.0.1 -p $port" -w -t 30 start || fail 'Startup failed; inspect database/logs/postgres.log. No cluster files were reset.'
fi

pg pg_isready -q -h 127.0.0.1 -p "$port" -t 3 || fail 'Cluster is not ready at the selected local endpoint; no database creation attempted.'
psql_args=(-X -w -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$port" -U "$db_user")
actual_data=$(pg psql "${psql_args[@]}" -d postgres -Atc 'SHOW data_directory;') || fail 'Cannot authenticate or verify cluster identity.'
actual_data=${actual_data//$'\r'/}
case "${OSTYPE:-}" in
  msys*|cygwin*)
    command -v cygpath >/dev/null || fail 'cygpath is required on Git Bash/Cygwin.'
    actual_data=$(cygpath -u "$actual_data")
    ;;
esac
[[ -d "$actual_data" ]] || fail 'Server data_directory does not resolve to a local directory.'
actual_data=$(cd -- "$actual_data" && pwd -P)
expected_data="$data_dir"
case "${OSTYPE:-}" in
  msys*|cygwin*) actual_data=${actual_data,,}; expected_data=${expected_data,,} ;;
esac
[[ "$actual_data" == "$expected_data" ]] || fail 'Endpoint belongs to a different data_directory; no database creation attempted.'

database_exists() {
  pg psql "${psql_args[@]}" -d postgres -At -v "ocote_db=$db_name" <<'SQL'
SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'ocote_db');
SQL
}

exists=$(database_exists) || fail 'Cannot read the database catalog.'
exists=${exists//$'\r'/}
case "$exists" in
  t) printf 'Database %s already exists; no changes made to it.\n' "$db_name" ;;
  f)
    [[ "$check_only" == false ]] || fail "Database $db_name is missing. Run without --check to create it."
    if pg createdb -w -h 127.0.0.1 -p "$port" -U "$db_user" \
      --maintenance-db=postgres --encoding=UTF8 --template=template0 -- "$db_name"; then
      printf 'Database %s created. No schemas or business tables were generated.\n' "$db_name"
    else
      exists=$(database_exists) || fail 'Database creation and catalog verification failed.'
      exists=${exists//$'\r'/}
      [[ "$exists" == t ]] || fail 'Cannot create application database.'
      printf 'Database %s was created concurrently; keeping it unchanged.\n' "$db_name"
    fi
    ;;
  *) fail 'Unexpected response from the database catalog.' ;;
esac

pg psql "${psql_args[@]}" -d "$db_name" -Atc 'SELECT 1;' >/dev/null || fail 'Application database exists but is not accessible.'
printf 'OK: %s on 127.0.0.1:%s, database=%s.\n' "$binary_version" "$port" "$db_name"