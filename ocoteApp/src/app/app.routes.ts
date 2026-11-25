import { Routes } from '@angular/router';
import { permitted, signedIn } from './core/session';

export const routes: Routes = [
	{ path: 'login', loadComponent: () => import('./auth/auth.pages').then(module => module.LoginPage) },
	{ path: '', loadComponent: () => import('./shell').then(module => module.Shell), canActivate: [signedIn], children: [
		{ path: 'administracion/:section', loadComponent: () => import('./admin/admin.page').then(module => module.AdminPage), canActivate: [permitted], data: { permission: 'administration:manage' } },
		...['planes', 'objetivos'].flatMap(path => [
			{ path, loadComponent: () => import('./operations/planning.page').then(module => module.PlanningPage), canActivate: [permitted], data: { kind: path === 'planes' ? 'plans' : 'objectives', permissions: ['planning:manage', 'planning:department'] } },
			{ path: path + '/:id', loadComponent: () => import('./operations/planning.page').then(module => module.PlanningPage), canActivate: [permitted], data: { kind: path === 'planes' ? 'plans' : 'objectives', permissions: ['planning:manage', 'planning:department'] } },
		]),
		{ path: 'tareas', loadComponent: () => import('./operations/tasks.page').then(module => module.TasksPage) },
		{ path: 'tareas/:id', loadComponent: () => import('./operations/task-detail.page').then(module => module.TaskDetailPage) },
		{ path: 'analitica', loadComponent: () => import('./operations/analytics.page').then(module => module.AnalyticsPage), canActivate: [permitted], data: { permission: 'analytics:read' } },
		...['evaluaciones','evaluaciones/:id'].map(path => ({ path, loadComponent: () => import('./operations/evaluations.page').then(module => module.EvaluationsPage), canActivate: [permitted], data: { permission:'evaluations:read' } })),
		...['kanban','timeline'].map(view => ({ path:view,loadComponent:() => import('./operations/execution.page').then(module => module.ExecutionPage),data:{ view } })),
		...['solicitudes-fecha','solicitudes-fecha/:id'].map(path => ({ path, loadComponent: () => import('./operations/requests.page').then(module => module.RequestsPage), canActivate: [permitted], data: { permission:'date-requests:create' } })),
		{ path: 'perfil', loadComponent: () => import('./auth/auth.pages').then(module => module.ProfilePage) },
		{ path: 'sin-permiso', loadComponent: () => import('./shell').then(module => module.UnavailablePage) },
		{ path: '', pathMatch: 'full', redirectTo: 'tareas' },
		{ path: '**', loadComponent: () => import('./shell').then(module => module.UnavailablePage) },
	] },
];
