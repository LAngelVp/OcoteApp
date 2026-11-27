const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const dependency = require('node:module').createRequire(require.resolve('@angular/cli/package.json'));
const { Architect } = dependency('@angular-devkit/architect');
const { WorkspaceNodeModulesArchitectHost } = dependency('@angular-devkit/architect/node');
const { workspaces, logging, schema } = dependency('@angular-devkit/core');
const { NodeJsSyncHost } = dependency('@angular-devkit/core/node');

async function main() {
  const { workspace } = await workspaces.readWorkspace('angular.json', workspaces.createWorkspaceHost(new NodeJsSyncHost()));
  const registry = new schema.CoreSchemaRegistry();
  registry.addPostTransform(schema.transforms.addUndefinedDefaults);
  const architect = new Architect(new WorkspaceNodeModulesArchitectHost(workspace, process.cwd()), registry);
  const logger = new logging.Logger('F7-delivery');
  logger.subscribe(entry => console.log(entry.message));
  const run = await architect.scheduleTarget({ project: 'ocoteApp', target: 'build', configuration: 'production' }, { watch: false, progress: false }, { logger });
  try {
    const result = await run.result;
    if (result.success !== true) throw Error('Production Architect result was not successful');
    const root = path.resolve('dist/ocote-app/browser');
    const files = {};
    function scan(directory) {
      for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
        const full = path.join(directory, entry.name);
        if (entry.isDirectory()) scan(full);
        else if (entry.isFile()) files[path.relative(root, full).replaceAll(path.sep, '/')] = crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex');
        else throw Error('Unsupported frontend output entry');
      }
    }
    scan(root);
    fs.writeFileSync('dist/ocote-app/architect-result.json', JSON.stringify({ success: true, configuration: 'production', project: 'ocoteApp', files }));
    console.log(JSON.stringify({ architect_success: true, files: Object.keys(files).length }));
  } finally { await run.stop(); }
}
main().then(() => process.exit(0), error => { console.error(error); process.exit(1); });