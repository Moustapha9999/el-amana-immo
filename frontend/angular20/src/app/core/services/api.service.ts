import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  readonly baseUrl = environment.apiUrl;

  get<T>(path: string, params?: Record<string, string | number>): Observable<T> {
    return this.http.get<T>(`${this.baseUrl}${path}`, { params: params as Record<string, string> });
  }

  post<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(`${this.baseUrl}${path}`, body);
  }

  patch<T>(path: string, body: unknown): Observable<T> {
    return this.http.patch<T>(`${this.baseUrl}${path}`, body);
  }

  put<T>(path: string, body: unknown): Observable<T> {
    return this.http.put<T>(`${this.baseUrl}${path}`, body);
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(`${this.baseUrl}${path}`);
  }

  download(path: string, params?: Record<string, string>): Observable<Blob> {
    return this.http.get(`${this.baseUrl}${path}`, {
      params,
      responseType: 'blob',
    });
  }

  upload<T>(path: string, file: File, fields?: Record<string, string>): Observable<T> {
    const form = new FormData();
    form.append('file', file);
    if (fields) {
      for (const [key, value] of Object.entries(fields)) {
        if (value != null && value !== '') {
          form.append(key, value);
        }
      }
    }
    return this.http.post<T>(`${this.baseUrl}${path}`, form);
  }
}
