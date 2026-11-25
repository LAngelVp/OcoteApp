import { CdkDrag, CdkDragDrop, CdkDropList, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import { Component, ViewEncapsulation } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatButtonModule } from '@angular/material/button';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { By } from '@angular/platform-browser';
import type { ECharts, EChartsOption } from 'echarts';
import { NgxEchartsModule } from 'ngx-echarts';
import { Timeline } from 'vis-timeline/standalone';

@Component({
    imports: [MatButtonModule, DragDropModule, NgxEchartsModule],
    encapsulation: ViewEncapsulation.None,
    styleUrls: ['../../node_modules/vis-timeline/styles/vis-timeline-graph2d.min.css'],
    template: `
    <button mat-flat-button (click)="clicks = clicks + 1">Fixture F1</button>
    <div cdkDropList (cdkDropListDropped)="reorder($event)">
      @for (sample of samples; track sample) {
        <div cdkDrag>{{ sample }}</div>
      }
    </div>
    <div echarts style="width: 320px; height: 180px"
      [options]="options" [initOpts]="{ renderer: 'canvas', width: 320, height: 180 }"
      (chartInit)="onChartInit($event)"></div>
    <div class="f1-timeline" style="width: 480px; max-width: 100%; height: 180px"></div>
  `
})
class CompatibilityFixture {
  clicks = 0;
  samples = ['Synthetic A', 'Synthetic B'];
  resolveChart!: (chart: ECharts) => void;
  chartReady = new Promise<ECharts>((resolve) => this.resolveChart = resolve);
  options: EChartsOption = {
    animation: false,
    color: ['#B85A1E'],
    xAxis: { type: 'category', data: ['A', 'B'] },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: [2, 3] }],
  };

  onChartInit(chart: ECharts): void {
    this.resolveChart(chart);
  }

  reorder(event: CdkDragDrop<string[]>): void {
    moveItemInArray(this.samples, event.previousIndex, event.currentIndex);
  }
}

describe('F1 library compatibility (synthetic browser fixture only)', () => {
  let fixture: ComponentFixture<CompatibilityFixture>;
  let timeline: Timeline | undefined;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CompatibilityFixture, NgxEchartsModule.forRoot({ echarts: () => import('echarts') })],
      providers: [provideNoopAnimations()],
    }).compileComponents();
    fixture = TestBed.createComponent(CompatibilityFixture);
    fixture.detectChanges();
  });

  afterEach(() => {
    timeline?.destroy();
    timeline = undefined;
    fixture.destroy();
  });

  it('renders Material and wires CDK reordering without business data', () => {
    const button: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    button.click();
    expect(fixture.componentInstance.clicks).toBe(1);
    expect(button.classList.contains('mat-mdc-unelevated-button')).toBeTrue();
    expect(fixture.debugElement.queryAll(By.directive(CdkDrag)).length).toBe(2);
    const list = fixture.debugElement.query(By.directive(CdkDropList)).injector.get(CdkDropList);
    list.dropped.emit({ previousIndex: 0, currentIndex: 1 } as CdkDragDrop<string[]>);
    fixture.detectChanges();
    expect(fixture.componentInstance.samples).toEqual(['Synthetic B', 'Synthetic A']);
  });

  it('renders nonblank ECharts 6 canvas through ngx-echarts 18 and resizes it', async () => {
    const chart = await fixture.componentInstance.chartReady;
    await fixture.whenStable();
    chart.getZr().refreshImmediately();
    const canvas: HTMLCanvasElement = fixture.nativeElement.querySelector('canvas');
    expect(canvas).toBeTruthy();
    expect(canvas.width).toBeGreaterThan(0);
    const context = canvas.getContext('2d')!;
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    expect(pixels.some((channel, index) => index % 4 === 3 && channel !== 0)).toBeTrue();
    chart.resize({ width: 280, height: 160 });
    expect(chart.getWidth()).toBe(280);
    expect(chart.getHeight()).toBe(160);
    fixture.destroy();
    expect(chart.isDisposed()).toBeTrue();
  });

  it('renders vis-timeline with CSS, selects a synthetic item and changes the window', async () => {
    const container: HTMLElement = fixture.nativeElement.querySelector('.f1-timeline');
    timeline = new Timeline(container, [{
      id: 'synthetic', content: 'Fixture F1', start: '2026-01-02T12:00:00Z',
    }], {
      start: '2026-01-01T00:00:00Z', end: '2026-01-04T00:00:00Z',
      height: '180px', showCurrentTime: false, editable: false,
    });
    timeline.redraw();
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    timeline.setSelection(['synthetic']);
    expect(timeline.getSelection()).toEqual(['synthetic']);
    const item = container.querySelector('.vis-item.vis-box.vis-selected') as HTMLElement;
    expect(item.textContent).toContain('Fixture F1');
    expect(getComputedStyle(item).position).toBe('absolute');
    timeline.setWindow('2026-01-01T00:00:00Z', '2026-01-05T00:00:00Z', { animation: false });
    expect(timeline.getWindow().end.toISOString()).toBe('2026-01-05T00:00:00.000Z');
  });
});