import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { FeedbackHostComponent } from './core/feedback/feedback-host.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, FeedbackHostComponent],
  template: '<router-outlet /><bea-feedback-host />',
})
export class App {}
