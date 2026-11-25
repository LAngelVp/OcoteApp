import { Type, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { Api, Row } from './core/api';
import { Session } from './core/session';
import { AnalyticsPage } from './operations/analytics.page';
import { EvaluationsPage } from './operations/evaluations.page';
import { EditData } from './shared/editor';
import { ExportMenu } from './shared/export-menu';

const metrics: Row = { task_count:4,completed_count:2,completion_rate:50,progress_percent:50,baseline_on_time_rate:25,on_time_rate:50,annual_plan:{ title:'Plan capturado',horizon_type:'custom',start_date:'2024-01-01',due_date:'2027-12-31' },department:{ name:'Departamento capturado' },evaluator:{ display_name:'Evaluador capturado' } };
const evaluation: Row = { id:'evaluation',version:3,status:'draft',can_finalize:true,period_start:'2025-01-01',period_end:'2025-12-31',snapshot_at:'2026-11-25T18:00:00Z',organization_timezone:'America/Mexico_City',calculation_version:'1.0',metrics,items:[],next_cursor:null };

class ReportsApi {
  reads: { path:string;query:Record<string,string> }[] = [];
  writes: { path:string;body:Row }[] = [];
  response: (path:string,query:Record<string,string>) => unknown = path => path.startsWith('/analytics/') ? { items:[],next_cursor:null,metrics:{ task_count:0,progress_percent:null,completion_rate:null,baseline_on_time_rate:null,on_time_rate:null },filters:{},snapshot_at:evaluation['snapshot_at'],organization_timezone:'America/Mexico_City' } : path === '/evaluations/evaluation' ? { ...evaluation } : { items:[],next_cursor:null };
  async get<T>(path:string,query:Record<string,string> = {}):Promise<T> { this.reads.push({ path,query }); return this.response(path,query) as T; }
  async all(path:string):Promise<Row[]> { this.reads.push({ path,query:{} }); return []; }
  async command(path:string,body:Row):Promise<Row> { this.writes.push({ path,body }); return {}; }
  async exportFile(path:string,body:Row):Promise<Blob> { this.writes.push({ path,body }); return new Blob(['synthetic']); }
}

describe('F6 browser contracts, synthetic only', () => {
  let api: ReportsApi;
  const setup = async <T>(component:Type<T>, permissions = ['analytics:read','evaluations:read','evaluations:manage','exports:read'], id = ''):Promise<ComponentFixture<T>> => {
    api = new ReportsApi();
    await TestBed.configureTestingModule({ imports:[component],providers:[provideRouter([]),provideNoopAnimations(),{ provide:Api,useValue:api },{ provide:Session,useValue:{ has:(permission:string) => permissions.includes(permission),user:signal(null) } },{ provide:ActivatedRoute,useValue:{ paramMap:of(convertToParamMap(id ? { id } : {})) } }] }).compileComponents();
    const fixture = TestBed.createComponent(component); fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges(); return fixture;
  };
  for (const component of [AnalyticsPage,EvaluationsPage] as Type<unknown>[]) it('makes no reporting or catalog reads without permission: ' + component.name, async () => {
    await setup(component,[]); expect(api.reads).toEqual([]); expect(api.writes).toEqual([]);
  });
  it('keeps empty analytics rates null and never invents a period', async () => {
    const fixture = await setup(AnalyticsPage);
    expect(fixture.componentInstance.metrics()?.['completion_rate']).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Sin datos');
    expect(fixture.componentInstance.form.getRawValue().period_start).toBe('');
    expect(api.reads.filter(read => read.path.startsWith('/analytics/')).every(read => read.query['limit'] === '5')).toBeTrue();
    fixture.componentInstance.form.controls.period_start.setValue('2025-01-01'); const before = api.reads.length;
    fixture.componentInstance.apply(); expect(api.reads.length).toBe(before); expect(fixture.componentInstance.form.hasError('period')).toBeTrue();
  });
  it('keeps explicit filters on five-row pages and resets cursors for all page sizes', async () => {
    const fixture = await setup(AnalyticsPage), page = fixture.componentInstance;
    api.response = (path,query) => ({ metrics,filters:query,snapshot_at:evaluation['snapshot_at'],organization_timezone:'America/Mexico_City',items:Array.from({ length:Number(query['limit'] ?? 5) },(_,index) => ({ id:'department-' + index,name:'Department ' + index,month:String(2025 + Math.floor(index / 12)) + '-' + String(index % 12 + 1).padStart(2,'0'),...metrics })),next_cursor:query['cursor'] ? null : path.endsWith('summary') ? 'department-next' : '2025-05' });
    page.form.patchValue({ period_start:'2025-01-01',period_end:'2027-12-31',status:'open' }); page.apply(); await fixture.whenStable(); fixture.detectChanges();
    expect(page.panels[0].report()?.items.length).toBe(5); expect(page.metrics()?.['baseline_on_time_rate']).toBe(25);
    await page.load('summary','department-next'); expect(page.panels[0].pagination.number()).toBe(2);
    for (const size of [10,20,50,5]) { page.resize('summary',size); await fixture.whenStable(); fixture.detectChanges(); expect(page.panels[0].report()?.items.length).toBe(size); expect(page.panels[0].pagination.number()).toBe(1); }
    const request = api.reads.filter(read => read.path === '/analytics/summary').at(-1)!;
    expect(request.query['status']).toBe('open'); expect(request.query['period_start']).toBe('2025-01-01'); expect(request.query['cursor']).toBeUndefined();
    expect(api.writes).toEqual([]);
  });
  it('paginates evaluation lists without commands or default business selections', async () => {
    const fixture = await setup(EvaluationsPage), page = fixture.componentInstance;
    api.response = (_path,query) => ({ items:Array.from({ length:Number(query['limit'] ?? 5) },(_,index) => ({ ...evaluation,id:'evaluation-' + index })),next_cursor:query['cursor'] ? null : 'next' });
    await page.load(); expect(page.rows().length).toBe(5); await page.load('next'); expect(page.pagination.number()).toBe(2);
    page.resize(20); await fixture.whenStable(); expect(page.rows().length).toBe(20); expect(page.pagination.number()).toBe(1);
    const open = spyOn(fixture.debugElement.injector.get(MatDialog),'open').and.returnValue({ afterClosed:() => of(false) } as MatDialogRef<unknown>);
    page.create(); const data = open.calls.mostRecent().args[1]?.data as EditData;
    expect(data.fields.every(field => field.value === undefined)).toBeTrue(); expect(data.validate?.({ period_start:'2025-12-31',period_end:'2025-01-01' })).toBeTruthy(); expect(api.writes).toEqual([]);
  });
  it('uses the stored cut and sends only the selected evaluation version on explicit recalculation', async () => {
    const fixture = await setup(EvaluationsPage,undefined,'evaluation'), page = fixture.componentInstance;
    expect(fixture.nativeElement.textContent).toContain('Plan capturado'); expect(fixture.nativeElement.textContent).toContain('Departamento capturado');
    expect(fixture.nativeElement.textContent).toContain('25%'); expect(api.writes).toEqual([]);
    const open = spyOn(fixture.debugElement.injector.get(MatDialog),'open').and.returnValue({ afterClosed:() => of(false) } as MatDialogRef<unknown>);
    page.change(evaluation,false); const data = open.calls.mostRecent().args[1]?.data as EditData; await data.submit({});
    expect(api.writes).toEqual([{ path:'/evaluations/evaluation/recalculate',body:{ expected_version:3 } }]);
    page.change(evaluation,true); const final = open.calls.mostRecent().args[1]?.data as EditData;
    expect(final.fields.map(field => [field.key,field.min,field.max])).toEqual([['summary',10,4000]]);
    await final.submit({ summary:'Conclusion explicita' }); expect(api.writes.at(-1)?.body).toEqual({ expected_version:3,summary:'Conclusion explicita' });
  });
  it('honors server finalization eligibility and never offers final mutations', async () => {
    const fixture = await setup(EvaluationsPage,undefined,'evaluation'), page = fixture.componentInstance;
    const open = spyOn(fixture.debugElement.injector.get(MatDialog),'open');
    page.change({ ...evaluation,can_finalize:false },true); page.change({ ...evaluation,status:'final' },false); expect(open).not.toHaveBeenCalled();
    api.response = () => ({ ...evaluation,status:'final',can_finalize:false,summary:'Conclusion sellada' }); await page.load(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Conclusion sellada'); expect(fixture.nativeElement.textContent).not.toContain('Recalcular corte'); expect(fixture.nativeElement.querySelector('ocote-export')).not.toBeNull();
  });
  it('keeps leader final reads free of evaluation management controls', async () => {
    const fixture = await setup(EvaluationsPage,['evaluations:read','exports:read']);
    expect(fixture.nativeElement.textContent).not.toContain('Crear evaluacion'); fixture.componentInstance.create(); expect(api.writes).toEqual([]);
  });
  it('blocks duplicate export sends and displays problem references', async () => {
    api = new ReportsApi(); await TestBed.configureTestingModule({ imports:[ExportMenu],providers:[{ provide:Api,useValue:api },provideNoopAnimations()] }).compileComponents();
    const fixture = TestBed.createComponent(ExportMenu); fixture.componentRef.setInput('path','/exports/tasks'); fixture.componentRef.setInput('filters',{ department_id:'department' });
    const failure = new HttpErrorResponse({ status:413,error:{ code:'EXPORT_TOO_LARGE',request_id:'export-reference' } }); spyOn(api,'exportFile').and.rejectWith(failure);
    const pending = fixture.componentInstance.download('csv'); await fixture.componentInstance.download('json'); await pending;
    expect(api.exportFile).toHaveBeenCalledOnceWith('/exports/tasks',{ department_id:'department',format:'csv' }); expect(fixture.componentInstance.issue()?.requestId).toBe('export-reference'); expect(fixture.componentInstance.busy()).toBeFalse();
  });
});

describe('F6 authenticated Blob errors', () => {
  it('preserves application/problem+json on binary download failures', async () => {
    TestBed.configureTestingModule({ providers:[provideHttpClient(),provideHttpClientTesting()] }); const api = TestBed.inject(Api), http = TestBed.inject(HttpTestingController);
    const response = api.exportFile('/exports/tasks',{ format:'json' }).catch(error => error);
    const request = http.expectOne('/api/v1/exports/tasks'); expect(request.request.method).toBe('POST'); expect(request.request.responseType).toBe('blob');
    request.flush(new Blob([JSON.stringify({ code:'EXPORT_TOO_LARGE',request_id:'blob-reference' })],{ type:'application/problem+json' }),{ status:413,statusText:'Payload Too Large' });
    const error = await response as HttpErrorResponse; expect(error.error.request_id).toBe('blob-reference'); expect(error.status).toBe(413); http.verify();
  });
});