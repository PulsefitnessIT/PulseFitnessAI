
const fmt = (iso) => (iso ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '—');
const dur = (a, b) => {
  if (!a || !b) return '';
  const m = Math.round((new Date(b) - new Date(a)) / 60000);
  return m >= 0 ? ` (${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m)` : '';
};

function Row({ label, children, testid }) {
  return (
    <div className="grid grid-cols-[150px_1fr] gap-2 py-1.5 border-b border-zinc-100 dark:border-zinc-800 last:border-0" data-testid={testid}>
      <span className="text-[11px] font-bold uppercase tracking-wide text-zinc-400">{label}</span>
      <span className="text-xs text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap">{children}</span>
    </div>
  );
}

function SignoffBlock({ signoff }) {
  if (!signoff) return <p className="text-xs text-zinc-400 mt-2" data-testid="report-view-no-signature">No customer signature captured.</p>;
  if (signoff.unavailable) {
    return <p className="text-xs text-amber-700 mt-2" data-testid="report-view-unavailable">Customer unable to sign — {signoff.unavailable_reason}{signoff.signed_at ? ` · ${fmt(signoff.signed_at)}` : ''}</p>;
  }
  return (
    <div className="mt-2" data-testid="report-view-signature">
      <p className="text-[11px] font-bold uppercase tracking-wide text-zinc-400 mb-1">Customer sign-off</p>
      {signoff.image_data ? <img src={signoff.image_data} alt="Customer signature" className="max-h-24 rounded border border-zinc-200 bg-white p-1 dark:bg-zinc-900 dark:border-zinc-800" /> : null}
      <p className="text-xs text-zinc-600 dark:text-zinc-300 mt-1">
        Signed by <b>{signoff.signed_by_name || 'Customer'}</b>{signoff.signed_by_role ? ` (${signoff.signed_by_role})` : ''}{signoff.signed_at ? ` · ${fmt(signoff.signed_at)}` : ''}
      </p>
    </div>
  );
}

export function EngineerReportView({ report, signoff, fallbackSummary }) {
  if (!report && !signoff && !fallbackSummary) return null;
  const parts = report?.further_parts_required || [];
  return (
    <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-3" data-testid="engineer-report-view">
      <p className="text-[11px] font-bold uppercase tracking-wide text-zinc-500 mb-1">Engineer report</p>
      {report ? (
        <>
          <Row label="Start time" testid="report-view-start">{fmt(report.start_time)}</Row>
          <Row label="End time" testid="report-view-end">{fmt(report.end_time)}{dur(report.start_time, report.end_time)}</Row>
          <Row label="Work completed" testid="report-view-work">{report.work_completed || '—'}</Row>
          <Row label="Further work" testid="report-view-further-work">{report.further_work_required || 'None'}</Row>
          <Row label="Further parts" testid="report-view-further-parts">{parts.length ? parts.map((p) => `${p.qty} × ${p.name}${p.sku ? ` (${p.sku})` : ''}`).join('\n') : 'None'}</Row>
        </>
      ) : (
        <Row label="Work completed" testid="report-view-work">{fallbackSummary || '—'}</Row>
      )}
      <SignoffBlock signoff={signoff} />
    </div>
  );
}

export default EngineerReportView;
