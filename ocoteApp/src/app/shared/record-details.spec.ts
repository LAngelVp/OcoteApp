import { TestBed } from '@angular/core/testing';
import { Row } from '../core/api';
import { RecordDetails } from './record-details';

describe('Read-only structured record details', () => {
  const setup = async (record: Row, summary = false) => {
    await TestBed.configureTestingModule({ imports: [RecordDetails] }).compileComponents();
    const fixture = TestBed.createComponent(RecordDetails);
    fixture.componentRef.setInput('record', record); fixture.componentRef.setInput('summary', summary);
    fixture.detectChanges(); return fixture;
  };
  it('renders Spanish labels, flags, roles and zero without raw JSON or changing the input', async () => {
    const row = Object.freeze({ name:'Initial',code:'open',position:0,is_active:true,is_initial:true,requires_evidence:false,allowed_roles:['admin','lider'] });
    const fixture = await setup(row,true), content = fixture.nativeElement.textContent as string;
    expect(content).toContain('Initial'); expect(content).toContain('Informaci\u00f3n general');
    expect(content).toContain('Activo'); expect(content).toContain('Inicial'); expect(content).toContain('No');
    expect(content).toContain('Administrador'); expect(content).toContain('L\u00edder'); expect(content).toContain('0');
    expect(fixture.nativeElement.querySelectorAll('pre').length).toBe(0);
    expect(fixture.nativeElement.querySelectorAll('.badge').length).toBeGreaterThan(3);
    expect(content).not.toContain('is_active'); expect(row.position).toBe(0);
  });
  it('formats instants in Mexico City and keeps civil dates on their original day', async () => {
    const fixture = await setup({ created_at:'2026-11-25T02:00:00Z',due_date:'2028-02-29',updated_at:'invalid' });
    const content = fixture.nativeElement.textContent as string;
    const expected = new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short',timeZone:'America/Mexico_City'}).format(new Date('2026-11-25T02:00:00Z'));
    expect(content).toContain(expected); expect(content).toContain('29 de febrero de 2028');
    expect(content).toContain('Fecha no disponible'); expect(fixture.nativeElement.querySelector('time[datetime="2026-11-25T02:00:00Z"]')?.dateTime).toBe('2026-11-25T02:00:00Z');
  });
  it('shows nested audit snapshots and object lists as sections, never object coercion', async () => {
    const fixture = await setup({ before_data:{ is_active:false,department_id:null },after_data:{ is_active:true,reason:'Current reason' },evidence:[{ name:'Attachment',id:'file-id' }] });
    const content = fixture.nativeElement.textContent as string;
    expect(content).toContain('Estado anterior'); expect(content).toContain('Estado posterior');
    expect(content).toContain('Inactivo'); expect(content).toContain('Current reason'); expect(content).toContain('Attachment');
    expect(content).not.toContain('[object Object]'); expect(content).not.toContain('{');
  });
  it('handles nulls, missing values and empty collections without dropping false or zero', async () => {
    const fixture = await setup({ name:null,description:'',allowed_roles:[],before_data:{},position:0,is_active:false });
    const content = fixture.nativeElement.textContent as string;
    expect(content).toContain('Sin informaci\u00f3n'); expect(content).toContain('Sin elementos');
    expect(content).toContain('Inactivo'); expect(content).toContain('0');
    fixture.componentRef.setInput('record',{}); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Sin informaci\u00f3n registrada.');
  });
  it('escapes user content and omits secret fields even in nested snapshots', async () => {
    const fixture = await setup({ name:'<img src=x onerror=alert(1)>',password_hash:'PRIVATE',after_data:{ access_token:'PRIVATE',name:'Allowed' } });
    expect(fixture.nativeElement.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('PRIVATE'); expect(fixture.nativeElement.textContent).toContain('Allowed');
  });
  it('refreshes every section when another record is displayed', async () => {
    const fixture = await setup({ name:'Previous',is_active:true },true);
    fixture.componentRef.setInput('record',{ key:'organization_timezone',value:'America/Mexico_City',version:2 }); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('Previous');
    expect(fixture.nativeElement.textContent).toContain('Zona horaria'); expect(fixture.nativeElement.textContent).toContain('America/Mexico_City');
  });
  it('preserves codes and free text even when they match an enum and puts general information first', async () => {
    const fixture = await setup({ id:'record-id',version:1,name:'admin',code:'open',value:'custom',reason:'active' },true);
    expect(fixture.nativeElement.querySelector('h3')?.textContent).toBe('admin');
    const definitions = Array.from(fixture.nativeElement.querySelectorAll('.record-field') as NodeListOf<HTMLElement>);
    expect(definitions.find(field => field.querySelector('dt')?.textContent === 'C\u00f3digo')?.querySelector('dd')?.textContent?.trim()).toBe('open');
    expect(definitions.find(field => field.querySelector('dt')?.textContent === 'Valor')?.querySelector('dd')?.textContent?.trim()).toBe('custom');
    expect(fixture.nativeElement.querySelector('h4')?.textContent).toBe('Informaci\u00f3n general');
  });
});