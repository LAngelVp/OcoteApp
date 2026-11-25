import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal, Type } from '@angular/core';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { MAT_DIALOG_DATA, MatDialog, MatDialogRef } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { Api, Row } from './core/api';
import { Role, Session, User } from './core/session';
import { routes } from './app.routes';
import { Shell } from './shell';
import { TasksPage } from './operations/tasks.page';
import { TaskDetailPage } from './operations/task-detail.page';
import { RequestsPage } from './operations/requests.page';
import { PlanningPage } from './operations/planning.page';
import { AdminPage } from './admin/admin.page';
import { stageProblem, transitionProblem, workflowProblem, WorkflowEditor } from './admin/workflow.editor';
import { EditData, Editor } from './shared/editor';
import { RouterTestingHarness } from '@angular/router/testing';
import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { civilDate, ExecutionPage } from './operations/execution.page';
import { Evidence } from './operations/evidence';
import { Transition } from './operations/transition';

const permissions: Record<Role,string[]> = {
  admin:['administration:manage','planning:manage','tasks:manage','tasks:transition','dates:decide','date-requests:create'],
  gerente:['planning:manage','dates:decide','date-requests:create'],
  lider:['planning:department','tasks:manage','tasks:transition','date-requests:create'],
  colaborador:['tasks:transition'],
};
const syntheticTask: Row = { id:'synthetic-task',version:7,objective_id:'synthetic-objective',title:'Synthetic task',description:'Synthetic',assignee_id:'synthetic-user',stage_id:'synthetic-open',priority_id:'synthetic-priority',start_date:'2027-11-15',original_due_date:'2027-12-01',due_date:'2028-01-01',progress_percent:100,pending_closure:true,baseline_punctuality_status:'late',punctuality_status:'on_time',annual_plan:{ id:'synthetic-plan',title:'Synthetic plan' },objective:{ id:'synthetic-objective',title:'Synthetic objective' },priority:{ id:'synthetic-priority',name:'Synthetic priority' } };
const syntheticRequest: Row = { id:'synthetic-request',task_id:'synthetic-task',requested_by:'synthetic-user',status:'pending',task_version_at_request:7,version:2,previous_due_date:'2028-01-01',proposed_due_date:'2028-01-05' };

class BrowserApi {
  reads: string[] = [];
  writes: { path:string;body:Row;method:string }[] = [];
  response: (path:string) => unknown = path => {
    if (path === '/catalogs/workflow') return { stages:[{ id:'synthetic-open',name:'Abierta',kind:'open' }],transitions:[] };
    if (path === '/tasks/synthetic-task') return syntheticTask;
    if (path === '/due-date-requests/synthetic-request') return syntheticRequest;
    if (path === '/configuration-status') return { complete:false,missing_settings:[],missing_horizons:[],normal_present:false,workflow_valid:false };
    if (path === '/kanban') return { columns:[] };
    if (path === '/timeline') return { items:[],next_cursor:null,organization_timezone:'America/Mexico_City' };
    if (path.endsWith('/evidence')) return { items:[],next_cursor:null,upload_limit_bytes:1024,uploads_configured:true };
    if (path === '/annual-plans/synthetic-plan') return { id:'synthetic-plan',version:1,title:'Synthetic plan',progress_percent:null,status:'draft',start_date:'2027-11-15',due_date:'2028-02-20' };
    return { items:[],next_cursor:null };
  };
  async get<T = Row>(path:string): Promise<T> { this.reads.push(path); return this.response(path) as T; }
  async all(path:string): Promise<Row[]> { this.reads.push(path); return (this.response(path) as { items?:Row[] }).items ?? []; }
  async command(path:string,body:Row,method = 'POST'): Promise<Row> { this.writes.push({ path,body,method }); return {}; }
}

