/**
 * MODCapexPortal — full-screen CAPEX view for MOD site users.
 *
 * Wraps the shared CapexIntelligenceTab (residual value, TCO, Cap-Spend
 * budget, replacement sweet-spot planner) in a MOD-styled modal shell.
 * Data is auto-scoped to the user's site via resolve_mod_query_filter,
 * so no props are needed. Built for shrinking-budget estates that need
 * to sequence ageing-machine replacement.
 */
import { PoundSterling, X } from 'lucide-react';
import CapexIntelligenceTab from '../CapexIntelligenceTab';

export default function MODCapexPortal({ onClose }) {
  return (
    <div className="fixed inset-0 z-[100] bg-[var(--color-ink-deep)] text-white overflow-y-auto" data-testid="mod-capex-portal">
      <header className="border-b border-white/10 bg-[var(--color-surface-darker)] sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-5 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-amber-500/15 grid place-items-center text-amber-300"><PoundSterling size={18} /></div>
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Reports</div>
              <h1 className="text-white text-lg font-extrabold tracking-tight">CAPEX &amp; Replacement Planner</h1>
            </div>
          </div>
          <button onClick={onClose} className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-white/10 hover:bg-white/5" data-testid="mod-capex-close">
            <X size={13} /> Close
          </button>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-5 pt-6 pb-12">
        <CapexIntelligenceTab />
      </main>
    </div>
  );
}
