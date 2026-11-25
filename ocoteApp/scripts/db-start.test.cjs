const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

const helper = fs.readFileSync(path.join(__dirname, "db-start.sh"), "utf8");
const initializer = fs.readFileSync(
  path.join(__dirname, "init-dev.sh"),
  "utf8",
);
const mock = `#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd -P)
state="$root/state"
tool=$(basename -- "$0")
printf '%s %s\\n' "$tool" "$*" >> "$state/calls"
case "$tool" in
  postgres) printf 'postgres (PostgreSQL) 18.4\\n' ;;
  pg_ctl)
    case " $* " in
      *' status '*) [[ -f "$state/running" ]] && exit 0 || exit 3 ;;
      *' start '*) touch "$state/running" ;;
      *) exit 91 ;;
    esac
    ;;
  pg_isready) [[ -f "$state/running" || -f "$state/foreign_port" ]] && exit 0 || exit 2 ;;
  psql)
    case " $* " in
      *'SHOW data_directory;'*)
        if [[ -f "$state/wrong_directory" ]]; then
          printf '%s/other-data\\n' "$root"
        else
          printf '%s/database/data\\n' "$root"
        fi
        ;;
      *'SELECT 1;'*) printf '1\\n' ;;
      *)
        input=$(cat)
        [[ "$input" == *'pg_database'* ]] || exit 92
        if [[ -f "$state/exists" ]]; then printf 't\\n'; else printf 'f\\n'; fi
        ;;
    esac
    ;;
  createdb)
    [[ -f "$state/fail_create" ]] && exit 1
    touch "$state/exists"
    [[ -f "$state/create_race" ]] && exit 1
    exit 0
    ;;
  *) exit 93 ;;
esac
`;

function fixture(context, markers = []) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "ocote db test "));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const directory of [
    "scripts",
    "database/postgres/bin",
    "database/data",
    "state",
    "other-data",
  ]) {
    fs.mkdirSync(path.join(root, directory), { recursive: true });
  }
  fs.writeFileSync(path.join(root, "scripts/db-start.sh"), helper);
  fs.writeFileSync(path.join(root, "scripts/init-dev.sh"), initializer);
  fs.writeFileSync(path.join(root, "database/data/PG_VERSION"), "18\n");
  fs.writeFileSync(
    path.join(root, "database/data/preserve.txt"),
    "existing data sentinel",
  );
  for (const tool of ["postgres", "pg_ctl", "pg_isready", "psql", "createdb"]) {
    fs.writeFileSync(path.join(root, "database/postgres/bin", tool), mock, {
      mode: 0o755,
    });
  }
  for (const marker of markers)
    fs.writeFileSync(path.join(root, "state", marker), "");
  const run = (
    argumentsList = [],
    environment = {},
    entry = "db-start.sh",
    workingDirectory = root,
  ) => {
    const script = path.join(root, "scripts", entry).replaceAll("\\", "/");
    const result = spawnSync("bash", [script, ...argumentsList], {
      cwd: workingDirectory,
      env: {
        ...process.env,
        APP_ENV: "test",
        PGPASSWORD: "fixture-only",
        OCOTE_PG_PORT: "5432",
        OCOTE_PG_USER: "postgres",
        OCOTE_DB_NAME: "",
        ...environment,
      },
      encoding: "utf8",
      timeout: 60000,
    });
    assert.equal(result.error, undefined, result.error?.message);
    result.outputText = result.stdout + result.stderr;
    assert.equal(result.outputText.includes("fixture-only"), false);
    assert.equal(result.outputText.includes("holamundo"), false);
    assert.equal(
      fs.readFileSync(path.join(root, "database/data/preserve.txt"), "utf8"),
      "existing data sentinel",
    );
    return result;
  };
  const calls = () => {
    const filename = path.join(root, "state/calls");
    return fs.existsSync(filename) ? fs.readFileSync(filename, "utf8") : "";
  };
  return { root, run, calls };
}

