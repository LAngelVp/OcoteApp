import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Editor, EditData, reason } from './editor';
import { problem } from '../core/problem';

describe('F4 command editor and sanitized errors', () => {
  const setup = (data: EditData) => {
    const close = jasmine.createSpy('close');
    TestBed.configureTestingModule({ imports:[Editor],providers:[provideNoopAnimations(),{ provide:MAT_DIALOG_DATA,useValue:data },{ provide:MatDialogRef,useValue:{ close,disableClose:false } }] });
    const fixture = TestBed.createComponent(Editor); fixture.detectChanges(); return { fixture,editor:fixture.componentInstance,close };
  };
  it('opens empty without creating or defaulting business values', () => {
    const submit = jasmine.createSpy().and.resolveTo({}); const { editor } = setup({ title:'Nuevo',fields:[{ key:'name',label:'Nombre',required:true }],submit });
    expect(editor.form.getRawValue()).toEqual({ name:null }); expect(editor.form.invalid).toBeTrue(); expect(submit).not.toHaveBeenCalled();
  });
  it('keeps user input and blocks re-sending a stale version after 409', async () => {
    const submit = jasmine.createSpy().and.rejectWith(new HttpErrorResponse({ status:409,error:{ code:'VERSION_CONFLICT' } }));
    const { editor,close } = setup({ title:'Editar',fields:[{ key:'title',label:'Titulo',value:'Edicion propia' }],submit });
    await editor.save(); expect(editor.form.getRawValue()['title']).toBe('Edicion propia'); expect(editor.issue()?.conflict).toBeTrue();
    await editor.save(); expect(submit).toHaveBeenCalledTimes(1); expect(close).not.toHaveBeenCalled();
  });
  it('rejects decimals for integer settings', () => {
    const { editor } = setup({ title:'Limite',fields:[{ key:'value',label:'Limite',type:'number',required:true,min:1,max:10000 }],submit:async () => ({}) });
    editor.form.patchValue({ value:1.5 }); expect(editor.form.invalid).toBeTrue(); editor.form.patchValue({ value:2 }); expect(editor.form.valid).toBeTrue();
  });
  it('converts actual numeric input to integer JSON rather than a string', async () => {
    const submit = jasmine.createSpy().and.resolveTo({});
    const { editor,fixture } = setup({ title:'Prioridad',fields:[{ key:'position',label:'Posicion',type:'number',required:true,min:0 }],submit });
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = '2'; input.dispatchEvent(new Event('input')); fixture.detectChanges();
    expect(editor.form.controls['position'].value).toBe(2); expect(editor.form.valid).toBeTrue();
    await editor.save(); expect(submit).toHaveBeenCalledOnceWith({ position:2 });
  });
  it('normalizes integer strings without truncating decimals or guessing locale separators', async () => {
    const submit = jasmine.createSpy().and.resolveTo({});
    const { editor } = setup({ title:'Horizonte',fields:[{ key:'position',label:'Posicion',type:'number',required:true,min:0,value:' 0 ' }],submit });
    expect(editor.form.controls['position'].value).toBe(0);
    for (const value of ['1,5','1.5','1,000','2abc',true,Infinity,Number.MAX_SAFE_INTEGER + 1,-1,'']) {
      editor.form.patchValue({ position:value }); expect(editor.form.invalid).withContext(String(value)).toBeTrue();
    }
    editor.form.patchValue({ position:' 3 ' }); expect(editor.form.valid).toBeTrue();
    await editor.save(); expect(submit).toHaveBeenCalledOnceWith({ position:3 });
  });
  it('supports cross-year civil ranges, rejects reversed ranges and short reasons', () => {
    const { editor } = setup({ title:'Periodo',fields:[{ key:'start_date',label:'Inicio',type:'date',required:true },{ key:'due_date',label:'Fin',type:'date',required:true },reason()],submit:async () => ({}) });
    editor.form.patchValue({ start_date:'2027-11-15',due_date:'2028-02-20',reason:'Cambio explicitamente motivado' }); expect(editor.form.valid).toBeTrue();
    editor.form.patchValue({ due_date:'2027-01-01' }); expect(editor.form.hasError('period')).toBeTrue();
    editor.form.patchValue({ due_date:'2028-02-20',reason:'corto' }); expect(editor.form.invalid).toBeTrue();
  });
  it('renders and revalidates command rules without closing or clearing fields', async () => {
    const submit = jasmine.createSpy().and.resolveTo({});
    const { editor,fixture,close } = setup({ title:'Regla',fields:[{ key:'name',label:'Nombre' }],validate:values => values['name'] === 'Valido' ? null : 'Nombre no valido.',submit });
    expect(editor.form.invalid).toBeTrue(); expect(fixture.nativeElement.textContent).toContain('Nombre no valido.');
    await editor.save(); expect(close).not.toHaveBeenCalled(); expect(submit).not.toHaveBeenCalled();
    editor.form.patchValue({ name:'Valido' }); expect(editor.form.valid).toBeTrue();
    await editor.save(); expect(submit).toHaveBeenCalledOnceWith({ name:'Valido' });
  });
  it('never renders server detail, validation input, SQL or a malicious request ID', () => {
    const issue = problem(new HttpErrorResponse({ status:422,error:{ detail:'SECRET-SQL',errors:[{ input:'SECRET-PASSWORD' }],request_id:'<script>bad</script>' } }));
    expect(JSON.stringify(issue)).not.toContain('SECRET'); expect(issue.requestId).toBeUndefined();
  });
  it('requires a department only for the roles that own operational work', () => {
    const { editor } = setup({ title:'Usuario',fields:[{ key:'role',label:'Rol',value:'admin' },{ key:'department_id',label:'Departamento',requiredWhen:{ key:'role',values:['lider','colaborador'] } }],submit:async () => ({}) });
    expect(editor.form.valid).toBeTrue(); editor.form.patchValue({ role:'lider' }); expect(editor.form.invalid).toBeTrue();
    editor.form.patchValue({ department_id:'synthetic-department' }); expect(editor.form.valid).toBeTrue();
    editor.form.patchValue({ role:'gerente',department_id:null }); expect(editor.form.valid).toBeTrue();
  });
  it('accepts leap day and rejects nonexistent and timestamp dates', () => {
    const { editor } = setup({ title:'Fecha',fields:[{ key:'due_date',label:'Fecha',type:'date',required:true }],submit:async () => ({}) });
    editor.form.patchValue({ due_date:'2028-02-29' }); expect(editor.form.valid).toBeTrue();
    editor.form.patchValue({ due_date:'2027-02-29' }); expect(editor.form.invalid).toBeTrue();
    editor.form.patchValue({ due_date:'2028-02-29T00:00:00Z' }); expect(editor.form.invalid).toBeTrue();
  });
  it('shows a sanitized request reference and does not close on 422', async () => {
    const { editor,fixture,close } = setup({ title:'Editar',fields:[],submit:async () => { throw new HttpErrorResponse({ status:422,error:{ code:'VALIDATION_ERROR',detail:'SECRET',request_id:'synthetic-request' } }); } });
    await editor.save(); fixture.detectChanges(); expect(close).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('synthetic-request'); expect(fixture.nativeElement.textContent).not.toContain('SECRET');
  });
});