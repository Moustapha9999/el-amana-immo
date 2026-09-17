import { Routes } from '@angular/router';
import { authGuard } from '../core/guards/auth.guard';
import { AccueilComponent } from './accueil/accueil.component';
import { ComptabiliteComponent } from './comptabilite/comptabilite.component';

export const PLATEFORME_ROUTES: Routes = [
  { path: 'accueil', component: AccueilComponent, canActivate: [authGuard] },
  { path: 'comptabilite', component: ComptabiliteComponent, canActivate: [authGuard] },
];
