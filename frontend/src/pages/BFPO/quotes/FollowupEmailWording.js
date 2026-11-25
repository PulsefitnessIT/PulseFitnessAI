import { useEffect, useState } from 'react';
import { CheckCircle2, Mail, Save } from 'lucide-react';
import { notify } from '@/components/notifications';
import { mq, errText, inputStyle, muted } from './modQuotesApi';
import { Btn, Banner, Field } from './MqUi';

const LABELS = { 1: 'Follow-up 1 · 2 weeks', 2: 'Follow-up 2 · 4 weeks', 3: 'Follow-up 3 · 6 weeks' };

function TemplateEditor({ n, t, disabled, onChange }) {
  return (
    <div className="mq-card p-4 space-y-2" data-testid={`mq-fu-tpl-${n}`}>
      <div className="font-semibold text-sm">{LABELS[n]}</div>
      <Field label="Subject">
        <input value={t.subject} disabled={disabled} onChange={(e) => onChange({ ...t, subject: e.target.value })}
          className="w-full rounded px-2 py-1 text-sm" style={inputStyle} data-testid={`mq-fu-subject-${n}`} aria-label={`Follow-up ${n} subject`} />
      </Field>
      <Field label="Message">
        <textarea rows={9} value={t.body} disabled={disabled} onChange={(e) => onChange({ ...t, body: e.target.value })}
          className="w-full rounded px-2 py-1 text-sm" style={inputStyle} data-testid={`mq-fu-body-${n}`} aria-label={`Follow-up ${n} message`} />
      </Field>
    </div>
  );
}

export default function FollowupEmailWording() {
  const [s, setS] = useState(null);
  const [tpl, setTpl] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = () => mq.get('/followup-emails').then((r) => { setS(r.data); setTpl(r.data.templates); }).catch((e) => notify.error(errText(e)));
  useEffect(() => { load(); }, []);
  if (!s) return null;
  const dirty = JSON.stringify(tpl) !== JSON.stringify(s.templates);
  const save = async () => {
    setBusy(true);
    try { await mq.put('/followup-emails', { templates: tpl }); notify.success('Wording saved — it needs owner approval before customers are emailed'); await load(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  const approve = async () => {
    if (!window.confirm('Approve this wording for the customer follow-up emails?')) return;
    setBusy(true);
    try { await mq.post('/followup-emails/approve'); notify.success('Follow-up wording approved'); await load(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  const state = s.approved ? `Approved by ${s.approved_by_name || 'an owner'}` : 'Awaiting owner approval';
  return (
    <div className="mq-card p-4 space-y-3" data-testid="mq-fu-wording">
      <div className="flex flex-wrap items-center gap-3">
        <Mail size={16} aria-hidden />
        <div className="font-semibold">Customer email wording</div>
        <span className="text-xs" style={{ color: s.approved ? 'var(--color-success)' : 'var(--color-warning)' }} data-testid="mq-fu-approval-state">{state}</span>
        <span className="text-xs" style={muted} data-testid="mq-fu-live-state">
          {s.approved && s.live_switch_on ? 'Customer emails are sending' : 'Customer emails are not being sent yet'}
        </span>
        <Btn size="sm" className="ml-auto" onClick={() => setOpen(!open)} data-testid="mq-fu-toggle">{open ? 'Hide wording' : 'Review wording'}</Btn>
      </div>
      {open && (
        <>
          {!s.live_switch_on && <Banner testid="mq-fu-switch-off">Sending is also switched off for this system. After approval, ask your administrator to turn on live MOD quote emails.</Banner>}
          <p className="text-xs" style={muted}>Placeholders filled in automatically: {s.placeholders.join(' ')}. The quotation PDFs are attached to every email.</p>
          <div className="grid lg:grid-cols-3 gap-3">
            {['1', '2', '3'].map((n) => <TemplateEditor key={n} n={n} t={tpl[n]} disabled={!s.can_edit} onChange={(t) => setTpl({ ...tpl, [n]: t })} />)}
          </div>
          <div className="flex flex-wrap gap-2">
            {s.can_edit && <Btn icon={Save} loading={busy} disabled={!dirty} onClick={save} data-testid="mq-fu-save">Save wording</Btn>}
            {s.can_approve && <Btn icon={CheckCircle2} variant="primary" disabled={busy || dirty || s.approved} onClick={approve} data-testid="mq-fu-approve">Approve wording</Btn>}
          </div>
        </>
      )}
    </div>
  );
}
