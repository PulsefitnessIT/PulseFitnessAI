import { Check, Loader2 } from 'lucide-react';
import { priorityTone } from './wizardConfig';

export function ConfirmationScreen({ confirmation, onDone }) {
  const isOffline = confirmation.offline;
  const tickets = confirmation.tickets || [];
  const multi = tickets.length > 1;
  return (
    <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm grid place-items-center p-4" data-testid="mod-fault-confirmation">
      <div
        className="w-full max-w-md border rounded-2xl overflow-hidden p-8 text-center"
        style={{ background: 'var(--theme-surface)', borderColor: isOffline ? 'rgba(245,158,11,0.4)' : 'rgb(var(--rgb-brand-cyan)/0.35)' }}
      >
        <div className={`w-16 h-16 rounded-full grid place-items-center mx-auto mb-4 ${isOffline ? 'bg-amber-500/20' : 'bg-emerald-500/20'}`}>
          {isOffline ? <Loader2 size={32} className="text-amber-500 dark:text-amber-300" /> : <Check size={32} className="text-emerald-500 dark:text-emerald-400" />}
        </div>
        <div className={`text-[10px] font-bold uppercase tracking-[0.2em] mb-1 ${isOffline ? 'text-amber-600 dark:text-amber-300' : 'text-[var(--color-brand-cyan)]'}`}>
          {isOffline ? 'Saved offline' : (multi ? `${tickets.length} tickets created` : 'Ticket created')}
        </div>

        {multi ? (
          <div className="mt-3 space-y-1.5 text-left max-h-[40vh] overflow-y-auto">
            {tickets.map((t, i) => (
              <div key={i} className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2" style={{ borderColor: 'var(--theme-border)' }} data-testid={`mod-confirmation-ticket-${i}`}>
                <span className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{t.machine?.name || t.machine?.serial_number || 'Machine'}</span>
                <span className="text-sm font-extrabold" style={{ color: 'var(--theme-text)' }}>{isOffline ? 'QUEUED' : t.ticket_ref}</span>
              </div>
            ))}
          </div>
        ) : (
          <>
            <div className="text-2xl font-extrabold mb-1 tracking-tight" style={{ color: 'var(--theme-text)' }} data-testid="mod-confirmation-ref">
              {isOffline ? 'QUEUED' : tickets[0]?.ticket_ref}
            </div>
            {tickets[0]?.priority && (
              <div className={`inline-block text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded mt-1 ${priorityTone(tickets[0].priority)}`}>
                {tickets[0].priority}
              </div>
            )}
            {tickets[0]?.duplicate_of && (
              <div className="mt-3 text-xs text-amber-600 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5">
                ⚠ Similar open ticket exists: {tickets[0].duplicate_of}
              </div>
            )}
          </>
        )}

        <p className="text-sm mt-4" style={{ color: 'var(--theme-text-muted)' }}>
          {isOffline
            ? "We've stored these faults and their photos on your device. They'll upload and create tickets the moment you're back online."
            : 'Confirmation email sent. You can track status on the dashboard.'}
        </p>
        {confirmation.partialFailed?.length > 0 && (
          <div className="mt-3 text-xs text-amber-600 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5 text-left" data-testid="mod-confirmation-partial-failed">
            ⚠ These machines didn't submit — please reopen the wizard and log them again: <strong>{confirmation.partialFailed.join(', ')}</strong>
          </div>
        )}
        <button
          onClick={onDone}
          className="mt-5 w-full rounded-lg px-4 py-3 text-sm font-extrabold"
          style={{ background: isOffline ? 'var(--color-warning)' : 'var(--color-brand-cyan)', color: '#04121a' }}
          data-testid="mod-confirmation-done"
        >Back to dashboard</button>
      </div>
    </div>
  );
}
