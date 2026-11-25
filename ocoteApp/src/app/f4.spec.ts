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
import { WorkflowEditor } from './admin/workflow.editor';
import { EditData } from './shared/editor';
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
  it('starts an atomic workflow with no invented stages, transitions or roles', async () => {
    const fixture = await setup(WorkflowEditor); expect(fixture.componentInstance.stages.length).toBe(0); expect(fixture.componentInstance.transitions.length).toBe(0);
    fixture.componentInstance.addStage(); expect(fixture.componentInstance.stages.at(0).get('code')?.value).toBe('');
    expect(fixture.componentInstance.stages.at(0).get('kind')?.value).toBe(''); expect(api.writes).toEqual([]);
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
  it('F5 uses required evidence IDs and the captured version in the shared transition', async () => {
    await setup(ExecutionPage,'admin',{}, { view:'kanban' });
    api.response = path => path === '/catalogs/workflow' ? {
      stages:[{ id:'done',name:'Terminada',is_active:true,requires_evidence:true,requires_reason:true }],
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