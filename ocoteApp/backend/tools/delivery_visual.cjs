const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const original = path.join(__dirname, 'f12_visual.cjs');
let source = fs.readFileSync(original, 'utf8');
const syntax = ts.createSourceFile(original, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
const replacements = [];
function visit(node) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'synthetic') {
    replacements.push({ start: node.getStart(syntax), end: node.end, text: `function synthetic(route,method) {
      if(route==='/setup/status') return setupScenario==='existing'
        ? {status:409,data:{code:'SETUP_DATABASE_NOT_EMPTY',request_id:'synthetic-f7-existing'}}
        : setupScenario==='pair' ? {status:403,data:{code:'SETUP_CAPABILITY_INVALID',request_id:'synthetic-f7-pair'}}
        : {status:200,data:{state:'prepared'}};
      if(route==='/setup/connection-tests') return setupScenario==='unavailable'
        ? {status:503,data:{code:'SETUP_CONNECTION_UNAVAILABLE',request_id:'synthetic-f7-unavailable'}}
        : {status:200,data:{test_id:'a'.repeat(32),expires_in:600,roles_verified:true}};
      if(route==='/setup/pair') return {status:200,data:{session_code:'synthetic-session'}};
      throw Error('Unexpected setup API '+method+' '+route);
    }` });
  }
  if (ts.isForOfStatement(node) && node.expression.getText(syntax) === '[1280, 360]') {
    replacements.push({ start: node.getStart(syntax), end: node.end, text: `
      const fill=async(name,value)=>evaluate('(()=>{const field=document.querySelector('+JSON.stringify('[formcontrolname="'+name+'"]')+');if(!field)throw Error("Missing field");field.value='+JSON.stringify(value)+';field.dispatchEvent(new Event("input",{bubbles:true}));})()');
      for(const width of [1280,360]) {
        await page('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
        setupScenario='pair'; await navigate('/instalacion','document.body.innerText.includes("Emparejar equipo")');
        await inspect('setup-pair-'+width);
        await fill('code','synthetic-capability'); setupScenario='local';
        await click(button('Emparejar'));await wait('document.querySelector(".mat-step-header[aria-current=step]")?.innerText.includes("PostgreSQL")');
        await inspect('setup-local-'+width);
        await evaluate('window.scrollTo(0,document.documentElement.scrollHeight)');await inspect('setup-local-bottom-'+width);await evaluate('window.scrollTo(0,0)');
        await fill('runtime_password','synthetic-runtime');await fill('migrator_password','synthetic-migrator');
        setupScenario='unavailable';await click(button('Probar conexion y permisos'));
        await wait('document.body.innerText.includes("synthetic-f7-unavailable")');
        await evaluate('[...document.querySelectorAll("input[type=password]")].forEach(field=>field.value="")');
        await inspect('setup-unavailable-'+width);
        setupScenario='local';await click(button('Probar conexion y permisos'));
        await wait('document.querySelector(".mat-step-header[aria-current=step]")?.innerText.includes("Primer administrador")');
        await inspect('setup-admin-'+width);
        await fill('display_name','Operador sintetico');await fill('email','synthetic@example.invalid');
        await fill('password','Synthetic-password-2026!');await fill('confirmation','Synthetic-password-2026!');
        await fill('timezone','America/Mexico_City');await fill('reason','Instalacion sintetica aislada F7');
        await click(button('Revisar instalacion'));
        await wait('document.querySelector(".mat-step-header[aria-current=step]")?.innerText.includes("Confirmar y sellar")');
        await evaluate('[...document.querySelectorAll("input[type=password]")].forEach(field=>field.value="")');
        await inspect('setup-review-'+width);
        setupScenario='pair';await navigate('/instalacion?synthetic=external','document.body.innerText.includes("Emparejar equipo")');
        await fill('code','synthetic-capability');setupScenario='local';await click(button('Emparejar'));
        await wait('document.querySelector(".mat-step-header[aria-current=step]")?.innerText.includes("PostgreSQL")');
        await click('document.querySelector("mat-select")');await wait('document.querySelector("mat-option")');
        await click('[...document.querySelectorAll("mat-option")].find(option=>option.innerText.includes("Externo"))');
        await wait('document.body.innerText.includes("TLS verify-full")');await inspect('setup-managed-'+width);
        await evaluate('window.scrollTo(0,document.documentElement.scrollHeight)');await inspect('setup-managed-bottom-'+width);await evaluate('window.scrollTo(0,0)');
        setupScenario='existing';await navigate('/instalacion?synthetic=existing','document.body.innerText.includes("Instalacion no disponible")');
        await inspect('setup-existing-'+width);
      }` });
  }
  ts.forEachChild(node, visit);
}
visit(syntax);
if (replacements.length !== 2) throw Error('Protected visual driver shape changed');
for (const replacement of replacements.sort((first, second) => second.start - first.start)) {
  source = source.slice(0, replacement.start) + replacement.text + source.slice(replacement.end);
}
source = 'let setupScenario="pair";\n' + source.replaceAll('ocote-f12-', 'ocote-f7-delivery-');
new Function('require', '__dirname', '__filename', source)(require, __dirname, __filename);