test("check on a stopped cluster does not start, create or prepare log/lock directories", (context) => {
  const state = fixture(context);
  assert.equal(state.run(["--check"]).status, 1);
  assert.doesNotMatch(state.calls(), /pg_ctl .* start|createdb /);
  assert.equal(fs.existsSync(path.join(state.root, "database/logs")), false);
  assert.equal(
    fs.existsSync(path.join(state.root, "database/.ocote-start.lock")),
    false,
  );
});

test("starting twice starts once and creates the database only once, including paths with spaces", (context) => {
  const state = fixture(context);
  const first = state.run();
  assert.equal(first.status, 0, first.outputText);
  const second = state.run();
  assert.equal(second.status, 0, second.outputText);
  assert.equal((state.calls().match(/pg_ctl .* start/g) || []).length, 1);
  assert.equal((state.calls().match(/^createdb /gm) || []).length, 1);
  assert.match(state.calls(), /createdb .* -- ocoteAppDatabase/);
  assert.equal(
    fs.existsSync(path.join(state.root, "database/.ocote-start.lock")),
    false,
  );
});

test("check succeeds on an existing database without a start or create command", (context) => {
  const state = fixture(context, ["running", "exists"]);
  const result = state.run(["--check"]);
  assert.equal(result.status, 0, result.outputText);
  assert.doesNotMatch(state.calls(), /pg_ctl .* start|createdb /);
  assert.equal(fs.existsSync(path.join(state.root, "database/logs")), false);
});

test("check does not create a missing database on a running cluster", (context) => {
  const state = fixture(context, ["running"]);
  assert.equal(state.run(["--check"]).status, 1);
  assert.doesNotMatch(state.calls(), /createdb /);
});

test("a different PostgreSQL instance on the port prevents startup", (context) => {
  const state = fixture(context, ["foreign_port"]);
  assert.equal(state.run().status, 1);
  assert.doesNotMatch(state.calls(), /pg_ctl .* start|createdb /);
});

test("a running endpoint with a different data_directory prevents database creation", (context) => {
  const state = fixture(context, ["running", "wrong_directory"]);
  assert.equal(state.run().status, 1);
  assert.doesNotMatch(state.calls(), /createdb /);
});

test("a binary/cluster major mismatch is rejected before contacting PostgreSQL", (context) => {
  const state = fixture(context);
  fs.writeFileSync(path.join(state.root, "database/data/PG_VERSION"), "16\n");
  assert.equal(state.run().status, 1);
  assert.doesNotMatch(state.calls(), /pg_ctl |pg_isready |psql |createdb /);
});

test("missing cluster and stale postmaster.pid are never reset", (context) => {
  const state = fixture(context);
  fs.writeFileSync(
    path.join(state.root, "database/data/postmaster.pid"),
    "stale sentinel",
  );
  assert.equal(state.run().status, 1);
  assert.equal(
    fs.readFileSync(
      path.join(state.root, "database/data/postmaster.pid"),
      "utf8",
    ),
    "stale sentinel",
  );
  fs.unlinkSync(path.join(state.root, "database/data/PG_VERSION"));
  assert.equal(state.run().status, 1);
  assert.equal(
    fs.existsSync(path.join(state.root, "database/data/PG_VERSION")),
    false,
  );
  assert.doesNotMatch(state.calls(), /pg_ctl .* start|createdb /);
});

test("creation failure returns nonzero and releases the helper lock", (context) => {
  const state = fixture(context, ["running", "fail_create"]);
  assert.equal(state.run().status, 1);
  assert.equal(
    fs.existsSync(path.join(state.root, "database/.ocote-start.lock")),
    false,
  );
});

test("an external concurrent create is accepted only after rechecking the catalog", (context) => {
  const state = fixture(context, ["running", "create_race"]);
  const result = state.run();
  assert.equal(result.status, 0, result.outputText);
  assert.match(result.outputText, /created concurrently/);
});