describe('F4 views, least privilege and command contracts (browser-only synthetic data)', () => {
  let api: BrowserApi;
  let account: ReturnType<typeof signal<User | null>>;
  const setup = async <T>(component: Type<T>, role:Role = 'admin', params:Row = {}, data:Row = {}): Promise<ComponentFixture<T>> => {
    api = new BrowserApi();
    account = signal<User | null>({ id:'synthetic-user',display_name:'Synthetic',email:'synthetic@example.test',role,department_id:'synthetic-department',permissions:permissions[role] });
    const session = { user:account,has:(permission:string) => account()?.permissions.includes(permission) ?? false,restore:async () => {},ready:signal(true) };
    await TestBed.configureTestingModule({ imports:[component],providers:[provideRouter(routes),provideNoopAnimations(),{ provide:Api,useValue:api },{ provide:Session,useValue:session },
      { provide:ActivatedRoute,useValue:{ paramMap:of(convertToParamMap(params as Record<string,string>)),snapshot:{ data,queryParamMap:convertToParamMap({}) } } },
      { provide:MAT_DIALOG_DATA,useValue:{ stages:[],transitions:[] } },{ provide:MatDialogRef,useValue:{ close:() => {},disableClose:false } },
    ] }).compileComponents();
    const fixture = TestBed.createComponent(component);
    if (component === Evidence) fixture.componentRef.setInput('task',syntheticTask);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges(); return fixture;
  };
  const dialogData = <T>(fixture: ComponentFixture<T>): { data:() => EditData } => {
    const open = spyOn(fixture.debugElement.injector.get(MatDialog),'open').and.returnValue({ afterClosed:() => of(false) } as MatDialogRef<unknown>);
    return { data:() => open.calls.mostRecent().args[1]!.data as EditData };
  };
  for (const role of ['admin','gerente','lider','colaborador'] as Role[]) {
    it('renders only the permitted navigation for ' + role, async () => {
      const fixture = await setup(Shell,role); const element = fixture.nativeElement as HTMLElement;
      expect(!!element.querySelector('a[href="/administracion/usuarios"]')).toBe(role === 'admin');
      expect(!!element.querySelector('a[href="/planes"]')).toBe(role !== 'colaborador');
      expect(!!element.querySelector('a[href="/solicitudes-fecha"]')).toBe(role !== 'colaborador');
      for (const path of ['/kanban','/timeline']) expect(element.querySelector('a[href="' + path + '"]')).not.toBeNull();
      for (const path of ['/analitica','/evaluaciones']) expect(element.querySelector('a[href="' + path + '"]')).toBeNull();
      expect(api.writes).toEqual([]);
    });
    it('renders only permitted task commands for ' + role, async () => {
      const fixture = await setup(TaskDetailPage,role,{ id:'synthetic-task' });
      const content = fixture.nativeElement.textContent as string;
      expect(content.includes('Reasignar')).toBe(role === 'admin' || role === 'lider');
      expect(content.includes('Cambiar etapa')).toBe(role !== 'gerente');
      expect(content.includes('Cambiar compromiso')).toBe(role === 'admin' || role === 'gerente');
      expect(content.includes('Solicitar fecha')).toBe(role !== 'colaborador');
      expect(content).toContain('Pendiente de cierre'); expect(content).toContain('Compromiso original');
    });
  }
  it('does not fetch planning modules or other users for collaborator filters', async () => {
    const fixture = await setup(TasksPage,'colaborador');
    expect(api.reads).not.toContain('/annual-plans'); expect(api.reads).not.toContain('/objectives'); expect(api.reads).not.toContain('/users');
    expect(fixture.nativeElement.textContent).toContain('Mis tareas'); expect(api.writes).toEqual([]);
  });
  it('keeps an empty admin installation empty and reports incomplete configuration', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'configuracion' });
    expect(fixture.nativeElement.textContent).toContain('Configuracion incompleta'); expect(api.writes).toEqual([]);
  });
  for (const [code,message] of [['WORKFLOW_INCOMPLETE','El grafo requiere una etapa inicial abierta y una terminal activa.'],['WORKFLOW_HAS_NO_TERMINAL_PATH','Todas las etapas activas necesitan un camino hacia la terminal.']]) {
    it('explains the exact workflow blocker without creating configuration for ' + code, async () => {
      const fixture = await setup(AdminPage,'admin',{ section:'configuracion' });
      api.response = () => ({ complete:false,missing_settings:[],missing_horizons:[],normal_present:true,workflow_valid:false,workflow_error:code });
      await fixture.componentInstance.load(); fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain(message);
      expect(fixture.nativeElement.querySelector('a[href="/administracion/transiciones"]')).not.toBeNull();
      expect(api.writes).toEqual([]);
      api.response = () => ({ complete:true,missing_settings:[],missing_horizons:[],normal_present:true,workflow_valid:true,workflow_error:null });
      await fixture.componentInstance.load(); fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('Configuracion completa');
      expect(fixture.nativeElement.textContent).not.toContain(message); expect(api.writes).toEqual([]);
    });
  }
  it('renders nested admin rows with stable UUID or setting keys after reload', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'parametros' });
    api.response = () => ({ items:[{ key:'organization_name',value:'Synthetic organization',version:1 },{ key:'evidence_max_bytes',value:1024,version:2 }] });
    await fixture.componentInstance.load(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('tbody tr').length).toBe(2);
    const first = fixture.nativeElement.querySelector('tbody tr');
    await fixture.componentInstance.load(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('tbody tr')).toBe(first);
    expect(fixture.componentInstance.rowKey({ id:'synthetic-id' })).toBe('synthetic-id');
    expect(fixture.componentInstance.rowKey({ key:'organization_name' })).toBe('organization_name');
    expect(api.writes).toEqual([]);
  });
  it('clears a created setting selection after reload without defaulting to another key', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'parametros' });
    fixture.componentInstance.settingKey = 'organization_name';
    api.response = () => ({ items:[{ key:'organization_name',value:'Synthetic organization',version:1 }] });
    await fixture.componentInstance.load(); fixture.detectChanges();
    expect(fixture.componentInstance.settingKey).toBe('');
    expect(fixture.componentInstance.availableKeys()).not.toContain('organization_name');
    const create = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(button => button.textContent?.includes('Crear'));
    expect(create?.disabled).toBeTrue(); expect(api.writes).toEqual([]);
  });
  it('starts an atomic workflow with no invented stages, transitions or roles', async () => {
    const fixture = await setup(WorkflowEditor); expect(fixture.componentInstance.stages.length).toBe(0); expect(fixture.componentInstance.transitions.length).toBe(0);
    fixture.componentInstance.addStage(); expect(fixture.componentInstance.stages.at(0).get('code')?.value).toBe('');
    expect(fixture.componentInstance.stages.at(0).get('kind')?.value).toBe(''); expect(api.writes).toEqual([]);
  });
  for (const stages of [[],[{ id:'open',kind:'open',is_initial:true,is_active:true }]]) it('creates only a stage without transition fields or complete graph validation, existing count ' + stages.length, async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'etapas' });
    api.response = path => ({ items:path === '/workflow-stages' ? stages : [] });
    const open = spyOn(fixture.debugElement.injector.get(MatDialog),'open').and.returnValue({ afterClosed:() => of(false) } as MatDialogRef<unknown>);
    await fixture.componentInstance.edit();
    expect(open.calls.mostRecent().args[0]).toBe(Editor);
    const data = open.calls.mostRecent().args[1]?.data as EditData;
    expect(data.fields.map(field => field.key)).toEqual(['code','name','position','is_active','kind','is_initial','requires_reason','requires_evidence','reason']);
    expect(api.reads).not.toContain('/workflow-transitions'); expect(api.writes).toEqual([]);
    const values = { code:'open',name:'Open',position:0,kind:'open',is_initial:true,is_active:true,requires_reason:false,requires_evidence:false,reason:'Explicit initial creation' };
    expect(data.validate?.(values)).toBeNull(); await data.submit(values);
    expect(api.writes).toEqual([{ path:'/workflow-stages',method:'POST',body:values }]);
    expect(fixture.nativeElement.textContent).not.toContain('Editar grafo');
    await fixture.componentInstance.workflow(); expect(open).toHaveBeenCalledTimes(1);
  });
  it('queries current admin detail and preserves request references when it is unavailable', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'departamentos' });
    api.response = () => ({ id:'department',name:'Current',version:3 });
    await fixture.componentInstance.inspect({ id:'department',name:'Old',version:1 });
    expect(api.reads).toContain('/departments/department'); expect(fixture.componentInstance.selected()?.['version']).toBe(3);
    spyOn(api,'get').and.rejectWith(new HttpErrorResponse({ status:404,error:{ code:'RESOURCE_NOT_FOUND',request_id:'missing-detail' } }));
    await fixture.componentInstance.inspect({ id:'missing' });
    expect(fixture.componentInstance.selected()).toBeNull(); expect(fixture.componentInstance.issue()?.requestId).toBe('missing-detail');
  });
  for (const [section,row,expected] of [
    ['departamentos',{ id:'department',name:'Current department',code:'department',is_active:true,version:3 },'Current department'],
    ['usuarios',{ id:'user',display_name:'Current user',role:'lider',department_id:null,is_active:false },'L\u00edder'],
    ['etapas',{ id:'stage',name:'Initial stage',kind:'open',is_initial:true,is_active:true,requires_evidence:false },'Inicial'],
    ['transiciones',{ id:'edge',from_stage_id:'open',to_stage_id:'done',allowed_roles:['admin','lider'],is_active:true },'Roles permitidos'],
    ['prioridades',{ id:'priority',name:'Normal',position:0,is_active:true },'Posici\u00f3n'],
    ['horizontes',{ id:'horizon',name:'Annual',code:'annual',position:0,is_active:true },'Annual'],
    ['parametros',{ key:'organization_timezone',value:'America/Mexico_City',version:3 },'Zona horaria'],
    ['auditoria',{ id:'audit',event_type:'administration_changed',before_data:{ is_active:false },after_data:{ is_active:true } },'Estado anterior'],
    ['releases',{ id:'release',application_version:'1.0',status:'succeeded',result_code:'VERIFIED' },'Correcta'],
  ] as [string,Row,string][]) {
    it('opens and closes readable read-only details repeatedly for ' + section, async () => {
      const fixture = await setup(AdminPage,'admin',{ section });
      api.response = () => row;
      for (let attempt = 0; attempt < 2; attempt++) {
        await fixture.componentInstance.inspect(row); fixture.detectChanges();
        const panel = fixture.nativeElement.querySelector('[aria-labelledby="record-detail-title"]') as HTMLElement;
        expect(panel).not.toBeNull(); expect(panel.textContent).toContain(expected);
        expect(panel.querySelector('ocote-record-details')).not.toBeNull(); expect(panel.querySelector('pre')).toBeNull();
        expect(panel.textContent).not.toContain('[object Object]');
        (panel.querySelector('[aria-label="Cerrar detalle"]') as HTMLButtonElement).click(); fixture.detectChanges();
        expect(fixture.componentInstance.selected()).toBeNull(); expect(fixture.nativeElement.querySelector('ocote-record-details')).toBeNull();
      }
      expect(api.writes).toEqual([]);
    });
  }
  it('renders task history snapshots as structured readonly information with no JSON blocks', async () => {
    const fixture = await setup(TaskDetailPage,'admin',{ id:'synthetic-task' });
    const original = api.response;
    api.response = path => path.endsWith('/history') ? { items:[{ id:'event',event_type:'task_updated',created_at:'2026-11-25T02:00:00Z',reason:'Current reason',before_data:{ title:'Previous title',due_date:'2028-02-28' },after_data:{ title:'Updated title',due_date:'2028-02-29',priority:{ name:'Normal' } } }],next_cursor:null } : original(path);
    await fixture.componentInstance.loadHistory(); fixture.detectChanges();
    const details = fixture.nativeElement.querySelector('details') as HTMLDetailsElement;
    (details.querySelector('summary') as HTMLElement).click(); fixture.detectChanges(); expect(details.open).toBeTrue();
    expect(details.querySelectorAll('ocote-record-details').length).toBe(2); expect(details.querySelector('pre')).toBeNull();
    expect(details.textContent).toContain('Previous title'); expect(details.textContent).toContain('Updated title');
    expect(details.textContent).toContain('29 de febrero de 2028'); expect(details.textContent).not.toContain('[object Object]');
    (details.querySelector('summary') as HTMLElement).click(); expect(details.open).toBeFalse(); expect(api.writes).toEqual([]);
  });
  for (const [section,row,body] of [
    ['departamentos',{ id:'department',name:'Department',is_active:true,version:2 },{ name:'Department' }],
    ['usuarios',{ id:'user',display_name:'User',role:'lider',department_id:'department',is_active:true,version:2 },{ display_name:'User',role:'lider',department_id:'department' }],
    ['prioridades',{ id:'priority',code:'urgent',name:'Priority',position:1,is_active:true,version:2 },{ name:'Priority',position:1 }],
    ['horizontes',{ id:'horizon',code:'annual',name:'Annual',position:1,is_active:true,version:2 },{ name:'Annual',position:1 }],
    ['etapas',{ id:'stage',code:'blocked',name:'Blocked',position:1,kind:'blocked',requires_reason:true,requires_evidence:false,is_active:true,version:2 },{ name:'Blocked',position:1,requires_reason:true,requires_evidence:false }],
    ['transiciones',{ id:'edge',allowed_roles:['admin'],is_active:true,version:2 },{ allowed_roles:['admin'] }],
  ] as [string,Row,Row][]) {
    it('uses a confirmed versioned non-destructive command for ' + section, async () => {
      const fixture = await setup(AdminPage,'admin',{ section }), dialog = dialogData(fixture);
      fixture.componentInstance.changeActivity(row);
      expect(api.writes).toEqual([]); expect(dialog.data().fields.map(field => field.key)).toEqual(['reason']);
      expect(dialog.data().message).toContain('historial');
      await dialog.data().submit({ reason:'Current deactivation reason' });
      expect(api.writes[0].method).toBe('PATCH'); expect(api.writes[0].body).toEqual({ ...body,is_active:false,expected_version:2,reason:'Current deactivation reason' });
      expect(api.writes[0].body['code']).toBeUndefined();
    });
  }
  for (const [section,row] of [['prioridades',{ code:'normal' }],['horizontes',{ code:'custom' }],['etapas',{ is_initial:true }],['etapas',{ kind:'completed' }]] as [string,Row][]) {
    it('does not expose deactivation of a protected entry in ' + section + JSON.stringify(row), async () => {
      const fixture = await setup(AdminPage,'admin',{ section });
      expect(fixture.componentInstance.canChangeActivity({ ...row,is_active:true })).toBeFalse(); expect(api.writes).toEqual([]);
    });
  }
  for (const [key,type,value] of [['organization_name','text','Synthetic organization'],['organization_timezone','text','America/Mexico_City'],['evidence_max_bytes','number',1024],['export_max_rows','number',50]] as const) {
    it('opens a typed empty setting and edits its current value for ' + key, async () => {
      const fixture = await setup(AdminPage,'admin',{ section:'parametros' }), dialog = dialogData(fixture);
      fixture.componentInstance.settingKey = key; await fixture.componentInstance.edit();
      expect(dialog.data().fields[0].type).toBe(type); expect(dialog.data().fields[0].value).toBeUndefined();
      await dialog.data().submit({ value,reason:'Synthetic explicit configuration' });
      expect(api.writes[0].body).toEqual({ key,value,reason:'Synthetic explicit configuration' });
      await fixture.componentInstance.edit({ key,value,version:4 });
      expect(dialog.data().fields[0].value).toBe(value);
      await dialog.data().submit({ value,reason:'Synthetic explicit update' });
      expect(api.writes[1]).toEqual({ path:'/settings/' + key,method:'PATCH',body:{ value,reason:'Synthetic explicit update',expected_version:4 } });
      if (key === 'organization_timezone') {
        expect(dialog.data().validate?.({ value:'Not/AZone' })).toContain('IANA');
        expect(dialog.data().validate?.({ value })).toBeNull();
      }
    });
  }
  for (const section of ['departamentos','usuarios','etapas','prioridades','horizontes','transiciones','parametros']) {
    it('reopens a complete independent Material dialog after cancel/save/conflict for ' + section, async () => {
      const fixture = await setup(AdminPage,'admin',{ section }), page = fixture.componentInstance, dialog = TestBed.inject(MatDialog);
      page.settingKey = 'organization_name';
      api.response = path => ({ items:path === '/workflow-stages' ? [{ id:'open',name:'Open',kind:'open',is_active:true },{ id:'done',name:'Done',kind:'completed',is_active:true }] : [] });
      const values = { code:section === 'horizontes' ? 'annual' : 'synthetic',name:'Synthetic',position:0,is_active:true,display_name:'Synthetic',email:'synthetic@example.test',password:'Synthetic-password-123',role:'admin',department_id:null,from_stage_id:'open',to_stage_id:'done',allowed_roles:['admin'],kind:'open',is_initial:false,requires_reason:false,requires_evidence:false,value:'Synthetic organization',reason:'Synthetic explicit change' };
      const open = async () => {
        await page.edit(); fixture.detectChanges(); await fixture.whenStable();
        const ref = dialog.openDialogs[0] as MatDialogRef<Editor>, editor = ref.componentInstance;
        expect(document.querySelectorAll('mat-dialog-content mat-form-field').length).toBe(editor.data.fields.filter(field => field.type !== 'check').length);
        expect(editor.data.fields.length).toBeGreaterThan(1); expect(editor.issue()).toBeNull(); expect(editor.busy()).toBeFalse();
        return ref;
      };
      const cancelled = await open(), firstEditor = cancelled.componentInstance, originalFields = firstEditor.data.fields.map(field => field.key);
      cancelled.componentInstance.form.controls['reason'].setValue('Cancelled synthetic values'); cancelled.close(false);
      fixture.detectChanges(); await fixture.whenStable();
      const saved = await open(); expect(saved.componentInstance).not.toBe(firstEditor);
      expect(saved.componentInstance.form.controls['reason'].value).toBeNull();
      expect(saved.componentInstance.data.fields.map(field => field.key)).toEqual(originalFields);
      saved.componentInstance.form.patchValue(values); expect(saved.componentInstance.form.valid).toBeTrue();
      await saved.componentInstance.save(); fixture.detectChanges(); await fixture.whenStable();
      expect(api.writes.length).toBe(1);
      const conflicted = await open();
      conflicted.componentInstance.form.patchValue(values); expect(conflicted.componentInstance.form.valid).toBeTrue();
      spyOn(api,'command').and.rejectWith(new HttpErrorResponse({ status:409,error:{ code:'VERSION_CONFLICT' } }));
      await conflicted.componentInstance.save(); fixture.detectChanges();
      expect(conflicted.componentInstance.issue()?.conflict).toBeTrue();
      expect(document.querySelectorAll('mat-dialog-content mat-form-field').length).toBeGreaterThan(0);
      conflicted.close('reload'); fixture.detectChanges(); await fixture.whenStable();
      const fresh = await open(); expect(fresh.componentInstance.data.fields.map(field => field.key)).toEqual(originalFields);
      fresh.close(false); fixture.detectChanges(); await fixture.whenStable();
    });
  }
  for (const [section,code] of [['prioridades','normal'],['horizontes','custom']]) {
    it('requires the protected code active without inserting or selecting it by default in ' + section, async () => {
      const fixture = await setup(AdminPage,'admin',{ section }), dialog = dialogData(fixture);
      await fixture.componentInstance.edit();
      expect(dialog.data().fields.find(field => field.key === 'code')?.value).toBeUndefined();
      expect(dialog.data().validate?.({ code,is_active:false })).toContain('activ');
      expect(dialog.data().validate?.({ code,is_active:true })).toBeNull();
      await fixture.componentInstance.edit({ id:'protected',code,name:'Current',position:0,is_active:true,version:3,reason:'Old reason' });
      expect(dialog.data().fields.find(field => field.key === 'reason')?.value).toBeUndefined();
      expect(dialog.data().validate?.({ is_active:false })).toContain('activ');
      expect(api.writes).toEqual([]);
    });
    it('does not open a misleading reorder command for an empty ' + section, async () => {
      const fixture = await setup(AdminPage,'admin',{ section });
      const open = spyOn(fixture.debugElement.injector.get(MatDialog),'open');
      await fixture.componentInstance.reorder(); expect(open).not.toHaveBeenCalled(); expect(api.writes).toEqual([]);
      const button = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(button => button.textContent?.includes('Ordenar'));
      expect(button?.disabled).toBeTrue();
    });
  }
  it('requires the user department by role and preserves the exact password including surrounding spaces', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'usuarios' }), dialog = TestBed.inject(MatDialog);
    await fixture.componentInstance.edit(); fixture.detectChanges(); await fixture.whenStable();
    const editor = dialog.openDialogs[0].componentInstance as Editor;
    const password = '  Synthetic secret 123!  ';
    editor.form.patchValue({ email:'  SYNTHETIC@example.invalid  ',display_name:'  Synthetic user  ',password,role:'lider',department_id:null,is_active:true,reason:'  Current user creation  ' });
    expect(editor.form.controls['department_id'].invalid).toBeTrue(); expect(editor.form.invalid).toBeTrue();
    editor.form.controls['role'].setValue('admin'); expect(editor.form.valid).toBeTrue();
    await editor.save(); fixture.detectChanges(); await fixture.whenStable();
    expect(api.writes[0].body['password']).toBe(password);
    expect(api.writes[0].body['email']).toBe('SYNTHETIC@example.invalid'); expect(api.writes[0].body['reason']).toBe('Current user creation');
    expect(api.writes[0].body['display_name']).toBe('Synthetic user');
    const captured = dialogData(fixture);
    await fixture.componentInstance.edit({ id:'user',display_name:'Current',email:'synthetic@example.invalid',role:'admin',department_id:null,is_active:true,version:3,reason:'Old creation' });
    expect(captured.data().fields.some(field => field.type === 'password')).toBeFalse();
    expect(captured.data().fields.find(field => field.key === 'reason')?.value).toBeUndefined();
    fixture.componentInstance.resetPassword({ id:'user',display_name:'Current',version:3 });
    expect(captured.data().fields.find(field => field.key === 'new_password')?.type).toBe('password');
    expect(captured.data().fields.find(field => field.key === 'new_password')?.value).toBeUndefined();
  });
  it('validates stage semantics and transition rules before calling the API', () => {
    const stages = [{ id:'open',code:'open',name:'Open',position:0,kind:'open',is_initial:true,is_active:true },{ id:'done',code:'done',name:'Done',position:1,kind:'completed',is_active:true }];
    expect(stageProblem({ ...stages[0],requires_evidence:true })).not.toBeNull();
    expect(stageProblem({ ...stages[0],requires_reason:true })).not.toBeNull();
    expect(stageProblem({ ...stages[0],kind:'blocked' })).not.toBeNull();
    expect(stageProblem({ ...stages[1],is_active:false })).not.toBeNull();
    const edge = { from_stage_id:'open',to_stage_id:'done',allowed_roles:['admin'],is_active:true };
    expect(transitionProblem(edge,stages)).toBeNull();
    for (const invalid of [{ to_stage_id:'open' },{ from_stage_id:'done',to_stage_id:'open' },{ allowed_roles:['lider'] },{ allowed_roles:['admin','admin'] },{ allowed_roles:['gerente'] }]) expect(transitionProblem({ ...edge,...invalid },stages)).not.toBeNull();
    expect(transitionProblem(edge,[stages[0],{ ...stages[1],is_active:false }])).not.toBeNull();
    const transition = { from_code:'open',to_code:'done',allowed_roles:['admin'],is_active:true };
    expect(workflowProblem(stages,[transition])).toBeNull();
    expect(workflowProblem(stages,[transition,transition])).toContain('duplicadas');
    expect(workflowProblem([stages[0],{ ...stages[1],position:0 }],[transition])).toContain('posiciones');
    expect(workflowProblem([...stages,{ code:'blocked',position:2,kind:'blocked',is_active:true }],[transition])).toContain('camino');
    expect(workflowProblem(stages,[{ ...transition,is_active:false }])).toContain('camino');
  });
  it('saves an actual first initial stage form without requiring a terminal or transition', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'etapas' });
    await fixture.componentInstance.edit(); fixture.detectChanges(); await fixture.whenStable();
    const editor = TestBed.inject(MatDialog).openDialogs[0].componentInstance as Editor;
    editor.form.patchValue({ code:'first',name:'Initial',position:0,kind:'open',is_initial:true,is_active:true,requires_evidence:false,requires_reason:false,reason:'Explicit initial creation' });
    expect(editor.form.valid).toBeTrue();
    for (const field of ['requires_evidence','requires_reason']) {
      editor.form.controls[field].setValue(true); expect(editor.form.invalid).toBeTrue();
      editor.form.controls[field].setValue(false); expect(editor.form.valid).toBeTrue();
    }
    expect(document.querySelector('mat-dialog-content')?.textContent).not.toContain('Transiciones');
    await editor.save(); fixture.detectChanges(); await fixture.whenStable();
    expect(api.writes.length).toBe(1); expect(api.writes[0].path).toBe('/workflow-stages');
    expect(api.writes[0].body['is_initial']).toBeTrue(); expect(api.writes[0].body['transitions']).toBeUndefined();
  });
  it('opens only transition fields and reads existing stages rather than creating stage rows', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'transiciones' }), dialog = dialogData(fixture);
    await fixture.componentInstance.edit();
    expect(dialog.data().fields.map(field => field.key)).toEqual(['from_stage_id','to_stage_id','allowed_roles','is_active','reason']);
    expect(api.reads).toContain('/workflow-stages'); expect(api.writes).toEqual([]);
    expect(fixture.nativeElement.textContent).not.toContain('Editar grafo');
  });
  for (const section of ['etapas','prioridades','horizontes']) {
    it('uses a visible integer input with exact PostgreSQL boundaries in ' + section, async () => {
      const fixture = await setup(AdminPage,'admin',{ section }), dialog = TestBed.inject(MatDialog);
      await fixture.componentInstance.edit(); fixture.detectChanges(); await fixture.whenStable();
      const editor = dialog.openDialogs[0].componentInstance as Editor;
      const field = editor.form.controls['position'];
      const input = document.querySelector('mat-dialog-content input[type="number"]') as HTMLInputElement;
      expect(input).not.toBeNull(); expect(input.min).toBe('0'); expect(input.max).toBe('2147483647'); expect(input.step).toBe('1');
      for (const invalid of [-1,1.5,2147483648,'1,000','']) { field.setValue(invalid); expect(field.invalid).withContext(String(invalid)).toBeTrue(); }
      for (const valid of [0,2147483647]) { field.setValue(valid); expect(field.valid).toBeTrue(); }
      if (section === 'horizontes') expect(editor.data.fields.find(item => item.key === 'code')?.options?.map(option => option.value)).toEqual(['annual','semiannual','quarterly','monthly','custom']);
      dialog.openDialogs[0].close(false); fixture.detectChanges(); await fixture.whenStable();
    });
  }
  for (const [key,type,maximum,value] of [['organization_name','text',160,'Synthetic'],['organization_timezone','text',100,'America/Mexico_City'],['evidence_max_bytes','number',10485760,1024],['export_max_rows','number',10000,100]] as const) {
    it('renders the exact required input and limits for ' + key, async () => {
      const fixture = await setup(AdminPage,'admin',{ section:'parametros' }), dialog = TestBed.inject(MatDialog);
      fixture.componentInstance.settingKey = key; await fixture.componentInstance.edit(); fixture.detectChanges(); await fixture.whenStable();
      const editor = dialog.openDialogs[0].componentInstance as Editor, control = editor.form.controls['value'];
      const input = document.querySelector('mat-dialog-content input') as HTMLInputElement;
      expect(input.type).toBe(type); expect(editor.data.fields[0].key).toBe('value'); expect(input.required).toBeTrue();
      input.value = String(value); input.dispatchEvent(new Event('input')); fixture.detectChanges(); expect(control.value).toBe(value);
      control.setValue(''); expect(control.invalid).toBeTrue();
      control.setValue(type === 'number' ? maximum + 1 : 'x'.repeat(maximum + 1)); expect(control.invalid).toBeTrue();
      if (type === 'number') { for (const invalid of [0,-1,1.5]) { control.setValue(invalid); expect(control.invalid).toBeTrue(); } control.setValue(maximum); expect(control.valid).toBeTrue(); }
      control.setValue(value); editor.form.controls['reason'].setValue('Current typed configuration'); expect(editor.form.valid).toBeTrue();
      expect(api.writes).toEqual([]); dialog.openDialogs[0].close(false); fixture.detectChanges(); await fixture.whenStable();
    });
  }
  it('submits a complete graph with integer positions and preserves immutable fields/versions', async () => {
    const fixture = await setup(WorkflowEditor), editor = fixture.componentInstance;
    editor.addStage({ code:'open',name:'Open',position:'0',kind:'open',is_initial:true,is_active:true,version:4 });
    editor.addStage({ code:'done',name:'Done',position:'1',kind:'completed',is_active:true,version:2 });
    editor.addTransition({ from_code:'open',to_code:'done',allowed_roles:['admin'],is_active:true,version:3 });
    editor.form.controls.reason.setValue('Synthetic explicit graph change');
    fixture.detectChanges(); expect(editor.form.valid).toBeTrue();
    expect(editor.stages.at(0).get('code')?.disabled).toBeTrue(); expect(editor.stages.at(0).get('kind')?.disabled).toBeTrue();
    editor.stages.at(0).get('position')?.setValue(' 2 '); await editor.save();
    expect(api.writes[0].path).toBe('/workflow');
    const stages = api.writes[0].body['stages'] as Row[], transitions = api.writes[0].body['transitions'] as Row[];
    expect(stages[0]['position']).toBe(2); expect(stages[0]['expected_version']).toBe(4); expect(stages[0]['is_initial']).toBeTrue();
    expect(transitions[0]['expected_version']).toBe(3);
  });
  it('validates graph text, fresh reason and PostgreSQL integer limits without implicit selections', async () => {
    const fixture = await setup(WorkflowEditor), editor = fixture.componentInstance;
    editor.addStage({ code:' open ',name:'   ',position:2147483648,kind:'open',is_initial:true,is_active:true });
    editor.addStage({ code:'done',name:'Done',position:1,kind:'completed',is_active:true });
    editor.addTransition({ from_code:'open',to_code:'done',allowed_roles:['admin'],is_active:true });
    editor.form.controls.reason.setValue('           '); expect(editor.form.invalid).toBeTrue();
    editor.stages.at(0).patchValue({ name:' Open ',position:0 }); editor.form.controls.reason.setValue('  Initial graph justification  ');
    expect(editor.form.valid).toBeTrue(); await editor.save();
    const body = api.writes[0].body; expect(body['reason']).toBe('Initial graph justification');
    expect((body['stages'] as Row[])[0]['code']).toBe('open');
    expect((body['stages'] as Row[])[0]['name']).toBe('Open');
  });
  it('reopens the graph from current data without cancelled rows, old errors or busy state', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'configuracion' }), dialog = TestBed.inject(MatDialog);
    api.response = path => ({ items:path === '/workflow-stages' ? [
      { id:'open',code:'open',name:'Open',position:0,kind:'open',is_initial:true,is_active:true,version:4 },
      { id:'done',code:'done',name:'Done',position:1,kind:'completed',is_active:true,version:2 },
    ] : path === '/workflow-transitions' ? [{ from_stage_id:'open',to_stage_id:'done',allowed_roles:['admin'],is_active:true,version:3 }] : [] });
    const open = async () => {
      await fixture.componentInstance.workflow(); fixture.detectChanges(); await fixture.whenStable();
      const ref = dialog.openDialogs[0] as MatDialogRef<WorkflowEditor>;
      expect(document.querySelectorAll('mat-dialog-content .workflow-row').length).toBe(3);
      expect(ref.componentInstance.issue()).toBeNull(); expect(ref.componentInstance.busy()).toBeFalse();
      expect(ref.componentInstance.form.controls.reason.value).toBe(''); return ref;
    };
    const cancelled = await open(); cancelled.componentInstance.addStage(); cancelled.close(false);
    fixture.detectChanges(); await fixture.whenStable();
    const saved = await open(); expect(saved.componentInstance.stages.length).toBe(2);
    saved.componentInstance.form.controls.reason.setValue('Synthetic explicit graph save'); await saved.componentInstance.save();
    fixture.detectChanges(); await fixture.whenStable(); expect(api.writes.length).toBe(1);
    const conflicted = await open(); conflicted.componentInstance.form.controls.reason.setValue('Synthetic graph conflict');
    spyOn(api,'command').and.rejectWith(new HttpErrorResponse({ status:409,error:{ code:'VERSION_CONFLICT' } }));
    await conflicted.componentInstance.save(); expect(conflicted.componentInstance.issue()?.conflict).toBeTrue();
    conflicted.close('reload'); fixture.detectChanges(); await fixture.whenStable();
    const fresh = await open(); fresh.close(false); fixture.detectChanges(); await fixture.whenStable();
  });
  it('keeps task completion confirmation content visible on reopening', async () => {
    const fixture = await setup(TaskDetailPage,'admin',{ id:'synthetic-task' }), dialog = TestBed.inject(MatDialog);
    for (let attempt = 0; attempt < 2; attempt++) {
      const pending = fixture.componentInstance.completeChild(syntheticTask,{ id:'child',title:'Synthetic child',version:2 });
      fixture.detectChanges(); await fixture.whenStable();
      expect(document.querySelector('mat-dialog-content')?.textContent).toContain('Synthetic child');
      expect(document.querySelector('mat-dialog-content')?.textContent).toContain('sin reapertura');
      dialog.openDialogs[0].close(false); await pending; fixture.detectChanges(); await fixture.whenStable();
    }
    expect(api.writes).toEqual([]);
  });
  it('shows task and destination even when a stage needs no form fields', async () => {
    const fixture = await setup(ExecutionPage,'admin',{}, { view:'kanban' }), dialog = TestBed.inject(MatDialog);
    api.response = () => ({ stages:[{ id:'done',name:'Done',is_active:true }],transitions:[{ from_stage_id:'synthetic-open',to_stage_id:'done' }] });
    const pending = TestBed.inject(Transition).open(syntheticTask,'done');
    await fixture.whenStable(); fixture.detectChanges();
    expect(document.querySelector('mat-dialog-content')?.textContent).toContain('Synthetic task');
    expect(document.querySelector('mat-dialog-content')?.textContent).toContain('Done');
    dialog.openDialogs[0].close(false); await pending; expect(api.writes).toEqual([]);
  });
  it('uses the parent and child captured versions for completion', async () => {
    const fixture = await setup(TaskDetailPage,'colaborador',{ id:'synthetic-task' }); const dialog = dialogData(fixture);
    await fixture.componentInstance.completeChild(syntheticTask,{ id:'synthetic-child',version:3,title:'Child' });
    await dialog.data().submit({}); expect(api.writes[0]).toEqual({ path:'/subtasks/synthetic-child/completion',method:'POST',body:{ expected_version:3,expected_task_version:7 } });
  });
  it('never sends the original date in a due-date command', async () => {
    const fixture = await setup(TaskDetailPage,'gerente',{ id:'synthetic-task' }); const dialog = dialogData(fixture);
    await fixture.componentInstance.due(syntheticTask); const data = dialog.data(); expect(data.fields.map(field => field.key)).toEqual(['due_date','reason']);
    await data.submit({ due_date:'2028-01-05',reason:'Cambio explicitamente autorizado' });
    expect(api.writes[0].body).toEqual({ due_date:'2028-01-05',reason:'Cambio explicitamente autorizado',expected_version:7 });
  });
  it('requests a child date using the request DTO rather than mutating the date', async () => {
    const fixture = await setup(TaskDetailPage,'lider',{ id:'synthetic-task' }); const dialog = dialogData(fixture);
    await fixture.componentInstance.requestDate({ id:'synthetic-child',version:3 },syntheticTask);
    await dialog.data().submit({ proposed_due_date:'2027-12-01',reason:'Solicitud explicitamente motivada' });
    expect(api.writes[0].path).toBe('/subtasks/synthetic-child/due-date-requests');
    expect(api.writes[0].body['expected_task_version']).toBe(7); expect(api.writes[0].body['expected_subtask_version']).toBe(3);
    expect(api.writes[0].body['due_date']).toBeUndefined();
  });
  it('uses a versioned audited command for a cross-year plan period', async () => {
    const fixture = await setup(PlanningPage,'gerente',{ id:'synthetic-plan' },{ kind:'plans' }); const dialog = dialogData(fixture);
    expect(fixture.nativeElement.textContent).toContain('Sin datos');
    await fixture.componentInstance.period({ id:'synthetic-plan',version:4 });
    await dialog.data().submit({ horizon_type:'custom',start_date:'2027-11-15',due_date:'2028-02-20',reason:'Periodo explicitamente ampliado' });
    expect(api.writes[0].path).toBe('/annual-plans/synthetic-plan/period-changes'); expect(api.writes[0].body['expected_version']).toBe(4);
  });
  it('keeps the existing inactive horizon visible without offering invented catalog values for creation', async () => {
    const fixture = await setup(PlanningPage,'gerente',{ id:'synthetic-plan' },{ kind:'plans' }), dialog = dialogData(fixture);
    await fixture.componentInstance.period({ id:'synthetic-plan',version:4,horizon_type:'annual',start_date:'2027-01-01',due_date:'2027-12-31' });
    const horizon = dialog.data().fields.find(field => field.key === 'horizon_type');
    expect(horizon?.value).toBe('annual'); expect(horizon?.options?.map(option => option.value)).toEqual(['annual']);
    expect(dialog.data().fields.find(field => field.key === 'reason')?.value).toBeUndefined();
  });
  it('refreshes plan detail after a confirmed edit and keeps the original version in its command', async () => {
    const fixture = await setup(PlanningPage,'gerente',{ id:'synthetic-plan' },{ kind:'plans' });
    spyOn(fixture.debugElement.injector.get(MatDialog),'open').and.returnValue({ afterClosed:() => of(true) } as MatDialogRef<unknown>);
    const refresh = spyOn(fixture.componentInstance,'load').and.resolveTo();
    await fixture.componentInstance.edit({ id:'synthetic-plan',version:4,title:'Current' }); expect(refresh).toHaveBeenCalledTimes(1);
  });
  it('refreshes task, child and history context after a confirmed command', async () => {
    const fixture = await setup(TaskDetailPage,'admin',{ id:'synthetic-task' });
    spyOn(fixture.debugElement.injector.get(MatDialog),'open').and.returnValue({ afterClosed:() => of(true) } as MatDialogRef<unknown>);
    const refresh = spyOn(fixture.componentInstance,'load').and.resolveTo();
    await fixture.componentInstance.editChild(syntheticTask,{ id:'child',title:'Current child',version:2 }); expect(refresh).toHaveBeenCalledTimes(1);
  });
  it('refreshes a request after cancellation without prefilling the prior reason', async () => {
    const fixture = await setup(RequestsPage,'gerente',{ id:'synthetic-request' });
    const open = spyOn(fixture.debugElement.injector.get(MatDialog),'open').and.returnValue({ afterClosed:() => of(true) } as MatDialogRef<unknown>);
    const refresh = spyOn(fixture.componentInstance,'load').and.resolveTo();
    fixture.componentInstance.decide({ ...syntheticRequest,reason:'Previous request reason' },'cancel');
    const data = open.calls.mostRecent().args[1]?.data as EditData;
    expect(data.fields[0].value).toBeUndefined(); await data.submit({ reason:'Current cancellation reason' });
    expect(api.writes[0].body).toEqual({ expected_version:2,reason:'Current cancellation reason' }); expect(refresh).toHaveBeenCalledTimes(1);
  });
  it('shows dependency problems and request ID while retaining a deactivation form on 409', async () => {
    const fixture = await setup(AdminPage,'admin',{ section:'departamentos' });
    fixture.componentInstance.changeActivity({ id:'department',name:'Current',version:2,is_active:true });
    fixture.detectChanges(); await fixture.whenStable();
    const dialog = TestBed.inject(MatDialog), editor = dialog.openDialogs[0].componentInstance as Editor;
    editor.form.patchValue({ reason:'Current deactivation reason' });
    const command = spyOn(api,'command').and.rejectWith(new HttpErrorResponse({ status:409,error:{ code:'DEPARTMENT_HAS_ACTIVE_USERS',request_id:'dependency-conflict',detail:'SECRET SQL' } }));
    await editor.save(); fixture.detectChanges();
    expect(editor.form.controls['reason'].value).toBe('Current deactivation reason');
    expect(document.querySelector('mat-dialog-content')?.textContent).toContain('dependency-conflict');
    expect(document.querySelector('mat-dialog-content')?.textContent).not.toContain('SECRET SQL');
    await editor.save(); expect(command).toHaveBeenCalledTimes(1);
    dialog.openDialogs[0].close(false); fixture.detectChanges(); await fixture.whenStable();
  });
  it('does not offer self approval and preserves the reject/cancel alternatives', async () => {
    const fixture = await setup(RequestsPage,'gerente',{ id:'synthetic-request' });
    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).map(button => button.textContent);
    expect(buttons.some(value => value?.includes('Aprobar'))).toBeFalse(); expect(buttons.some(value => value?.includes('Rechazar'))).toBeTrue();
  });
  it('blocks approval when the captured task version no longer matches', async () => {
    const fixture = await setup(RequestsPage,'gerente',{ id:'synthetic-request' });
    fixture.componentInstance.record.set({ ...syntheticRequest,requested_by:'someone-else',task_version_at_request:6 }); fixture.detectChanges();
    expect(fixture.componentInstance.stale()).toBeTrue();
    const approve = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(button => button.textContent?.includes('Aprobar'));
    expect(approve?.disabled).toBeTrue(); expect(api.writes).toEqual([]);
  });
  it('submits the request version and reason for a decision', async () => {
    const fixture = await setup(RequestsPage,'gerente',{ id:'synthetic-request' }); const dialog = dialogData(fixture);
    fixture.componentInstance.decide(syntheticRequest,'reject'); await dialog.data().submit({ reason:'Rechazo explicitamente motivado' });
    expect(api.writes[0]).toEqual({ path:'/due-date-requests/synthetic-request/reject',method:'POST',body:{ reason:'Rechazo explicitamente motivado',expected_version:2 } });
  });
  it('keeps an authorized request visible if its task context fails and does not enable approval', async () => {
    const fixture = await setup(RequestsPage,'gerente',{ id:'synthetic-request' });
    api.response = path => {
      if (path === '/due-date-requests/synthetic-request') return { ...syntheticRequest,requested_by:'other',reason:'Previous request reason' };
      throw new HttpErrorResponse({ status:503,error:{ request_id:'context-unavailable',detail:'SECRET SQL' } });
    };
    await fixture.componentInstance.load(); fixture.detectChanges();
    expect(fixture.componentInstance.record()?.['id']).toBe('synthetic-request'); expect(fixture.componentInstance.context()).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Previous request reason'); expect(fixture.nativeElement.textContent).toContain('context-unavailable');
    expect(fixture.nativeElement.textContent).not.toContain('SECRET SQL');
    const approve = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(button => button.textContent?.includes('Aprobar'));
    expect(approve?.disabled).toBeTrue(); expect(api.writes).toEqual([]);
  });
  it('F5 preserves active empty Kanban columns without writes', async () => {
    const fixture = await setup(ExecutionPage,'admin',{}, { view:'kanban' });
    api.response = path => path === '/kanban' ? { columns:[
      { stage:{ id:'open',name:'Abierta' },count:1,items:[syntheticTask] },
      { stage:{ id:'done',name:'Terminada' },count:0,items:[] },
    ] } : { items:[] };
    await fixture.componentInstance.load(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.kanban-lane').length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('Sin tareas.'); expect(api.writes).toEqual([]);
  });
  it('F5 collaborator views never fetch planning modules or offer planning Timeline levels', async () => {
    const fixture = await setup(ExecutionPage,'colaborador',{}, { view:'kanban' });
    expect(api.reads).not.toContain('/annual-plans'); expect(api.reads).not.toContain('/objectives'); expect(api.reads).not.toContain('/catalogs/departments');
    expect(fixture.componentInstance.kinds.map(item => item.value)).toEqual(['task','subtask']);
  });
  it('F5 does not move a manager card even through a direct method call', async () => {
    const fixture = await setup(ExecutionPage,'gerente',{}, { view:'kanban' });
    const transition = spyOn(TestBed.inject(Transition),'open');
    await fixture.componentInstance.move(syntheticTask,'done'); expect(transition).not.toHaveBeenCalled(); expect(api.writes).toEqual([]);
  });
  it('F5 does not optimistically move a card when a transition is cancelled', async () => {
    const fixture = await setup(ExecutionPage,'admin',{}, { view:'kanban' });
    const lane = { stage:{ id:'synthetic-open' },count:1,items:[syntheticTask] };
    fixture.componentInstance.lanes.set([lane]);
    spyOn(TestBed.inject(Transition),'open').and.resolveTo(false);
    await fixture.componentInstance.move(syntheticTask,'done'); expect(fixture.componentInstance.lanes()[0]).toBe(lane);
  });
  for (const [status,code] of [[409,'VERSION_CONFLICT'],[422,'REASON_REQUIRED'],[403,'FORBIDDEN']] as [number,string][]) {
    it('retains the Kanban card, current reason and request reference on ' + status, async () => {
      const fixture = await setup(ExecutionPage,'admin',{}, { view:'kanban' });
      const lane = { stage:{ id:'synthetic-open',name:'Abierta' },count:1,items:[syntheticTask] };
      fixture.componentInstance.lanes.set([lane]);
      api.response = () => ({ stages:[{ id:'done',name:'Terminada',requires_reason:true }],transitions:[{ from_stage_id:'synthetic-open',to_stage_id:'done' }] });
      const write = spyOn(api,'command').and.rejectWith(new HttpErrorResponse({ status,error:{ code,request_id:'kanban-rejected',detail:'SECRET SQL' } }));
      const pending = fixture.componentInstance.move(syntheticTask,'done');
      await fixture.whenStable(); fixture.detectChanges();
      const dialog = TestBed.inject(MatDialog), editor = dialog.openDialogs[0].componentInstance as Editor;
      expect(editor.form.controls['reason'].value).toBeNull();
      editor.form.patchValue({ reason:'Current transition justification' }); await editor.save(); fixture.detectChanges();
      expect(editor.form.controls['reason'].value).toBe('Current transition justification');
      expect(editor.issue()?.requestId).toBe('kanban-rejected'); expect(editor.issue()?.conflict).toBe(status === 409);
      expect(document.querySelector('mat-dialog-content')?.textContent).not.toContain('SECRET SQL');
      expect(fixture.componentInstance.lanes()[0]).toBe(lane);
      expect(write.calls.mostRecent().args[1]['expected_version']).toBe(7);
      if (status === 409) { await editor.save(); expect(write).toHaveBeenCalledTimes(1); }
      dialog.openDialogs[0].close(false); await pending;
      expect(fixture.componentInstance.lanes()[0]).toBe(lane); expect(fixture.componentInstance.moving()).toBeFalse();
    });
  }
  it('F5 uses required evidence IDs and the captured version in the shared transition', async () => {
    await setup(ExecutionPage,'admin',{}, { view:'kanban' });
    api.response = path => path === '/catalogs/workflow' ? {
      stages:[{ id:'done',name:'Terminada',requires_evidence:true,requires_reason:true }],
      transitions:[{ from_stage_id:'synthetic-open',to_stage_id:'done' }],
    } : { items:[{ id:'file',original_name:'synthetic.pdf' }] };
    const open = spyOn(TestBed.inject(MatDialog),'open').and.returnValue({ afterClosed:() => of(false) } as MatDialogRef<unknown>);
    await TestBed.inject(Transition).open(syntheticTask,'done');
    const data = open.calls.mostRecent().args[1]!.data as EditData;
    expect(data.fields.find(field => field.key === 'evidence_ids')?.required).toBeTrue();
    expect(data.fields.find(field => field.key === 'evidence_ids')?.options?.[0].value).toBe('file');
    await data.submit({ evidence_ids:['file'],reason:'Synthetic explicit reason' });
    expect(api.writes[0].body).toEqual({ evidence_ids:['file'],reason:'Synthetic explicit reason',expected_version:7,to_stage_id:'done' });
  });
  it('F5 renders Timeline data as text and preserves original/current dates in its table', async () => {
    const fixture = await setup(ExecutionPage,'admin',{}, { view:'timeline' });
    api.response = () => ({ items:[{ ...syntheticTask,title:'<img src=x onerror=alert(1)>',row_type:'task',task_id:'synthetic-task' }],next_cursor:null,organization_timezone:'Pacific/Auckland' });
    await fixture.componentInstance.load(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.vis-timeline')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.vis-timeline img')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('2027-12-01'); expect(fixture.nativeElement.textContent).toContain('2028-01-01');
    expect(fixture.componentInstance.instant('2027-12-01T10:00:00Z')).toBe(new Intl.DateTimeFormat('es-MX',{ timeZone:'Pacific/Auckland',dateStyle:'medium',timeStyle:'short' }).format(new Date('2027-12-01T10:00:00Z')));
    expect(api.writes).toEqual([]);
  });
  it('F5 rejects empty/oversize and MIME-extension mismatch before an explicit upload', async () => {
    const fixture = await setup(Evidence); const component = fixture.componentInstance;
    const choose = (file:File) => component.choose({ target:{ files:[file],value:'synthetic' } } as unknown as Event);
    choose(new File([], 'empty.pdf',{ type:'application/pdf' })); expect(component.file()).toBeNull();
    choose(new File(['x'.repeat(1025)], 'large.pdf',{ type:'application/pdf' })); expect(component.file()).toBeNull();
    choose(new File(['synthetic'], 'wrong.png',{ type:'application/pdf' })); expect(component.file()).toBeNull();
    choose(new File(['synthetic'], 'valid.pdf',{ type:'application/pdf' })); expect(component.file()?.name).toBe('valid.pdf'); expect(api.writes).toEqual([]);
  });
  it('F5 blocks resending an evidence conflict until explicit discard/reload', async () => {
    const fixture = await setup(Evidence); const component = fixture.componentInstance;
    component.file.set(new File(['synthetic'],'synthetic.pdf',{ type:'application/pdf' }));
    const upload = jasmine.createSpy().and.rejectWith(new HttpErrorResponse({ status:409,error:{ code:'VERSION_CONFLICT' } }));
    (api as unknown as { upload:unknown }).upload = upload;
    await component.upload(); await component.upload(); expect(upload).toHaveBeenCalledTimes(1); expect(component.file()).not.toBeNull();
    const reload = spyOn(component.refresh,'emit'); component.discard(); expect(component.file()).toBeNull(); expect(reload).toHaveBeenCalled();
  });
  it('clears a transient evidence query problem after a successful reload', async () => {
    const fixture = await setup(Evidence), component = fixture.componentInstance;
    const read = spyOn(api,'get').and.rejectWith(new HttpErrorResponse({ status:503,error:{ request_id:'evidence-unavailable' } }));
    await component.load(); expect(component.issue()?.requestId).toBe('evidence-unavailable');
    read.and.callThrough(); await component.load(); expect(component.issue()).toBeNull(); expect(api.writes).toEqual([]);
  });
  it('keeps the evidence conflict through successful or failed reloads and download failures', async () => {
    const fixture = await setup(Evidence), component = fixture.componentInstance;
    const conflict = { message:'Current conflict',conflict:true,requestId:'evidence-conflict' };
    component.issue.set(conflict); await component.load(); expect(component.issue()).toBe(conflict);
    spyOn(api,'get').and.rejectWith(new HttpErrorResponse({ status:503 }));
    await component.load(); expect(component.issue()).toBe(conflict);
    (api as unknown as { download:unknown }).download = jasmine.createSpy().and.rejectWith(new HttpErrorResponse({ status:503 }));
    await component.download({ id:'synthetic-file' }); expect(component.issue()).toBe(conflict); expect(api.writes).toEqual([]);
  });
  it('F5 keeps civil dates inclusive across year/leap boundaries', () => {
    const date = civilDate('2028-02-29'); expect([date.getFullYear(),date.getMonth(),date.getDate(),date.getHours()]).toEqual([2028,1,29,0]);
    const next = civilDate('2027-12-31',true); expect([next.getFullYear(),next.getMonth(),next.getDate()]).toEqual([2028,0,1]);
  });
});

