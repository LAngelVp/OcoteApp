import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export type Row = Record<string, unknown>;
export interface Page { items: Row[]; next_cursor?: string | null; }
export const text = (row: Row, key: string): string => String(row[key] ?? '');
export const version = (row: Row): number => Number(row['version']);

@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);
  get<T = Row>(path: string, query: Record<string, string> = {}): Promise<T> {
    return firstValueFrom(this.http.get<T>('/api/v1' + path, { params: new HttpParams({ fromObject: query }) }));
  }
  async all(path: string, query: Record<string, string> = {}): Promise<Row[]> {
    const rows: Row[] = [], seen = new Set<string>();
    let cursor = '';
    do {
      const page = await this.get<Page>(path, { ...query, limit: '100', ...(cursor ? { cursor } : {}) });
      rows.push(...page.items);
      cursor = page.next_cursor ?? '';
      if (cursor && seen.has(cursor)) throw new Error('Invalid pagination');
      seen.add(cursor);
    } while (cursor);
    return rows;
  }
  command<T = Row>(path: string, body: Row, method: 'POST' | 'PATCH' = 'POST'): Promise<T> {
    return firstValueFrom(this.http.request<T>(method, '/api/v1' + path, { body }));
  }
  upload(task: Row, file: File): Promise<Row> {
    return firstValueFrom(this.http.post<Row>('/api/v1/tasks/' + encodeURIComponent(text(task, 'id')) + '/evidence', file, {
      params: { expected_version: String(version(task)) },
      headers: { 'Content-Type': file.type, 'X-File-Name': encodeURIComponent(file.name) },
    }));
  }
  download(identity: string): Promise<Blob> {
    return firstValueFrom(this.http.get('/api/v1/evidence/' + encodeURIComponent(identity) + '/content', { responseType: 'blob' }));
  }
}