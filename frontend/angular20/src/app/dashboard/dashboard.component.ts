import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { PageHeaderComponent } from '../shared/page-header.component';
import { ParcChartsPanelComponent } from './parc-charts-panel.component';

@Component({
  selector: 'app-dashboard',
  imports: [MatIconModule, MatButtonModule, PageHeaderComponent, ParcChartsPanelComponent],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {}