describe('F5 binary transport', () => {
  it('sends raw bytes, file metadata and expected version without a public file URL', async () => {
    TestBed.configureTestingModule({ providers:[provideHttpClient(),provideHttpClientTesting()] });
    const api = TestBed.inject(Api), http = TestBed.inject(HttpTestingController);
    const file = new File(['synthetic'],'synthetic report.pdf',{ type:'application/pdf' });
    const upload = api.upload(syntheticTask,file), request = http.expectOne('/api/v1/tasks/synthetic-task/evidence?expected_version=7');
    expect(request.request.body).toBe(file); expect(request.request.headers.get('X-File-Name')).toBe('synthetic%20report.pdf'); expect(request.request.headers.get('Content-Type')).toBe('application/pdf');
    request.flush({}); await upload;
    const download = api.download('synthetic-file'), response = http.expectOne('/api/v1/evidence/synthetic-file/content');
    expect(response.request.responseType).toBe('blob'); response.flush(new Blob(['synthetic'])); await download; http.verify();
  });
});

describe('F4 direct route guards', () => {
  for (const role of ['gerente','lider','colaborador'] as Role[]) {
    it('denies administration by direct URL to ' + role, async () => {
      TestBed.configureTestingModule({ providers:[provideRouter(routes),provideNoopAnimations(),{ provide:Session,useValue:{ restore:async () => {},user:signal({ role,display_name:'Synthetic',permissions:permissions[role] }),has:(permission:string) => permissions[role].includes(permission) } }] });
      const harness = await RouterTestingHarness.create(); await harness.navigateByUrl('/administracion/usuarios');
      expect(harness.routeNativeElement?.textContent).toContain('Acceso no disponible');
    });
  }
  it('denies planning and date requests by direct URL to a collaborator', async () => {
    TestBed.configureTestingModule({ providers:[provideRouter(routes),provideNoopAnimations(),{ provide:Session,useValue:{ restore:async () => {},user:signal({ role:'colaborador',display_name:'Synthetic',permissions:permissions.colaborador }),has:(permission:string) => permissions.colaborador.includes(permission) } }] });
    const harness = await RouterTestingHarness.create();
    for (const path of ['/planes','/objetivos/foreign','/solicitudes-fecha']) { await harness.navigateByUrl(path); expect(harness.routeNativeElement?.textContent).toContain('Acceso no disponible'); }
  });
});