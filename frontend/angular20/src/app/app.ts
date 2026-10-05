import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { FeedbackHostComponent } from './core/feedback/feedback-host.component';
import { ThemeService } from './core/services/theme.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, FeedbackHostComponent],
  template: '<router-outlet /><bea-feedback-host />',
})
export class App {
  constructor() {
    inject(ThemeService);
  }
}
