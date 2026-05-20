/**
 * DatePicker — DD/MM/YYYY hybrid input + calendar picker for the whole platform.
 *
 * Iter 216h193 — Lee's standardisation pass. Date input UX across the
 * platform was a mix of `<input type="date">` (browser-locale-dependent
 * display) and free-text fields (Craig's screenshot: "SLA Expiry Date"
 * placeholder). Both are inconsistent and error-prone.
 *
 * Iter 216h241 — Hybrid input mode. Previous version was button-only
 * which forced 3 clicks (year nav → month nav → day) for dates of
 * birth. Now the trigger is a real `<input>` that accepts typed
 * DD/MM/YYYY (forgiving: D/M/YYYY, D-M-YYYY, DDMMYYYY also parse) and
 * the calendar icon next to it still opens the popover.
 *
 * This component:
 *   • Shows the date as DD/MM/YYYY (UK convention) in a styled input.
 *   • Accepts typed input (parses to ISO on blur / Enter).
 *   • Opens a Shadcn Calendar (react-day-picker) via the calendar icon.
 *   • Round-trips the value as an ISO YYYY-MM-DD string so backend
 *     storage stays unambiguous (Mongo / Mongo's ISODate friendly).
 *   • Accepts an `onChange(iso)` callback returning the ISO string.
 *
 * Props mirror a normal Input so existing forms can swap straight in:
 *   <DatePicker value={form.warranty_expiry} onChange={(iso) => …} />
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Calendar as CalendarIcon, X } from 'lucide-react';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
// Iter 216h241 — accept common UK typed shapes: 27/10/1986, 27-10-1986,
// 27.10.1986, 27101986. Pad single-digit day/month so "1/4/2026" parses.
const TYPED_RE = /^(\d{1,2})[/.\-\s]?(\d{1,2})[/.\-\s]?(\d{2,4})$/;

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

// Iter 216h241 — parse a typed DD/MM/YYYY string into an ISO date.
// Returns '' for unparseable input. 2-digit years map to 19xx if ≥ 50,
// otherwise 20xx (so DOBs in the 1900s still work).
function parseTypedDate(raw) {
  if (!raw || typeof raw !== 'string') return '';
  const m = raw.trim().match(TYPED_RE);
  if (!m) return '';
  const day = Number(m[1]);
  const mon = Number(m[2]);
  let yr  = Number(m[3]);
  if (m[3].length === 2) yr = yr >= 50 ? 1900 + yr : 2000 + yr;
  if (m[3].length === 3) yr = 1000 + yr;  // permissive, unlikely
  if (day < 1 || day > 31 || mon < 1 || mon > 12 || yr < 1900 || yr > 2200) return '';
  // Round-trip through Date to catch e.g. 31/02/2026.
  const d = new Date(Date.UTC(yr, mon - 1, day, 12));
  if (d.getUTCFullYear() !== yr || d.getUTCMonth() !== mon - 1 || d.getUTCDate() !== day) return '';
  return dateToIso(d);
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
  const [draft, setDraft] = useState(() => formatDDMMYYYY(value));
  const inputRef = useRef(null);
  const display = useMemo(() => formatDDMMYYYY(value), [value]);
  const selected = useMemo(() => isoToDate(value), [value]);

  // Keep typed draft in sync when the parent value changes externally.
  useEffect(() => { setDraft(formatDDMMYYYY(value)); }, [value]);

  const commitDraft = () => {
    const iso = parseTypedDate(draft);
    if (iso) {
      onChange?.(iso);
      setDraft(formatDDMMYYYY(iso));
    } else if (!draft.trim()) {
      onChange?.('');
    } else {
      // Reset to last valid value if the typed text is unparseable.
      setDraft(formatDDMMYYYY(value));
    }
  };

  const handleSelect = (date) => {
    const iso = dateToIso(date);
    onChange?.(iso);
    setDraft(formatDDMMYYYY(iso));
    if (iso) setOpen(false);
  };

  const handleClear = (e) => {
    e.stopPropagation();
    onChange?.('');
    setDraft('');
    inputRef.current?.focus();
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <div
        className={cn(
          'w-full flex items-center px-2 py-1 text-sm rounded-md border bg-[var(--theme-input-bg,var(--theme-surface))] text-[var(--theme-text)] border-[var(--theme-border)] focus-within:ring-1 focus-within:ring-[var(--color-brand-cyan)] transition-colors',
          disabled && 'cursor-not-allowed opacity-50',
          inputClassName,
          className,
        )}
      >
        <input
          ref={inputRef}
          type="text"
          value={draft}
          inputMode="numeric"
          autoComplete="off"
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitDraft}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); commitDraft(); }
            if (e.key === 'Escape') { setDraft(display); inputRef.current?.blur(); }
          }}
          className="flex-1 bg-transparent outline-none border-0 px-1 py-0.5 placeholder:text-[var(--theme-text-muted)]"
          data-testid={testid || 'datepicker-input'}
          aria-label={rest['aria-label'] || 'Date'}
        />
        {clearable && display && !disabled && (
          <button
            type="button"
            tabIndex={-1}
            onClick={handleClear}
            className="p-0.5 rounded hover:bg-[var(--theme-border)]/40 mr-1"
            aria-label="Clear date"
            data-testid={testid ? `${testid}-clear` : 'datepicker-clear'}
          >
            <X size={12} className="opacity-60" />
          </button>
        )}
        <PopoverTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            className="p-1 rounded hover:bg-[var(--theme-border)]/40 inline-flex items-center"
            aria-label="Open calendar"
            data-testid={testid ? `${testid}-trigger` : 'datepicker-trigger'}
          >
            <CalendarIcon size={14} className="opacity-70" />
          </button>
        </PopoverTrigger>
      </div>
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

export { formatDDMMYYYY, dateToIso, isoToDate, parseTypedDate };