test("an existing helper lock is preserved rather than removed", (context) => {
  const state = fixture(context);
  fs.mkdirSync(path.join(state.root, "database/.ocote-start.lock"));
  assert.equal(state.run().status, 1);
  assert.equal(
    fs.existsSync(path.join(state.root, "database/.ocote-start.lock")),
    true,
  );
  assert.doesNotMatch(state.calls(), /pg_ctl |psql |createdb /);
});

test("invalid ports, database identifiers, arguments and production mode fail before database access", (context) => {
  const state = fixture(context);
  for (const environment of [
    { OCOTE_PG_PORT: "70000" },
    { OCOTE_PG_PORT: "bad-port" },
    { OCOTE_DB_NAME: "invalid;sql" },
    { OCOTE_DB_NAME: "postgres" },
    { APP_ENV: "production" },
  ]) {
    assert.equal(state.run([], environment).status, 1);
  }
  assert.equal(state.run(["--unknown"]).status, 1);
  assert.equal(state.calls(), "");
});

test("init-dev works outside the checkout, repeats safely and summarizes optional directories", (context) => {
  const state = fixture(context, ["running", "exists"]);
  const first = state.run([], {}, "init-dev.sh", os.tmpdir());
  assert.equal(first.status, 0, first.outputText);
  assert.match(first.outputText, /Base: ocoteAppDatabase accesible/);
  for (const directory of [
    "backend/.venv",
    "backend/alembic",
    "node_modules",
  ]) {
    assert.ok(
      first.outputText.includes(directory + ": pendiente/no encontrado"),
    );
    fs.mkdirSync(path.join(state.root, directory), { recursive: true });
  }
  const second = state.run([], {}, "init-dev.sh", os.tmpdir());
  assert.equal(second.status, 0, second.outputText);
  for (const directory of [
    "backend/.venv",
    "backend/alembic",
    "node_modules",
  ]) {
    assert.ok(second.outputText.includes(directory + ": presente"));
  }
  assert.equal(fs.existsSync(path.join(state.root, "database/logs")), true);
  assert.doesNotMatch(state.calls(), /pg_ctl .* start|createdb /);
});

test("init-dev check uses the development fallback without printing it or creating logs", (context) => {
  const state = fixture(context, ["running", "exists"]);
  const result = state.run(["--check"], { PGPASSWORD: "" }, "init-dev.sh");
  assert.equal(result.status, 0, result.outputText);
  assert.equal(fs.existsSync(path.join(state.root, "database/logs")), false);
  assert.doesNotMatch(state.calls(), /pg_ctl .* start|createdb /);
});

test("init-dev diagnoses missing binaries and never initializes a missing cluster", (context) => {
  const state = fixture(context);
  fs.unlinkSync(path.join(state.root, "database/postgres/bin/pg_ctl"));
  const missingBinary = state.run([], {}, "init-dev.sh");
  assert.equal(missingBinary.status, 1);
  assert.match(missingBinary.outputText, /Missing executable/);
  fs.unlinkSync(path.join(state.root, "database/data/PG_VERSION"));
  const missingCluster = state.run([], {}, "init-dev.sh");
  assert.equal(missingCluster.status, 1);
  assert.match(missingCluster.outputText, /Missing initialized cluster/);
  assert.equal(
    fs.existsSync(path.join(state.root, "database/data/PG_VERSION")),
    false,
  );
  assert.equal(state.calls(), "");
});

test("init-dev refuses production, legacy database settings and unknown arguments before database access", (context) => {
  const state = fixture(context);
  assert.equal(
    state.run([], { APP_ENV: "production" }, "init-dev.sh").status,
    1,
  );
  assert.equal(
    state.run([], { OCOTE_DB_NAME: "legacy_database" }, "init-dev.sh").status,
    1,
  );
  assert.equal(state.run(["--unknown"], {}, "init-dev.sh").status, 1);
  assert.equal(state.calls(), "");
});
