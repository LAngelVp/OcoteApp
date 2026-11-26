import { FormControl } from '@angular/forms';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { MatDialog } from '@angular/material/dialog';
import { of } from 'rxjs';
import { Api, Row } from './core/api';
import { Configuration } from './core/configuration';
import { Session } from './core/session';
import { decimalValidator, decimalValue, integerValidator } from './shared/editor';
import { Collaboration, commentPayload, metadataChanges, metadataFields, metadataPayload } from './operations/collaboration';
import { Search } from './operations/search';

describe('F9 typed metadata', () => {
  it('preserves selected mentions and adds only their missing literal names', () => {
    const readers = [{ id: 'reader', display_name: 'Synthetic reader' }];
    expect(commentPayload('<b>literal</b>', ['reader'], readers)).toEqual({ body: '<b>literal</b>\n@Synthetic reader', mention_ids: ['reader'] });
    expect(commentPayload('Hello @Synthetic reader', ['reader'], readers)['body']).toBe('Hello @Synthetic reader');
    expect(commentPayload('Plain', [], readers)).toEqual({ body: 'Plain', mention_ids: [] });
  });
  it('does not request the custom-fields module for tags-only creation', () => {
    expect(metadataPayload({ tag_ids: ['tag'] }, [{ key: 'tag_ids', label: 'Tags', type: 'multi' }])).toEqual({ tag_ids: ['tag'] });
    expect(metadataPayload({}, [])).toEqual({});
    expect(metadataPayload({ empty: [] }, [{ key: 'empty', label: 'Optional', type: 'multi' }])).toEqual({ custom_fields: {} });
  });
  it('clears empty selections with null and stores an explicitly confirmed false', () => {
    expect(metadataChanges({ empty: [], flag: false, number: 0 }, [
      { key: 'empty', label: 'Selection', type: 'multi', value: ['old'] },
      { key: 'flag', label: 'Flag', type: 'check' },
      { key: 'number', label: 'Number', type: 'decimal', value: 0 },
    ])).toEqual({ empty: null, flag: false });
  });
  it('marks creation and stage requirements independently', () => {
    const schema = { fields: [{ id: 'value', label: 'Required', data_type: 'text', active: true,
      required_on_create: true, required_stage_ids: ['final'] }] };
    expect(metadataFields(schema, true)[0].required).toBeTrue();
    expect(metadataFields(schema, false, 'final')[0].required).toBeTrue();
    expect(metadataFields(schema, false, 'other')[0].required).toBeFalse();
  });
  it('keeps false and zero in creation payload instead of dropping explicit values', () => {
    expect(metadataPayload({ flag: false, number: 0, optional: null }, [
      { key: 'flag', label: 'Flag' }, { key: 'number', label: 'Number' }, { key: 'optional', label: 'Optional' },
    ])).toEqual({ custom_fields: { flag: false, number: 0 } });
  });
  it('uses typed controls and preserves false and zero without HTML rendering', () => {
    const fields = metadataFields({ fields: [
      { id: 'flag', label: '<b>literal</b>', data_type: 'boolean', active: true },
      { id: 'amount', label: 'Amount', data_type: 'number', active: true },
    ], values: [{ definition_id: 'flag', value: false }, { definition_id: 'amount', value: 0 }] });
    expect(fields[0].type).toBe('check'); expect(fields[0].value).toBeFalse();
    expect(fields[1].type).toBe('decimal'); expect(fields[1].value).toBe(0);
    expect(fields[0].label).toContain('<b>literal</b>');
  });
  it('accepts finite numeric(18,4) without weakening integer controls', () => {
    expect(decimalValue('12.1250')).toBe(12.125);
    expect(decimalValidator(new FormControl(12.125))).toBeNull();
    expect(integerValidator(new FormControl(12.125))).not.toBeNull();
    for (const value of [true, 'NaN', Infinity, 1.12345, 0.00001, 100000000000000]) {
      expect(decimalValidator(new FormControl(value))).not.toBeNull();
    }
  });
});

