import { Directive, ElementRef, HostListener, inject, Input, OnInit, Renderer2, forwardRef } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { formatMontant, parseMontant } from './montant.pipe';

/**
 * Saisie monétaire FR : affichage avec séparateur de milliers + virgule.
 * La valeur du FormControl reste un ``number``.
 *
 * Usage : ``<input appMontantInput formControlName="valeur_brute" />``
 */
@Directive({
  selector: 'input[appMontantInput]',
  standalone: true,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => MontantInputDirective),
      multi: true,
    },
  ],
})
export class MontantInputDirective implements ControlValueAccessor, OnInit {
  private readonly el = inject(ElementRef<HTMLInputElement>);
  private readonly renderer = inject(Renderer2);

  @Input() fractionDigits = 2;

  private onChange: (value: number | null) => void = () => undefined;
  private onTouched: () => void = () => undefined;
  private disabled = false;

  ngOnInit(): void {
    this.renderer.setAttribute(this.el.nativeElement, 'inputmode', 'decimal');
    this.renderer.setAttribute(this.el.nativeElement, 'autocomplete', 'off');
    this.renderer.removeAttribute(this.el.nativeElement, 'type');
    this.renderer.setAttribute(this.el.nativeElement, 'type', 'text');
  }

  writeValue(value: number | string | null | undefined): void {
    const n = parseMontant(value);
    const display =
      n === null ? '' : formatMontant(n, this.fractionDigits).replace('—', '');
    this.renderer.setProperty(this.el.nativeElement, 'value', display === '—' ? '' : display);
  }

  registerOnChange(fn: (value: number | null) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled = isDisabled;
    this.renderer.setProperty(this.el.nativeElement, 'disabled', isDisabled);
  }

  @HostListener('input', ['$event'])
  onInput(event: Event): void {
    if (this.disabled) {
      return;
    }
    const raw = (event.target as HTMLInputElement).value;
    const n = parseMontant(raw);
    this.onChange(n);
  }

  @HostListener('blur')
  onBlur(): void {
    this.onTouched();
    const n = parseMontant(this.el.nativeElement.value);
    const display =
      n === null ? '' : formatMontant(n, this.fractionDigits).replace('—', '');
    this.renderer.setProperty(this.el.nativeElement, 'value', display === '—' ? '' : display);
    this.onChange(n);
  }

  @HostListener('focus')
  onFocus(): void {
    // Garde le format lisible à l'édition (espaces + virgule).
  }
}
