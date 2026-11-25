import { Component, inject, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Row, text, version } from '../core/api';
import { problem, Problem } from '../core/problem';
import { Editor, Field, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';

const justification = (): Field => ({ ...reason(), max: 1000 });
const purposes = ['backup', 'local_storage', 'clamav', 'jwt_signing', 'csrf', 'health_monitor'];

@Component({
  standalone: true,
  imports: [MatButtonModule, MatDialogModule, MatIconModule, MatTabsModule, MatTooltipModule, Feedback],
  styles: [`:host { display:block; min-width:0; } section { padding:24px 0; border-bottom:1px solid var(--ocote-border); }
    .provider-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
    h2 { font-size:1.25rem; margin:0 0 12px; } .facts dd { overflow-wrap:anywhere; }
    .table-wrap { max-width:100%; } .empty-state { padding:32px 12px; }`],
  template: `<header class="page-heading"><div><p class="eyebrow">ADMINISTRACION</p><h1>Salud y custodia</h1></div>
    <button mat-icon-button aria-label="Recargar salud" matTooltip="Recargar" [disabled]="loading()" (click)="load()"><mat-icon>refresh</mat-icon></button></header>
    <ocote-feedback [issue]="issue()" />@if (notice()) { <p class="notice" role="status">{{ notice() }}</p> }
    @if (loading()) { <p role="status">Consultando estado...</p> }
    @if (health(); as health) {
      <mat-tab-group animationDuration="0ms" [dynamicHeight]="false">
        <mat-tab label="Salud"><section><h2>Estado de instancia</h2><dl class="facts">
          <div><dt>Boveda</dt><dd>{{ health['vault_available'] ? 'Disponible' : 'No disponible' }}</dd></div>
          <div><dt>Custodia del cliente</dt><dd>{{ custody()?.['custody_complete'] ? 'Contactos completos' : 'Incompleta' }}</dd></div>
          <div><dt>Configuracion de evidencias</dt><dd>{{ health['evidence_configuration_verified'] ? 'Activa y verificada' : 'Cargas cerradas' }}</dd></div>
          <div><dt>Aceptacion operativa cliente</dt><dd>Pendiente</dd></div></dl></section>
        </mat-tab>
        <mat-tab label="Proveedores">@for (kind of kinds; track kind.code) { @let record = provider(kind.code);
          <section><div class="provider-heading"><h2>{{ kind.label }}</h2><div class="actions">
            <button mat-icon-button [attr.aria-label]="'Configurar ' + kind.label" matTooltip="Configurar" (click)="configure(kind.code, record)"><mat-icon>edit</mat-icon></button>
            <button mat-icon-button [attr.aria-label]="'Probar ' + kind.label" matTooltip="Probar" [disabled]="!record" (click)="test(record!)"><mat-icon>science</mat-icon></button>
            <button mat-icon-button [attr.aria-label]="'Cambiar activacion de ' + kind.label" matTooltip="Activacion" [disabled]="!record" (click)="activation(record!)"><mat-icon>power_settings_new</mat-icon></button>
          </div></div><dl class="facts"><div><dt>Estado</dt><dd>{{ record ? record['is_active'] ? 'Activo' : 'Inactivo' : 'Sin configurar' }}</dd></div>
          <div><dt>Revision de configuracion</dt><dd>{{ record?.['config_revision'] ?? '-' }}</dd></div>
          <div><dt>Revision probada</dt><dd>{{ record?.['tested_version'] ?? 'Sin prueba aprobada' }}</dd></div>
          <div><dt>Ultima comprobacion</dt><dd>{{ lastCheck(record) }}</dd></div>
          @if (record) { @for (entry of configuration(record); track entry[0]) { <div><dt>{{ entry[0] }}</dt><dd>{{ entry[1] }}</dd></div> } }
          </dl></section>
        }</mat-tab>
        <mat-tab label="Boveda"><section><div class="provider-heading"><h2>Secretos</h2><button mat-stroked-button [disabled]="!health['vault_available']" (click)="secret()"><mat-icon>add</mat-icon>Registrar</button></div>
          @if (!secrets().length) { <p>Sin secretos registrados.</p> } @else {
            <div class="table-wrap" role="region" aria-label="Metadatos de secretos" tabindex="0"><table class="data-table"><thead><tr><th>Titular UUID</th><th>Proposito</th><th>Version</th><th>Acciones</th></tr></thead><tbody>
              @for (row of secrets(); track row['owner_id'] + ':' + row['purpose']) { <tr><td>{{ row['owner_id'] }}</td><td>{{ row['purpose'] }}</td><td>{{ row['version'] }}</td><td><button mat-icon-button aria-label="Reemplazar secreto" matTooltip="Reemplazar" (click)="secret(row)"><mat-icon>key</mat-icon></button></td></tr> }
            </tbody></table></div>
          }
          @for (key of keys(); track key['purpose']) { <div class="provider-heading"><p>{{ key['purpose'] }} · Epoch {{ key['epoch'] }}</p><button mat-stroked-button (click)="rotate(key)"><mat-icon>autorenew</mat-icon>Rotar DEK</button></div> }
        </section></mat-tab>
        <mat-tab label="Custodia"><section><div class="provider-heading"><h2>Responsables del cliente</h2><button mat-icon-button aria-label="Editar custodia" matTooltip="Editar custodia" [disabled]="!custody()" (click)="editCustody()"><mat-icon>edit</mat-icon></button></div>
          <dl class="facts">@for (field of custodyFields; track field.key) { <div><dt>{{ field.label }}</dt><dd>{{ custody()?.[field.key] || 'Pendiente' }}</dd></div> }</dl>
        </section></mat-tab>
      </mat-tab-group>
    }`
})
export class PlatformPage implements OnInit {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  readonly health = signal<Row | null>(null);
  readonly secrets = signal<Row[]>([]);
  readonly keys = signal<Row[]>([]);
  readonly issue = signal<Problem | null>(null);
  readonly loading = signal(false);
  readonly notice = signal('');
  readonly kinds = [{ code: 'local_storage', label: 'Almacenamiento privado local' }, { code: 'clamav', label: 'ClamAV' }];
  readonly custodyFields: Field[] = [
    { key: 'primary_name', label: 'Nombre del titular', max: 160 },
    { key: 'primary_contact', label: 'Contacto del titular', max: 254 },
    { key: 'backup_name', label: 'Nombre del suplente', max: 160 },
    { key: 'backup_contact', label: 'Contacto del suplente', max: 254 },
  ];
  private epoch = 0;
  ngOnInit(): void { void this.load(); }
  custody(): Row | null { return this.health()?.['custody'] as Row | null; }
  provider(kind: string): Row | undefined { return (this.health()?.['integrations'] as Row[] | undefined)?.find(row => row['kind'] === kind); }
  configuration(row: Row): [string, unknown][] { return Object.entries(row['config'] as Row); }
  lastCheck(row?: Row): string { const check = row?.['last_check'] as Row | undefined; return check ? String(check['result_code']) : 'Pendiente'; }
  async load(): Promise<void> {
    const epoch = ++this.epoch;
    this.loading.set(true); this.issue.set(null);
    try {
      const [health, vault] = await Promise.all([this.api.get('/admin/health'), this.api.get('/admin/vault')]);
      if (epoch === this.epoch) { this.health.set(health); this.secrets.set(vault['items'] as Row[]); this.keys.set(vault['keys'] as Row[]); }
    } catch (error) { if (epoch === this.epoch) { this.health.set(null); this.issue.set(problem(error)); } }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  private open(title: string, fields: Field[], submit: (values: Row) => Promise<unknown>): void {
    this.notice.set('');
    this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: { title, fields: [...fields, justification()], submit } })
      .afterClosed().subscribe(result => { if (result) void this.load(); });
  }
  configure(kind: string, record?: Row): void {
    const config = record?.['config'] as Row | undefined;
    const fields: Field[] = kind === 'local_storage'
      ? [{ key: 'root', label: 'Directorio privado absoluto', required: true, max: 500 }]
      : [{ key: 'port', label: 'Puerto ClamAV loopback', type: 'number', required: true, min: 1, max: 65535 }, { key: 'timeout', label: 'Timeout (segundos)', type: 'number', required: true, min: 1, max: 8 }];
    this.open('Configurar ' + kind, fields.map(field => ({ ...field, value: config?.[field.key] })), values => {
      const config = Object.fromEntries(fields.map(field => [field.key, values[field.key]]));
      return this.api.command('/admin/integrations/' + kind, { config, expected_version: record ? version(record) : 0, reason: values['reason'] }, 'PUT');
    });
  }
  test(record: Row): void {
    this.open('Probar ' + text(record, 'kind'), [], async values => {
      const result = await this.api.command('/admin/integrations/' + text(record, 'kind') + '/test', { ...values, expected_version: version(record) });
      this.notice.set(result['passed'] ? 'Prueba aprobada. Proveedor inactivo.' : 'Prueba fallida. Proveedor inactivo.');
      return result;
    });
  }
  activation(record: Row): void {
    this.open('Activacion de ' + text(record, 'kind'), [{ key: 'is_active', label: 'Activo', type: 'check', value: record['is_active'] }],
      values => this.api.command('/admin/integrations/' + text(record, 'kind') + '/activation', { ...values, expected_version: version(record) }));
  }
  secret(record?: Row): void {
    const fields: Field[] = record ? [] : [
      { key: 'owner_id', label: 'Titular UUID', required: true, max: 36, pattern: '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' },
      { key: 'purpose', label: 'Proposito', type: 'select', required: true, options: purposes.map(value => ({ value, label: value })) },
    ];
    this.open(record ? 'Reemplazar secreto' : 'Registrar secreto', [...fields, { key: 'value', label: 'Nuevo secreto', type: 'password', required: true, min: 1, max: 16384 }], values =>
      this.api.command('/admin/vault/' + encodeURIComponent(String(record?.['owner_id'] ?? values['owner_id'])) + '/' + encodeURIComponent(String(record?.['purpose'] ?? values['purpose'])),
        { value: values['value'], reason: values['reason'], expected_version: record ? version(record) : 0 }, 'PUT'));
  }
  rotate(key: Row): void {
    this.open('Rotar clave de ' + text(key, 'purpose'), [], values => this.api.command('/admin/vault/rotate', { ...values, purpose: key['purpose'], expected_version: key['epoch'] }));
  }
  editCustody(): void {
    const record = this.custody(); if (!record) return;
    this.open('Custodia del cliente', this.custodyFields.map(field => ({ ...field, value: record[field.key] })), values => this.api.command('/admin/custody',
      { ...Object.fromEntries(this.custodyFields.map(field => [field.key, values[field.key] || null])), reason: values['reason'], expected_version: version(record) }, 'PATCH'));
  }
}