import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Row, text, version } from '../core/api';
import { BRAND_TOKENS, brandingContrast, Configuration, passesAA } from '../core/configuration';
import { problem, Problem } from '../core/problem';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';

const numberField = (key: string, label: string, min: number, max: number): Field => ({ key,label,type:'number',required:true,min,max });
const selectField = (key: string, label: string, values: string[]): Field => ({ key,label,type:'select',required:true,options:values.map(value => ({ value,label:value })) });

@Component({
  imports: [DecimalPipe, MatButtonModule, MatIconModule, MatTabsModule, MatTooltipModule, Feedback],
  styles: [`:host { display:block; min-width:0; } section { padding:24px 0; border-bottom:1px solid var(--ocote-border); }
    h2 { font-size:1.25rem; } .toolbar,.colors,.officials { display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
    .toolbar { justify-content:space-between; } .colors label { display:grid; gap:4px; font-size:.875rem; }
    input[type=color] { width:64px; height:40px; } input[type=file] { max-width:100%; }
    .preview { width:100%; max-width:320px; height:180px; object-fit:contain; } .officials img { width:120px; height:80px; object-fit:contain; }
    .sample { padding:16px; margin:16px 0; width:fit-content; max-width:100%; overflow-wrap:anywhere; border-radius:8px; }
    .ratios { display:flex; flex-wrap:wrap; gap:12px; } td,dd { overflow-wrap:anywhere; } .data-table { min-width:0; }
  `],
  template: `<header class="page-heading"><div><p class="eyebrow">ADMINISTRACION</p><h1>Configuracion institucional</h1></div><button mat-icon-button aria-label="Recargar configuracion" matTooltip="Recargar" (click)="load()" [disabled]="loading()"><mat-icon>refresh</mat-icon></button></header>
    <ocote-feedback [issue]="issue()" />@if (notice()) { <p role="status">{{ notice() }}</p> }
    @if (data(); as data) { <mat-tab-group animationDuration="0ms">
      <mat-tab label="Seguridad"><section><div class="toolbar"><h2>Politicas de acceso y limites</h2><button mat-stroked-button (click)="security()"><mat-icon>edit</mat-icon>Configurar</button></div>
        @if (data['security_policy']; as policy) { <dl class="facts">@for (field of policyFields; track field.key) { <div><dt>{{ field.label }}</dt><dd>{{ fieldValue(policy, field.key) }}</dd></div> }</dl> } @else { <p>Politica pendiente. Operacion cerrada.</p> }
      </section></mat-tab>
      <mat-tab label="Modulos"><section><h2>Disponibilidad</h2><table class="data-table"><thead><tr><th>Modulo</th><th>Estado</th><th></th></tr></thead><tbody>@for (module of modules(); track module['code']) { <tr><td>{{ module['code'] }}</td><td>{{ !module['installed'] ? 'No instalado' : module['enabled'] === null ? 'Sin configurar' : module['enabled'] ? 'Activo' : 'Inactivo' }}</td><td><button mat-icon-button aria-label="Configurar modulo" matTooltip="Configurar" [disabled]="!module['installed']" (click)="flag(module)"><mat-icon>tune</mat-icon></button></td></tr> }</tbody></table></section></mat-tab>
      <mat-tab label="Branding"><section><div class="toolbar"><h2>Identidad institucional</h2><div class="actions"><button mat-stroked-button (click)="branding()" [disabled]="!validAA()"><mat-icon>save</mat-icon>Guardar identidad</button><button mat-stroked-button (click)="reset()"><mat-icon>restart_alt</mat-icon>Restablecer OCOTE</button></div></div>
        <img class="preview" [src]="previewLogo() || runtime.logo() || '/logos/ocote-complete.webp'" (error)="imageError($event)" width="1200" height="660" alt="Vista previa institucional"><h3>{{ organizationName() || 'OCOTE' }}</h3>
        <div class="sample" [style.background]="palette()['primary']" [style.color]="palette()['on-primary']">{{ organizationName() || 'OCOTE' }}</div>
        <div class="colors">@for (token of colorTokens; track token) { <label>{{ token }}<input type="color" [value]="palette()[token]" (input)="color(token,$event)"></label> }</div>
        <div class="ratios" aria-live="polite">@for (entry of ratios(); track entry[0]) { <p>{{ entry[0] }}: {{ entry[1] | number:'1.2-2' }}:1</p> }</div>@if (!validAA()) { <p role="alert" class="problem">Contraste insuficiente: minimo 4.5:1 en todos los estados.</p> }
        <label>Logotipo PNG o JPEG<input type="file" accept="image/png,image/jpeg" (change)="uploadLogo($event)"></label>
        <h3>Identidad oficial de respaldo</h3><div class="officials"><img src="/logos/ocote-complete.webp" width="1200" height="660" alt="OCOTE completo"><img src="/logos/ocote-text.webp" width="1000" height="327" alt="OCOTE tipografico"><img src="/logos/ocote-icon.png" width="256" height="256" alt="OCOTE isotipo"></div>
      </section></mat-tab>
      <mat-tab label="Calendarios"><section><div class="toolbar"><h2>Jornadas y festivos</h2><button mat-stroked-button (click)="calendar()"><mat-icon>add</mat-icon>Calendario</button></div>@for (row of calendars(); track row['id']) { <div class="toolbar"><p>{{ row['name'] }} · {{ row['scope_kind'] }}</p><div class="actions"><button mat-icon-button aria-label="Editar calendario" matTooltip="Editar" (click)="calendar(row)"><mat-icon>edit</mat-icon></button><button mat-icon-button aria-label="Festivos" matTooltip="Festivos" (click)="selectCalendar(row)"><mat-icon>event</mat-icon></button></div></div> }
        @if (selectedCalendar()) { <h3>{{ selectedCalendar()?.['name'] }}</h3><label>Anio <input type="number" min="1900" max="9998" [value]="year()" (change)="changeYear($event)"></label><button mat-stroked-button (click)="holiday()"><mat-icon>add</mat-icon>Festivo</button>@for (row of holidays(); track row['id']) { <div class="toolbar"><p>{{ row['holiday_date'] }} · {{ row['name'] }} · {{ row['is_active'] ? 'Activo' : 'Inactivo' }}</p><button mat-icon-button aria-label="Editar festivo" matTooltip="Editar" (click)="holiday(row)"><mat-icon>edit</mat-icon></button></div> } }
        <button mat-stroked-button (click)="calculate()"><mat-icon>calculate</mat-icon>Calcular fecha</button><p role="status">{{ calculation() }}</p>
      </section></mat-tab>
      <mat-tab label="Almacenamiento externo"><section><div class="toolbar"><h2>Destinos privados</h2><div class="actions"><button mat-stroked-button (click)="provider('s3')"><mat-icon>add</mat-icon>S3 compatible</button><button mat-stroked-button (click)="provider('azure_blob')"><mat-icon>add</mat-icon>Azure Blob</button></div></div>@for (row of providers(); track row['id']) { <div class="toolbar"><p>{{ row['name'] }} · {{ row['provider'] }} · {{ row['is_active'] ? 'Activo' : 'Inactivo' }} · Revision {{ row['config_revision'] }} / probada {{ row['tested_version'] ?? '-' }}</p><div class="actions"><button mat-icon-button aria-label="Editar destino" matTooltip="Editar" (click)="provider(asText(row,'provider'),row)"><mat-icon>edit</mat-icon></button><button mat-icon-button aria-label="Probar destino" matTooltip="Probar" (click)="probe(row)"><mat-icon>science</mat-icon></button><button mat-icon-button aria-label="Activacion" matTooltip="Activacion" (click)="activation(row)"><mat-icon>power_settings_new</mat-icon></button></div></div> }</section></mat-tab>
    </mat-tab-group> }`
})
export class EnterprisePage implements OnInit {
  private readonly api=inject(Api); private readonly dialog=inject(MatDialog);
  readonly runtime=inject(Configuration); readonly data=signal<Row|null>(null); readonly loading=signal(false);
  readonly issue=signal<Problem|null>(null); readonly notice=signal(''); readonly calendars=signal<Row[]>([]);
  readonly providers=signal<Row[]>([]); readonly departments=signal<Row[]>([]); readonly holidays=signal<Row[]>([]);
  readonly selectedCalendar=signal<Row|null>(null); readonly year=signal(new Date().getUTCFullYear()); readonly calculation=signal('');
  readonly previewLogo=signal<string|null>(null); private pendingLogo: string|null=null;
  readonly palette=signal({...BRAND_TOKENS}); readonly colorTokens=Object.keys(BRAND_TOKENS);
  readonly ratios=computed(() => Object.entries(brandingContrast(this.palette()))); readonly validAA=computed(() => passesAA(brandingContrast(this.palette())));
  readonly modules=computed(() => this.data()?.['modules'] as Row[] ?? []); readonly asText=text;
  readonly policyFields: Field[]=[numberField('password_min_length','Longitud minima',12,64),
    ...[['require_upper','Mayusculas'],['require_lower','Minusculas'],['require_digit','Digitos'],['require_symbol','Simbolos']].map(([key,label]) => ({key,label,type:'check' as const})),
    numberField('access_ttl_seconds','Acceso (segundos)',60,600),numberField('refresh_absolute_seconds','Sesion absoluta (segundos)',3600,604800),numberField('idle_timeout_seconds','Inactividad (segundos)',60,3600),numberField('failed_attempt_threshold','Umbral de intentos',3,10),numberField('failed_window_seconds','Ventana de intentos (segundos)',60,900),numberField('lockout_seconds','Bloqueo (segundos)',60,3600),
    {key:'page_sizes',label:'Tamanos de pagina',type:'multi',required:true,options:[5,10,20,50].map(size => ({value:String(size),label:String(size)}))},
    numberField('import_max_rows','Filas de importacion',1,1000),numberField('import_max_bytes','Bytes de importacion',1,10485760),numberField('export_max_bytes','Bytes de exportacion',1,16777216)];
  constructor() { inject(DestroyRef).onDestroy(() => this.clearPreview()); }
  ngOnInit(): void { void this.load(); }
  fieldValue(row: unknown,key: string): string { const value=(row as Row)[key]; return Array.isArray(value)?value.join(', '):typeof value==='boolean'?value?'Si':'No':String(value); }
  private brand(): Row { return this.data()?.['branding'] as Row ?? {}; }
  organizationName(): string { return text(this.brand(),'organization_name'); }
  async load(): Promise<void> {
    this.loading.set(true); this.issue.set(null);
    try { const data=await this.api.get('/admin/configuration'); this.data.set(data); this.palette.set({...BRAND_TOKENS,...this.brand()['token_overrides'] as Record<string,string>});
      if(data['security_policy']) { const [calendars,providers,departments]=await Promise.all([this.api.all('/admin/calendars'),this.api.all('/admin/object-storage'),this.api.all('/departments')]); this.calendars.set(calendars);this.providers.set(providers);this.departments.set(departments); }
      await this.runtime.reload();
    } catch(error) { this.issue.set(problem(error)); } finally { this.loading.set(false); }
  }
  private open(title: string,fields: Field[],submit: (values: Row)=>Promise<unknown>,validate?: (values: Row)=>string|null): void {
    this.dialog.open(Editor,{width:'720px',maxWidth:'96vw',data:{title,fields:[...fields,{key:'current_password',label:'Contrasena actual',type:'password',required:true,min:1,max:128},{...reason(),max:1000}],submit,validate}}).afterClosed().subscribe(result => {if(result) void this.load();});
  }
  security(): void { const record=this.data()?.['security_policy'] as Row|null;
    this.open('Politicas de seguridad',this.policyFields.map(field => ({...field,value:field.key==='page_sizes'?(record?.[field.key] as number[]|undefined)?.map(String):record?.[field.key]})),values => this.api.command('/admin/security-policy',{current_password:values['current_password'],reason:values['reason'],expected_version:record?version(record):0,values:Object.fromEntries(this.policyFields.map(field => [field.key,field.key==='page_sizes'?(values[field.key] as string[]).map(Number):values[field.key]]))},'PUT'),values => (values['page_sizes'] as string[]).includes('5')?null:'El tamano minimo 5 es obligatorio.');
  }
  flag(record: Row): void { this.open('Disponibilidad de '+text(record,'code'),[{key:'enabled',label:'Activo',type:'check',value:record['enabled']===true}],values => this.api.command('/admin/feature-flags',{...values,code:record['code'],expected_version:record['version']??0},'PUT')); }
  color(token: string,event: Event): void { this.palette.update(palette => ({...palette,[token]:(event.target as HTMLInputElement).value})); }
  branding(): void { const record=this.brand(); if(!this.validAA()) return;
    this.open('Identidad institucional',[{key:'organization_name',label:'Nombre institucional',required:true,max:160,value:record['organization_name']},{key:'welcome_text',label:'Bienvenida',type:'textarea',max:500,value:record['welcome_text']},{key:'footer_text',label:'Pie institucional',type:'textarea',max:500,value:record['footer_text']}],async values => {const result=await this.api.command('/admin/branding',{...values,welcome_text:values['welcome_text']||'',footer_text:values['footer_text']||'',token_overrides:this.palette(),logo_asset_id:this.pendingLogo??record['logo_asset_id']??null,organization_name_version:record['organization_name_version'],expected_version:record['version']},'PUT');this.pendingLogo=null;this.clearPreview();return result;},()=>this.validAA()?null:'Contraste insuficiente.');
  }
  reset(): void { const record=this.brand();this.open('Restablecer OCOTE',[],async values => {const result=await this.api.command('/admin/branding/reset',{...values,expected_version:record['version'],organization_name_version:record['organization_name_version']});this.pendingLogo=null;this.clearPreview();return result;}); }
  private clearPreview(): void {const current=this.previewLogo();if(current)URL.revokeObjectURL(current);this.previewLogo.set(null);}
  imageError(event: Event): void {const image=event.target as HTMLImageElement;if(!image.src.endsWith('/logos/ocote-complete.webp'))image.src='/logos/ocote-complete.webp';}
  uploadLogo(event: Event): void {const input=event.target as HTMLInputElement,file=input.files?.[0];input.value='';if(!file)return;
    if(!['image/png','image/jpeg'].includes(file.type)||file.size>1048576){this.notice.set('Logo rechazado: PNG/JPEG de hasta 1 MiB.');return;}
    this.open('Registrar logotipo privado',[],async values => {let binary='';for(const byte of new Uint8Array(await file.arrayBuffer()))binary+=String.fromCharCode(byte);const row=await this.api.command('/admin/branding/logo',{...values,expected_version:this.brand()['version'],media_type:file.type,content:btoa(binary)});const identity=text(row,'id'),blob=await this.api.logo(identity);this.clearPreview();this.pendingLogo=identity;this.previewLogo.set(URL.createObjectURL(blob));return row;});
  }
  private scope(record?: Row): Field[] {return [selectField('scope_kind','Alcance',['organization','department']),{key:'department_id',label:'Departamento',type:'select' as const,options:options(this.departments()),requiredWhen:{key:'scope_kind',values:['department']}}].map(field=>({...field,value:record?.[field.key]}));}
  calendar(record?: Row): void {
    const fields: Field[]=[{key:'name',label:'Nombre',required:true,max:120},...this.scope(record),selectField('inheritance','Herencia',['inherit','replace']),{key:'weekdays',label:'Dias laborales',type:'multi',required:true,options:['Lunes','Martes','Miercoles','Jueves','Viernes','Sabado','Domingo'].map((label,index)=>({value:String(index),label})),value:record?[0,1,2,3,4,5,6].filter(index=>Number(record['weekday_mask'])&(1<<index)).map(String):[]}];
    this.open(record?'Editar calendario':'Crear calendario',fields.map(field=>({...field,value:field.value??record?.[field.key]})),values=>{const {weekdays,...body}=values;return this.api.command('/admin/calendars'+(record?'/'+text(record,'id'):''),{...body,department_id:body['scope_kind']==='organization'?null:body['department_id'],weekday_mask:(weekdays as string[]).reduce((mask,day)=>mask|(1<<Number(day)),0),expected_version:record?version(record):0},record?'PUT':'POST');});
  }
  async selectCalendar(record: Row): Promise<void> {
    this.selectedCalendar.set(record);this.issue.set(null);
    try {this.holidays.set(await this.api.all('/admin/calendars/'+text(record,'id')+'/holidays',{year:String(this.year())}));} catch(error){this.issue.set(problem(error));}
  }
  changeYear(event: Event): void {const year=Number((event.target as HTMLInputElement).value);if(Number.isInteger(year)&&year>=1900&&year<=9998){this.year.set(year);const record=this.selectedCalendar();if(record)void this.selectCalendar(record);}}
  holiday(record?: Row): void {
    const calendar=this.selectedCalendar();if(!calendar)return;
    this.open(record?'Editar festivo':'Crear festivo',[...(!record?[{key:'holiday_date',label:'Fecha civil',type:'date' as const,required:true}]:[]),{key:'name',label:'Nombre',required:true,max:120,value:record?.['name']},{key:'is_active',label:'Activo',type:'check',value:record?.['is_active']}],async values=>{const result=await this.api.command('/admin/calendars/'+text(calendar,'id')+'/holidays'+(record?'/'+text(record,'id'):''),{...values,holiday_date:record?.['holiday_date']??values['holiday_date'],expected_version:record?version(record):0},record?'PUT':'POST');await this.selectCalendar(calendar);return result;});
  }
  calculate(): void {
    this.open('Calcular fecha',[{key:'department_id',label:'Departamento',type:'select',options:options(this.departments())},{key:'start_date',label:'Fecha inicial',type:'date',required:true},numberField('days','Dias de desplazamiento',0,365),selectField('mode','Computo',['natural','business'])],async values=>{const result=await this.api.command('/admin/calendar-preview',{department_id:values['department_id']??null,start_date:values['start_date'],days:values['days'],mode:values['mode']});this.calculation.set('Fecha resultante: '+String(result['date']));return result;});
  }
  provider(kind: string,record?: Row): void {
    const config=record?.['config'] as Row|undefined;
    const fields: Field[]=[{key:'name',label:'Nombre del destino',required:true,max:120},...this.scope(record),{key:'endpoint',label:'Endpoint HTTPS',required:true,max:2048},{key:'isolation_prefix',label:'Prefijo privado aislado',required:true,max:200},{key:'approved_addresses',label:'Direcciones IP aprobadas',type:'textarea',required:true,max:1600,value:(config?.['approved_addresses'] as string[]|undefined)?.join('\n')},{key:'allow_private_endpoint',label:'Endpoint privado aprobado',type:'check'},{key:'private_access_attested',label:'Destino privado confirmado',type:'check'},numberField('connect_timeout_seconds','Timeout conexion (s)',1,10),numberField('read_timeout_seconds','Timeout lectura (s)',1,30),numberField('evidence_max_bytes','Limite de evidencia (bytes)',1,10485760),{key:'allowed_mime',label:'Tipos MIME',type:'multi',required:true,options:['application/pdf','image/png','image/jpeg'].map(value=>({value,label:value}))}];
    if(kind==='s3')fields.push({key:'bucket',label:'Bucket',required:true,max:63},{key:'region',label:'Region',required:true,max:64},selectField('address_style','Estilo de direccion',['path','virtual_hosted']),{key:'access_key',label:'Nueva access key',type:'password',required:!record,max:128},{key:'secret_key',label:'Nueva secret key',type:'password',required:!record,max:256},{key:'session_token',label:'Nuevo session token',type:'password',max:16384});
    else fields.push({key:'container',label:'Contenedor',required:true,max:63},{key:'account_name',label:'Cuenta Azure',required:true,max:24},selectField('auth','Autenticacion',['shared_key']),{key:'account_key',label:'Nueva clave de cuenta',type:'password',required:!record,max:512});
    this.open(record?'Editar destino privado':'Crear destino privado',fields.map(field=>({...field,value:field.type==='password'?undefined:field.value??config?.[field.key]??record?.[field.key]})),values=>{
      const {name,scope_kind,department_id,reason,current_password,access_key,secret_key,session_token,account_key,...settings}=values;
      const credentials=kind==='s3'?access_key||secret_key||session_token?{access_key,secret_key,session_token:session_token||null}:null:account_key?{account_key}:null;
      return this.api.command('/admin/object-storage'+(record?'/'+text(record,'id'):''),{name,scope_kind,department_id:scope_kind==='organization'?null:department_id,reason,current_password,expected_version:record?version(record):0,config:{...settings,provider:kind,retention_days:null,approved_addresses:String(settings['approved_addresses']).split(/[\s,]+/).filter(Boolean)},...(credentials?{credentials}:{})},record?'PUT':'POST');
    });
  }
  probe(record: Row): void {this.open('Probar destino privado',[],async values=>{const result=await this.api.command('/admin/object-storage/'+text(record,'id')+'/test',{...values,expected_version:version(record)});this.notice.set(result['passed']?'Prueba aprobada. Destino inactivo.':'Prueba fallida. Destino inactivo.');return result;});}
  activation(record: Row): void {this.open('Activacion de destino privado',[{key:'is_active',label:'Activo',type:'check',value:record['is_active']}],values=>this.api.command('/admin/object-storage/'+text(record,'id')+'/activation',{...values,expected_version:version(record)}));}
}