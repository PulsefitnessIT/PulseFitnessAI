/** Org Chart — AI assistant (generate from text, analyse, draft JD). */
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Sparkles, Wand2, ClipboardList, Loader2, CheckCircle2, AlertTriangle, Copy, ArrowRight,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ocApi } from './api';

const SEV_COLOR = { high: '#dc2626', medium: '#ea580c', low: '#ca8a04' };

function Section({ icon: Icon, title, desc, children }) {
  return (
    <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
      <h4 className="text-sm font-bold inline-flex items-center gap-2 mb-1" style={{ color: 'var(--theme-text)' }}><Icon size={15} /> {title}</h4>
      <p className="text-[11px] mb-3" style={{ color: 'var(--theme-text-muted)' }}>{desc}</p>
      {children}
    </div>
  );
}

export default function AIPanel({ chartId, onImported }) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [genBusy, setGenBusy] = useState(false);
  const [rows, setRows] = useState(null);
  const [applyBusy, setApplyBusy] = useState(false);

  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [analysis, setAnalysis] = useState(null);

  const [jdTitle, setJdTitle] = useState('');
  const [jdDept, setJdDept] = useState('');
  const [jdBusy, setJdBusy] = useState(false);
  const [jd, setJd] = useState(null);

  const generate = async () => {
    setGenBusy(true); setRows(null);
    try { const r = await ocApi.aiGenerate(chartId, text); setRows(r.rows); if (!r.count) toast(t('orgchart.ai_no_people', 'No people detected — try more detail')); }
    catch (e) { toast.error(e?.response?.data?.detail || t('orgchart.ai_gen_failed', 'Generation failed')); } finally { setGenBusy(false); }
  };
  const applyRows = async () => {
    setApplyBusy(true);
    try { const r = await ocApi.importApplyRows(chartId, rows, { link_existing: true }); toast.success(t('orgchart.ai_added', 'Added {{count}} cards', { count: r.imported })); setRows(null); setText(''); onImported?.(); }
    catch { toast.error(t('orgchart.could_not_add_cards', 'Could not add cards')); } finally { setApplyBusy(false); }
  };

  const analyze = async () => {
    setAnalyzeBusy(true); setAnalysis(null);
    try { setAnalysis(await ocApi.aiAnalyze(chartId)); }
    catch (e) { toast.error(e?.response?.data?.detail || t('orgchart.ai_analysis_failed', 'Analysis failed')); } finally { setAnalyzeBusy(false); }
  };

  const draftJd = async () => {
    if (!jdTitle.trim()) { toast.error(t('orgchart.ai_enter_title', 'Enter a role title')); return; }
    setJdBusy(true); setJd(null);
    try { setJd(await ocApi.aiDraftJd(chartId, { title: jdTitle, department: jdDept })); }
    catch (e) { toast.error(e?.response?.data?.detail || t('orgchart.ai_draft_failed', 'Draft failed')); } finally { setJdBusy(false); }
  };
  const copyJd = () => {
    if (!jd) return;
    const jdText = `${jd.title}\n\n${jd.summary}\n\nResponsibilities:\n${(jd.responsibilities || []).map((x) => `• ${x}`).join('\n')}\n\nRequirements:\n${(jd.requirements || []).map((x) => `• ${x}`).join('\n')}`;
    navigator.clipboard.writeText(jdText); toast.success(t('orgchart.ai_copied', 'Copied'));
  };

  const ta = 'w-full px-3 py-2 rounded-lg text-sm border outline-none';
  const taStyle = { background: 'var(--theme-bg,#fff)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };

  return (
    <div className="space-y-5" data-testid="orgchart-ai-panel">
      <Section icon={Wand2} title={t('orgchart.ai_gen_title', 'Generate from a staff list')} desc={t('orgchart.ai_gen_desc', 'Paste names, roles and who reports to whom — AI builds the cards and reporting lines for you to review.')}>
        <textarea rows={4} className={ta} style={taStyle} value={text} onChange={(e) => setText(e.target.value)} placeholder={t('orgchart.ai_gen_ph', 'e.g. Sarah is the Gym Manager. Tom and Priya are personal trainers reporting to Sarah. We need to hire a receptionist.')} data-testid="orgchart-ai-text" />
        <button onClick={generate} disabled={genBusy || !text.trim()} className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-ai-generate">
          {genBusy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {t('orgchart.ai_generate', 'Generate')}
        </button>
        {rows && (
          <div className="mt-3" data-testid="orgchart-ai-rows">
            <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
              <table className="w-full text-xs">
                <thead><tr style={{ color: 'var(--theme-text-muted)' }}>{[['name', 'Name'], ['title', 'Title'], ['department', 'Department'], ['reports_to', 'Reports to'], ['blank', '']].map(([hk, hl]) => <th key={hk} className="px-2 py-1.5 text-left font-bold">{hl ? t(`orgchart.col_${hk}`, hl) : ''}</th>)}</tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                      <td className="px-2 py-1.5 font-semibold" style={{ color: 'var(--theme-text)' }}>{r.full_name}</td>
                      <td className="px-2 py-1.5" style={{ color: 'var(--theme-text-muted)' }}>{r.job_title || '—'}</td>
                      <td className="px-2 py-1.5" style={{ color: 'var(--theme-text-muted)' }}>{r.department || '—'}</td>
                      <td className="px-2 py-1.5" style={{ color: 'var(--theme-text-muted)' }}>{r.manager_name || '—'}</td>
                      <td className="px-2 py-1.5">{r.vacancy === 'yes' && <span className="text-[10px] font-semibold" style={{ color: '#ea580c' }}>{t('orgchart.ai_vacancy', 'Vacancy')}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button onClick={applyRows} disabled={applyBusy} className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold disabled:opacity-50" style={{ background: '#16a34a', color: '#fff' }} data-testid="orgchart-ai-apply">
              {applyBusy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} {t('orgchart.ai_add_to_chart', 'Add {{count}} cards to chart', { count: rows.length })}
            </button>
          </div>
        )}
      </Section>

      <Section icon={Sparkles} title={t('orgchart.ai_analyse_title', 'Analyse structure')} desc={t('orgchart.ai_analyse_desc', 'Spot staffing gaps, overloaded managers, orphaned reports and circular lines.')}>
        <button onClick={analyze} disabled={analyzeBusy} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-ai-analyze">
          {analyzeBusy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {t('orgchart.ai_run_analysis', 'Run analysis')}
        </button>
        {analysis && (
          <div className="mt-3 space-y-3" data-testid="orgchart-ai-analysis">
            {analysis.summary && <p className="text-sm" style={{ color: 'var(--theme-text)' }}>{analysis.summary}</p>}
            {!!analysis.issues?.length && (
              <div className="space-y-1.5">
                {analysis.issues.map((iss, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs rounded-lg border p-2" style={{ borderColor: 'var(--theme-border)' }}>
                    <AlertTriangle size={13} style={{ color: SEV_COLOR[iss.severity] || '#ca8a04', flexShrink: 0, marginTop: 1 }} />
                    <div><span className="font-semibold uppercase text-[9px] tracking-wide" style={{ color: SEV_COLOR[iss.severity] || '#ca8a04' }}>{iss.type} · {iss.severity}</span><div style={{ color: 'var(--theme-text)' }}>{iss.detail}</div></div>
                  </div>
                ))}
              </div>
            )}
            {!!analysis.suggestions?.length && (
              <ul className="text-xs space-y-1" style={{ color: 'var(--theme-text-muted)' }}>
                {analysis.suggestions.map((s, i) => <li key={i} className="flex gap-1.5"><ArrowRight size={12} className="mt-0.5" style={{ color: 'var(--color-brand-cyan)' }} /> {s}</li>)}
              </ul>
            )}
          </div>
        )}
      </Section>

      <Section icon={ClipboardList} title={t('orgchart.ai_jd_title', 'Draft a job description')} desc={t('orgchart.ai_jd_desc', 'Generate a professional JD for a vacant or planned role.')}>
        <div className="flex flex-wrap gap-2">
          <input className={ta + ' flex-1 min-w-[160px]'} style={taStyle} value={jdTitle} onChange={(e) => setJdTitle(e.target.value)} placeholder={t('orgchart.ai_jd_role_ph', 'Role title')} data-testid="orgchart-jd-title" />
          <input className={ta + ' flex-1 min-w-[140px]'} style={taStyle} value={jdDept} onChange={(e) => setJdDept(e.target.value)} placeholder={t('orgchart.ai_jd_dept_ph', 'Department (optional)')} data-testid="orgchart-jd-dept" />
          <button onClick={draftJd} disabled={jdBusy} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-jd-generate">
            {jdBusy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {t('orgchart.ai_jd_draft', 'Draft')}
          </button>
        </div>
        {jd && (
          <div className="mt-3 rounded-xl border p-3 text-sm" style={{ borderColor: 'var(--theme-border)' }} data-testid="orgchart-jd-result">
            <div className="flex items-center justify-between mb-1"><span className="font-bold" style={{ color: 'var(--theme-text)' }}>{jd.title}</span><button onClick={copyJd} className="inline-flex items-center gap-1 text-[11px]" style={{ color: 'var(--color-brand-cyan)' }} data-testid="orgchart-jd-copy"><Copy size={11} /> {t('orgchart.ai_copy', 'Copy')}</button></div>
            <p className="text-xs mb-2" style={{ color: 'var(--theme-text-muted)' }}>{jd.summary}</p>
            {['responsibilities', 'requirements', 'nice_to_have'].map((k) => (jd[k]?.length ? (
              <div key={k} className="mb-1.5"><div className="text-[10px] font-bold uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>{k.replace('_', ' ')}</div><ul className="text-xs list-disc ml-4" style={{ color: 'var(--theme-text)' }}>{jd[k].map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            ) : null))}
          </div>
        )}
      </Section>
    </div>
  );
}
