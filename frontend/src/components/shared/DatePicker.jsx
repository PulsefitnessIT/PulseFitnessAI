/**
 * DatePicker — DD/MM/YYYY calendar picker for the whole platform.
 *
 * Iter 216h193 — Lee's standardisation pass. Date input UX across the
 * platform was a mix of `<input type="date">` (browser-locale-dependent
 * display) and free-text fields (Craig's screenshot: "SLA Expiry Date"
 * placeholder). Both are inconsistent and error-prone.
 *
 * This component:
 *   • Shows the date as DD/MM/YYYY (UK convention) in a styled input.
 *   • Pops a Shadcn Calendar (react-day-picker) when clicked.
 *   • Round-trips the value as an ISO YYYY-MM-DD string so backend
 *     storage stays unambiguous (Mongo / Mongo's ISODate friendly).
 *   • Accepts an `onChange(iso)` callback returning the ISO string.
 *
 * Props mirror a normal Input so existing forms can swap straight in:
 *   <DatePicker value={form.warranty_expiry} onChange={(iso) => …} />
 */
import React, { useMemo, useState } from 'react';
import { Calendar as CalendarIcon, X } from 'lucide-react';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

function isoToDate(iso) {
  if (!iso || typeof iso !== 'string') return undefined;
  const m = iso.match(ISO_RE);
  if (!m) {
    // Tolerate ISO datetimes too (".slice(0, 10)" callers).
    const d = new Date(iso);
    return isNaN(d.getTime()) ? undefined : d;
  }
  // Use UTC noon to dodge timezone day-shift on day boundaries.
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12));
}

function dateToIso(d) {
  if (!d || !(d instanceof Date) || isNaN(d.getTime())) return '';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatDDMMYYYY(iso) {
  const d = isoToDate(iso);
  if (!d) return '';
  const day = String(d.getUTCDate()).padStart(2, '0');
  const mon = String(d.getUTCMonth() + 1).padStart(2, '0');
  const yr = d.getUTCFullYear();
  return `${day}/${mon}/${yr}`;
}

export default function DatePicker({
  value,
  onChange,
  placeholder = 'DD/MM/YYYY',
  className = '',
  inputClassName = '',
  disabled = false,
  clearable = true,
  minDate,
  maxDate,
  testid,
  ...rest
}) {
  const [open, setOpen] = useState(false);
  const display = useMemo(() => formatDDMMYYYY(value), [value]);
  const selected = useMemo(() => isoToDate(value), [value]);

  const handleSelect = (date) => {
    const iso = dateToIso(date);
    onChange?.(iso);
    if (iso) setOpen(false);
  };

  const handleClear = (e) => {
    e.stopPropagation();
    onChange?.('');
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            'w-full flex items-center justify-between px-3 py-2 text-sm rounded-md border bg-[var(--theme-input-bg,var(--theme-surface))] text-[var(--theme-text)] border-[var(--theme-border)] hover:bg-[var(--theme-surface-hover,var(--theme-surface))] transition-colors disabled:cursor-not-allowed disabled:opacity-50',
            inputClassName,
            className,
          )}
          data-testid={testid || 'datepicker-trigger'}
          aria-label={rest['aria-label']}
        >
          <span className={display ? '' : 'text-[var(--theme-text-muted)]'}>
            {display || placeholder}
          </span>
          <span className="flex items-center gap-1 ml-2">
            {clearable && display && !disabled && (
              <span
                role="button"
                tabIndex={-1}
                onClick={handleClear}
                className="p-0.5 rounded hover:bg-[var(--theme-border)]/40"
                aria-label="Clear date"
                data-testid={testid ? `${testid}-clear` : 'datepicker-clear'}
              >
                <X size={12} className="opacity-60" />
              </span>
            )}
            <CalendarIcon size={14} className="opacity-60" />
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-auto p-0 bg-[var(--theme-surface)] border-[var(--theme-border)]"
        data-testid={testid ? `${testid}-popover` : 'datepicker-popover'}
      >
        <Calendar
          mode="single"
          weekStartsOn={1}
          selected={selected}
          onSelect={handleSelect}
          defaultMonth={selected}
          disabled={(date) => {
            if (minDate && date < isoToDate(minDate)) return true;
            if (maxDate && date > isoToDate(maxDate)) return true;
            return false;
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

export { formatDDMMYYYY, dateToIso, isoToDate };