describe('F9 collaboration access and plaintext', () => {
  async function render(enabled: boolean) {
    const calls: string[] = [];
    const fixture = TestBed.configureTestingModule({ imports: [Collaboration], providers: [
      provideRouter([]),
      { provide: Configuration, useValue: { value: signal<Row | null>({}), enabled: () => enabled } },
      { provide: Session, useValue: { user: () => ({ id: 'assigned', role: 'colaborador' }), has: () => false } },
      { provide: Api, useValue: { get: async (path: string) => {
        calls.push(path);
        if (path.endsWith('/metadata')) return { fields: [], values: [], tags: [], tag_ids: [], resource_version: 1 };
        if (path.endsWith('/revisions')) return { items: [{ id: 'revision', revision_no: 1, body: '<b>Revision previa literal</b>', reason: 'Synthetic reason' }], next_cursor: null };
        return { items: path.endsWith('/comments') ? [{ id: 'comment', current_revision: 1,
          body: '<img src=x onerror=alert(1)>literal', annulled_at: null, can_edit: false }] : [], next_cursor: null, plan_version: 1 };
      } } },
    ] }).createComponent(Collaboration);
    fixture.componentRef.setInput('record', { id: 'task', version: 1, title: 'Assigned task' });
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    return { fixture, calls };
  }
  it('makes no F9 requests when its modules are disabled', async () => {
    const { fixture, calls } = await render(false);
    expect(calls).toEqual([]);
    expect(fixture.nativeElement.textContent).not.toContain('Agregar predecesora');
  });
  it('renders comments literally and never exposes dependency management to C', async () => {
    const { fixture } = await render(true);
    expect(fixture.nativeElement.textContent).toContain('<img src=x onerror=alert(1)>literal');
    expect(fixture.nativeElement.querySelector('.body img')).toBeNull();
    const text = fixture.nativeElement.textContent;
    expect(text).not.toContain('Editar valores');
    expect(text).not.toContain('Predecesora');
    expect(text).toContain('Abrir impedimento');
  });
  it('reads revisions without interpreting historical markup', async () => {
    const { fixture, calls } = await render(true);
    await fixture.componentInstance.showRevisions({ id: 'comment' }); fixture.detectChanges();
    expect(calls).toContain('/collaboration/task/task/comments/comment/revisions');
    expect(fixture.nativeElement.textContent).toContain('<b>Revision previa literal</b>');
    expect(fixture.nativeElement.querySelector('[aria-label="Revisiones del comentario"] b')).toBeNull();
  });
});

describe('F9 saved views', () => {
  it('archives stored filters rather than overwriting them with the current search', async () => {
    let submit: (values: Row) => Promise<unknown> = async () => undefined;
    const command = jasmine.createSpy('command').and.resolveTo({});
    const fixture = TestBed.configureTestingModule({ imports: [Search], providers: [provideRouter([]),
      { provide: Configuration, useValue: { enabled: () => false } },
      { provide: Session, useValue: { user: () => ({ id: 'author', role: 'admin' }) } },
      { provide: Api, useValue: { command } },
      { provide: MatDialog, useValue: { open: (_component: unknown, config: { data: { submit: typeof submit } }) => {
        submit = config.data.submit; return { afterClosed: () => of(false) };
      } } },
    ] }).createComponent(Search);
    const view = { id: 'view', name: 'Stored', version: 3, entity_type: 'objective', scope_kind: 'personal', department_id: null, filters: { q: 'stored', entity_type: 'objective' } };
    fixture.componentInstance.query.set('different');
    await fixture.componentInstance.save(view, true);
    await submit({ reason: 'Synthetic archive operation' });
    expect(command.calls.mostRecent().args[1].filters).toEqual(view.filters);
    expect(command.calls.mostRecent().args[1].active).toBeFalse();
  });
});