/* Shared, presentational primitives for the MOD Fault Wizard. */

export function StepTitle({ eyebrow, title, subtitle }) {
  return (
    <div className="mb-4">
      <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">{eyebrow}</div>
      <h3 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.01em', color: 'var(--theme-text)' }}>{title}</h3>
      {subtitle && <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>{subtitle}</div>}
    </div>
  );
}

export function RadioGroup({ label, options, value, onChange, testidPrefix, withHelp, alert, error }) {
  return (
    <div role="radiogroup" aria-label={label}>
      <div className="text-[10px] font-bold uppercase tracking-wider mb-1.5" style={{ color: error ? '#ef4444' : 'var(--theme-text-muted)' }}>
        {label}{error && <span className="ml-1 normal-case tracking-normal font-semibold">· required</span>}
      </div>
      <div className={`grid grid-cols-1 sm:grid-cols-3 gap-2 ${error ? 'rounded-lg ring-1 ring-red-500/50 p-1 -m-1' : ''}`}>
        {options.map((o) => {
          const picked = o.id === value;
          const cls = picked
            ? (alert ? 'border-red-500 bg-red-500/10' : 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.12)]')
            : 'hover:border-[var(--color-brand-cyan)]';
          return (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={picked}
              onClick={() => onChange(o.id)}
              className={`text-left rounded-lg border px-3 py-2.5 transition-all ${cls}`}
              style={picked ? {} : { background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}
              data-testid={`${testidPrefix}-${o.id}`}
            >
              <div className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{o.label}</div>
              {withHelp && o.help && <div className="text-[10px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{o.help}</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ReviewRow({ label, value, multiline }) {
  return (
    <div className={multiline ? 'pt-1' : 'flex items-start gap-3'}>
      <div className="text-[10px] font-bold uppercase tracking-wider w-28 shrink-0" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
      <div className={`text-sm ${multiline ? 'mt-1' : 'flex-1'}`} style={{ color: 'var(--theme-text)' }}>{value || '—'}</div>
    </div>
  );
}

/* Client-side image compression: max edge 1920px, WebP q=0.82. */
export async function compressToWebP(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const MAX = 1920;
        const scale = Math.min(1, MAX / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale);
        const h = Math.round(img.height * scale);
        const canvas = document.createElement('canvas');
        canvas.width = w; canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        canvas.toBlob(
          (blob) => {
            if (!blob) return reject(new Error('Compression failed'));
            resolve(new File([blob], `mod-${Date.now()}.webp`, { type: 'image/webp' }));
          },
          'image/webp',
          0.82,
        );
      };
      img.onerror = () => reject(new Error('Image load failed'));
      img.src = reader.result;
    };
    reader.onerror = () => reject(new Error('Read failed'));
    reader.readAsDataURL(file);
  });
}
