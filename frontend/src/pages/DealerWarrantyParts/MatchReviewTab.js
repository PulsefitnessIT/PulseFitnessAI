import { useEffect, useState, useCallback } from 'react';
import { Check, X, ShieldCheck, GitMerge, Plus } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, StatCard, Modal, Field, input, CONFIDENCE_TONE } from './shared';

function ConfBadge({ c }) {
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border capitalize ${CONFIDENCE_TONE[c] || CONFIDENCE_TONE.none}`}>{String(c || '').replace(/_/g, ' ')}</span>;
}

export default function MatchReviewTab() {
  const [tab, setTab] = useState('pending');
  const [matches, setMatches] = useState([]);
  const [aliases, setAliases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [aliasModal, setAliasModal] = useState(false);
  const [aliasForm, setAliasForm] = useState({ from_code: '', to_code: '', note: '' });

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      tab === 'aliases' ? Promise.resolve({ matches: [] }) : dpApi.listDataMatches({ review_status: tab === 'all' ? '' : tab }),
      dpApi.listAliases(),
    ]).then(([m, a]) => { setMatches(m.matches || []); setAliases(a.aliases || []); }).finally(() => setLoading(false));
  }, [tab]);
  useEffect(() => { load(); }, [load]);

  const review = async (id, action) => {
    try { await dpApi.reviewMatch(id, action); notify.success(action === 'approve' ? 'Match approved' : 'Match rejected'); load(); }
    catch { notify.error('Failed'); }
  };
  const reviewAlias = async (id, action) => {
    try { await dpApi.reviewAlias(id, action); notify.success('Alias ' + action + 'd'); load(); }
    catch { notify.error('Failed'); }
  };
  const saveAlias = async () => {
    if (!aliasForm.from_code.trim() || !aliasForm.to_code.trim()) { notify.error('Both codes required'); return; }
    try { await dpApi.createAlias(aliasForm); notify.success('Alias submitted for approval'); setAliasModal(false); setAliasForm({ from_code: '', to_code: '', note: '' }); load(); }
    catch { notify.error('Failed'); }
  };

  const pendingAliases = aliases.filter((a) => a.status === 'pending').length;

  return (
    <div className="space-y-4" data-testid="dp-match-review-tab">
      <div className="flex items-center gap-2">
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          {['pending', 'approved', 'rejected', 'all', 'aliases'].map((t) => (
            <button key={t} data-testid={`dp-match-filter-${t}`} onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md capitalize ${tab === t ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`}>
              {t}{t === 'aliases' && pendingAliases ? ` (${pendingAliases})` : ''}
            </button>
          ))}
        </div>
        {tab === 'aliases' && (
          <button data-testid="dp-add-alias-btn" onClick={() => setAliasModal(true)} className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90">
            <Plus size={15} /> New alias
          </button>
        )}
      </div>

      {loading ? <Spinner /> : tab === 'aliases' ? (
        aliases.length === 0 ? <div className="text-center py-16 text-slate-400 text-sm">No aliases yet. Map superseded/old codes to current BOM codes.</div> : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
                <th className="py-2.5 px-4">From (old)</th><th></th><th>To (current)</th><th>Note</th><th>Status</th><th></th>
              </tr></thead>
              <tbody>
                {aliases.map((a) => (
                  <tr key={a.id} data-testid={`dp-alias-row-${a.id}`} className="border-b border-slate-50">
                    <td className="py-2.5 px-4 font-mono text-xs text-slate-600">{a.from_code}</td>
                    <td><GitMerge size={13} className="text-slate-300" /></td>
                    <td className="font-mono text-xs text-slate-600">{a.to_code}</td>
                    <td className="text-xs text-slate-500 max-w-[220px] truncate">{a.note || '—'}</td>
                    <td><span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${a.status === 'approved' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : a.status === 'rejected' ? 'bg-red-50 text-red-600 border-red-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>{a.status}</span></td>
                    <td className="text-right pr-3">
                      {a.status === 'pending' && (
                        <span className="inline-flex gap-1">
                          <button onClick={() => reviewAlias(a.id, 'approve')} className="p-1.5 rounded-md bg-emerald-50 text-emerald-600 hover:bg-emerald-100"><Check size={14} /></button>
                          <button onClick={() => reviewAlias(a.id, 'reject')} className="p-1.5 rounded-md bg-red-50 text-red-500 hover:bg-red-100"><X size={14} /></button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : matches.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No {tab} matches. Run matching from Data Imports.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">Used part</th><th>Matched BOM component</th><th>Confidence</th><th>Machines</th><th>Status</th><th></th>
            </tr></thead>
            <tbody>
              {matches.map((m) => (
                <tr key={m.id} data-testid={`dp-match-row-${m.id}`} className="border-b border-slate-50">
                  <td className="py-2.5 px-4 max-w-[240px]"><span className="font-mono text-xs text-slate-500">{m.used_code}</span><div className="text-xs text-slate-500 truncate">{m.used_description}</div></td>
                  <td className="max-w-[240px]"><span className="font-mono text-xs text-slate-500">{m.bom_code}</span><div className="text-xs text-slate-500 truncate">{m.bom_description}</div></td>
                  <td><ConfBadge c={m.confidence} /></td>
                  <td className="text-xs text-slate-500">{(m.models || []).slice(0, 2).join(', ')}{m.models?.length > 2 ? ` +${m.models.length - 2}` : ''}</td>
                  <td>{m.approved ? <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600"><ShieldCheck size={12} /> approved</span> : <span className="text-[11px] text-amber-600 capitalize">{m.review_status}</span>}</td>
                  <td className="text-right pr-3">
                    {m.review_status === 'pending' && (
                      <span className="inline-flex gap-1">
                        <button data-testid={`dp-match-approve-${m.id}`} onClick={() => review(m.id, 'approve')} className="p-1.5 rounded-md bg-emerald-50 text-emerald-600 hover:bg-emerald-100"><Check size={14} /></button>
                        <button data-testid={`dp-match-reject-${m.id}`} onClick={() => review(m.id, 'reject')} className="p-1.5 rounded-md bg-red-50 text-red-500 hover:bg-red-100"><X size={14} /></button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={aliasModal} onClose={() => setAliasModal(false)} title="Create part alias" testid="dp-alias-modal"
        footer={<>
          <button onClick={() => setAliasModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-alias-save" onClick={saveAlias} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Submit</button>
        </>}>
        <p className="text-xs text-slate-500 mb-3">Map an old / superseded part code to the current BOM component code. Requires approval before it affects matching.</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="From (old / used code) *"><input className={`${input} font-mono`} value={aliasForm.from_code} onChange={(e) => setAliasForm({ ...aliasForm, from_code: e.target.value })} /></Field>
          <Field label="To (current BOM code) *"><input className={`${input} font-mono`} value={aliasForm.to_code} onChange={(e) => setAliasForm({ ...aliasForm, to_code: e.target.value })} /></Field>
        </div>
        <Field label="Note"><input className={input} value={aliasForm.note} onChange={(e) => setAliasForm({ ...aliasForm, note: e.target.value })} /></Field>
      </Modal>
    </div>
  );
}
