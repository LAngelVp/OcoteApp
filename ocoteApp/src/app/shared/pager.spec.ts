import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Pager, Pagination } from './pager';

describe('Cursor pagination', () => {
  it('starts at five rows and tracks forward, previous and first without guessing totals', () => {
    const state = new Pagination();
    expect(state.size()).toBe(5); expect(state.number()).toBe(1); expect(state.previous()).toBeNull();
    state.accept('', 'second'); state.accept('second', 'third'); state.accept('third', 'fourth');
    expect(state.number()).toBe(3); expect(state.previous()).toBe('second');
    state.accept('second', 'third'); expect(state.number()).toBe(2); expect(state.previous()).toBe('');
    state.accept('', 'second'); expect(state.number()).toBe(1); expect(state.previous()).toBeNull();
  });
  it('clears every old cursor on a valid size change and rejects unsupported sizes', () => {
    const state = new Pagination(); state.accept('', 'second'); state.accept('second', 'third');
    expect(state.resize(7)).toBeFalse(); expect(state.cursor()).toBe('second');
    expect(state.resize(20)).toBeTrue(); expect(state.size()).toBe(20);
    expect(state.cursor()).toBe(''); expect(state.next()).toBeNull(); expect(state.previous()).toBeNull(); expect(state.number()).toBe(1);
    expect(state.resize(20)).toBeFalse(); expect(state.resize(NaN)).toBeFalse();
  });
  it('keeps the previous cursor when the current page is refreshed', () => {
    const state = new Pagination(); state.accept('', 'second'); state.accept('second', 'third'); state.accept('second', null);
    expect(state.number()).toBe(2); expect(state.previous()).toBe(''); expect(state.next()).toBeNull();
  });
  it('renders accessible controls, emits cursors and disables navigation while busy', async () => {
    await TestBed.configureTestingModule({ imports:[Pager],providers:[provideNoopAnimations()] }).compileComponents();
    const fixture = TestBed.createComponent(Pager), state = new Pagination(), requested: string[] = [];
    state.accept('', 'second'); fixture.componentRef.setInput('state',state);
    fixture.componentInstance.navigate.subscribe(cursor => requested.push(cursor)); fixture.detectChanges();
    const buttons = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
    expect(buttons[0].disabled).toBeTrue(); expect(buttons[1].disabled).toBeTrue(); expect(buttons[2].disabled).toBeFalse();
    buttons[2].click(); expect(requested).toEqual(['second']);
    fixture.componentRef.setInput('busy',true); fixture.detectChanges();
    expect(Array.from(buttons).every(button => button.disabled)).toBeTrue();
    expect(fixture.nativeElement.querySelector('mat-select').getAttribute('aria-disabled')).toBe('true');
    expect(fixture.nativeElement.textContent).toContain('Filas por p\u00e1gina');
  });
});