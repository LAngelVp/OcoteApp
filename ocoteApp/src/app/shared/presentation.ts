import { Row } from '../core/api';

const labels: Record<string, string> = {
  annual: 'Anual', semiannual: 'Semestral', quarterly: 'Trimestral', monthly: 'Mensual', custom: 'Personalizado',
  draft: 'Borrador', active: 'Activo', closed: 'Cerrado', open: 'Abierta', blocked: 'Bloqueada', completed: 'Completada',
  pending: 'Pendiente', on_time: 'A tiempo', late: 'Con retraso', overdue: 'Vencida',
  approved: 'Aprobada', rejected: 'Rechazada', cancelled: 'Cancelada', succeeded: 'Correcta', failed: 'Fallida',
};
export const label = (value: unknown): string => labels[String(value)] ?? String(value ?? 'Sin datos');
export const nested = (row: Row, key: string): Row => row[key] && typeof row[key] === 'object' && !Array.isArray(row[key]) ? row[key] as Row : {};
export function instant(value: unknown): string {
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value))) return '—';
  return new Intl.DateTimeFormat('es-MX', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Mexico_City' }).format(new Date(value));
}
export const progress = (value: unknown): string => typeof value === 'number' ? value.toLocaleString('es-MX', { maximumFractionDigits: 2 }) + '%' : 'Sin datos';