import { inject, Injectable } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { firstValueFrom } from 'rxjs';
import { Api, Row, text, version } from '../core/api';
import { Editor, Field, options, reason } from '../shared/editor';

@Injectable({ providedIn: 'root' })
export class Transition {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  async open(row: Row, destination = ''): Promise<boolean | 'reload' | undefined> {
    const workflow = await this.api.get<{ stages: Row[]; transitions: Row[] }>('/catalogs/workflow');
    const destinations = new Set(workflow.transitions.filter(edge => edge['from_stage_id'] === row['stage_id']).map(edge => edge['to_stage_id']));
    const stages = workflow.stages.filter(stage => stage['is_active'] !== false && destinations.has(stage['id']));
    let target = stages.find(stage => stage['id'] === destination);
    if (destination && !target) throw new Error('Transition unavailable');
    if (!target) {
      const selected = await firstValueFrom(this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: {
        title: 'Seleccionar etapa', confirm: 'Continuar', fields: [{ key: 'to_stage_id', label: 'Etapa destino', type: 'select', required: true, options: options(stages) }],
        submit: async (values: Row) => { target = stages.find(stage => stage['id'] === values['to_stage_id']); },
      } }).afterClosed());
      if (selected !== true || !target) return;
    }
    const fields: Field[] = target['requires_reason'] ? [reason()] : [];
    if (target['requires_evidence']) {
      const files = await this.api.all('/tasks/' + text(row, 'id') + '/evidence');
      fields.push({ key: 'evidence_ids', label: 'Evidencias', type: 'multi', required: true, options: options(files, 'original_name') });
    }
    return firstValueFrom(this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: {
      title: 'Cambiar a ' + text(target, 'name'), fields,
      message: 'La tarea "' + text(row, 'title') + '" pasara a "' + text(target, 'name') + '".',
      submit: (values: Row) => this.api.command('/tasks/' + text(row, 'id') + '/stage-transitions', {
        ...values, expected_version: version(row), to_stage_id: target!['id'],
      }),
    } }).afterClosed());
  }
}