/**
 * Marketing Starter Pack panel — iter 216h71 + 216h74 launch wiring.
 *
 * Sits below the Brand Auto-Discovery panel in Brand Kit. Lets the
 * operator one-click "Generate my starter pack" — Claude Haiku 4.5
 * drafts 3 email templates (welcome / win-back / promo) + 3 social
 * posts (Instagram / Facebook / X) in their tone-of-voice using the
 * audience segments + campaigns extracted by brand discovery.
 *
 * Iter 216h74 — every email now has 3 launch actions:
 *   • Send test to me        → real Resend dispatch to the operator
 *   • Create campaign draft  → POST /campaigns → "Open in Campaigns"
 *   • (Top-of-pack) Build welcome journey → 3 emails wired with waits
 *
 * Social cards retain "Copy to clipboard" until the Meta/X OAuth
 * scheduling MVP lands.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Wand2, Mail, Instagram, Facebook, Twitter, Loader2, Sparkles,
  CheckCircle2, Copy, Trash2, Send, FilePlus, GitBranch, ExternalLink,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const EMAIL_META = {
  welcome:  { label: 'Welcome',  hint: 'For new sign-ups',         color: '#10b981' },
  win_back: { label: 'Win-back', hint: 'For lapsed members',       color: '#f59e0b' },
  promo:    { label: 'Promo',    hint: 'Current campaign push',    color: '#6366f1' },
};
const SOCIAL_META = {
  instagram: { label: 'Instagram', Icon: Instagram, color: '#e1306c' },
  facebook:  { label: 'Facebook',  Icon: Facebook,  color: '#1877f2' },
  x:         { label: 'X',         Icon: Twitter,   color: '#0f1419' },
};

export default function StarterPackPanel({ API, headers }) {
  const [doc, setDoc] = useState(null);
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState(null); // e.g. "test:welcome", "campaign:promo", "journey"
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/marketing/starter-pack`, { headers });
      setDoc(r.data || null);
    } catch {
      /* tolerated */
    }
     
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/marketing/starter-pack/generate`, {}, { headers });
      setDoc(r.data);
      notify.success('Starter pack drafted — review & tweak below.');
    } catch (e) {
      notifyApiError(notify, e, 'Could not draft your starter pack');
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    if (!window.confirm('Clear your starter pack drafts? Any campaigns or journeys you already created stay put.')) return;
    setBusy(true);
    try {
      await axios.delete(`${API}/api/marketing/starter-pack`, { headers });
      setDoc(null);
      notify.success('Starter pack cleared.');
    } catch (e) {
      notifyApiError(notify, e, 'Could not clear');
    } finally {
      setBusy(false);
    }
  };

  const copyToClipboard = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text);
      notify.success(`${label} copied to clipboard`);
    } catch {
      notify.error('Clipboard unavailable in this browser');
    }
  };

  const sendTest = async (emailId, label) => {
    setBusyAction(`test:${emailId}`);
    try {
      const r = await axios.post(
        `${API}/api/marketing/starter-pack/emails/${emailId}/test-send`,
        {},
        { headers },
      );
      notify.success(`${label} test email sent to ${r.data?.to || 'your inbox'}`);
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Test send failed');
    } finally {
      setBusyAction(null);
    }
  };

  const createCampaign = async (emailId, label) => {
    setBusyAction(`campaign:${emailId}`);
    try {
      const r = await axios.post(
        `${API}/api/marketing/starter-pack/emails/${emailId}/create-campaign`,
        {},
        { headers },
      );
      const campaignId = r.data?.campaign_id;
      if (r.data?.already_exists) {
        notify.success(`${label} campaign already exists — opening in Campaigns`);
      } else {
        notify.success(`${label} campaign created — pick an audience and Send`);
      }
      await load();
      // Deep-link to the campaigns tab. Marketing tab keys live in MarketingSuite.
      if (campaignId) {
        navigate(`/marketing?tab=campaigns&campaign=${encodeURIComponent(campaignId)}`);
      }
    } catch (e) {
      notifyApiError(notify, e, 'Could not create campaign draft');
    } finally {
      setBusyAction(null);
    }
  };

  const createJourney = async () => {
    setBusyAction('journey');
    try {
      const r = await axios.post(
        `${API}/api/marketing/starter-pack/create-journey`,
        {},
        { headers },
      );
      const journeyId = r.data?.journey_id;
      if (r.data?.already_exists) {
        notify.success('Welcome journey already exists — opening in Journeys');
      } else {
        notify.success('Welcome journey created · 3 emails wired with waits');
      }
      await load();
      if (journeyId) {
        navigate(`/marketing?tab=journeys&journey=${encodeURIComponent(journeyId)}`);
      }
    } catch (e) {
      notifyApiError(notify, e, 'Could not build the welcome journey');
    } finally {
      setBusyAction(null);
    }
  };

  const pack = doc?.pack;
  const launches = doc?.launches || {};
  const emailLaunches = launches.emails || {};
  const journeyId = launches.journey_id;

  return (
    <div
      className="rounded-2xl border p-5 mb-5"
      style={{
        background: 'linear-gradient(135deg, rgba(25, 205, 255,0.05), rgba(236,72,153,0.05))',
        borderColor: 'rgba(25, 205, 255,0.25)',
      }}
      data-testid="starter-pack-panel"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="text-[10px] uppercase tracking-wider font-extrabold text-purple-500 flex items-center gap-1.5">
            <Wand2 size={11} /> Marketing starter pack
          </div>
          <h3 className="text-base font-bold mt-1">3 emails + 3 social posts in your tone</h3>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 max-w-xl">
            We'll use your brand voice, audience segments and current campaigns to draft a
            welcome email, a win-back email, a promo email, and three social posts. Send a
            test, push to Campaigns, or bundle all three into a Welcome Journey in one click.
          </p>
        </div>
        {pack && (
          <button onClick={clear} disabled={busy}
            className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 hover:text-zinc-700 flex items-center gap-1 disabled:opacity-50"
            data-testid="starter-pack-clear">
            <Trash2 size={10} /> Clear
          </button>
        )}
      </div>

      {!pack && (
        <button
          onClick={generate}
          disabled={busy}
          className="px-5 py-2.5 text-sm font-bold rounded-md bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50 flex items-center gap-1.5"
          data-testid="starter-pack-generate"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          Draft my starter pack
        </button>
      )}

      {pack && (
        <div className="space-y-4" data-testid="starter-pack-drafts">
          {/* Journey CTA — sits above the email list */}
          <div className="rounded-lg border border-purple-200 dark:border-purple-900/40 bg-white/70 dark:bg-zinc-900/60 p-3 flex items-center justify-between gap-3 flex-wrap"
            data-testid="starter-pack-journey-row">
            <div className="flex items-start gap-2 min-w-0">
              <GitBranch size={16} className="text-purple-500 mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
                  Welcome series · 3 emails, automated
                </div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  Welcome → wait 3d → Win-back → wait 7d → Promo. Drops into Journeys as a draft so you can wire the trigger & publish.
                </div>
              </div>
            </div>
            {journeyId ? (
              <button
                onClick={() => navigate(`/marketing?tab=journeys&journey=${encodeURIComponent(journeyId)}`)}
                className="px-3 py-1.5 text-xs font-bold rounded-md border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-200 inline-flex items-center gap-1.5"
                data-testid="starter-pack-open-journey">
                <CheckCircle2 size={11} /> Journey created · Open
                <ExternalLink size={10} />
              </button>
            ) : (
              <button
                onClick={createJourney}
                disabled={busyAction === 'journey'}
                className="px-3 py-1.5 text-xs font-bold rounded-md bg-purple-600 hover:bg-purple-700 text-white inline-flex items-center gap-1.5 disabled:opacity-50"
                data-testid="starter-pack-build-journey">
                {busyAction === 'journey'
                  ? <Loader2 size={11} className="animate-spin" />
                  : <GitBranch size={11} />}
                Build welcome journey
              </button>
            )}
          </div>

          {/* Emails */}
          <Section icon={Mail} title="Email templates">
            <div className="space-y-2">
              {(pack.emails || []).map((em) => {
                const meta = EMAIL_META[em.id] || { label: em.id, hint: '', color: '#71717a' };
                const launch = emailLaunches[em.id] || {};
                const campaignId = launch.campaign_id;
                const testSentAt = launch.test_sent_at;
                return (
                  <details key={em.id} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 group" data-testid={`starter-pack-email-${em.id}`}>
                    <summary className="cursor-pointer p-3 flex items-center gap-2 list-none">
                      <span className="w-1.5 h-6 rounded shrink-0" style={{ background: meta.color }} />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold uppercase tracking-wider" style={{ color: meta.color }}>
                          {meta.label} <span className="text-zinc-400 ml-1 normal-case">· {meta.hint}</span>
                        </div>
                        <div className="text-sm font-semibold mt-0.5 truncate">{em.subject}</div>
                        <div className="text-xs text-zinc-500 dark:text-zinc-400 truncate">{em.preview}</div>
                      </div>
                      <button
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); copyToClipboard(`Subject: ${em.subject}\nPreview: ${em.preview}\n\n${em.body}`, `${meta.label} email`); }}
                        className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded flex items-center gap-1"
                        data-testid={`starter-pack-copy-email-${em.id}`}>
                        <Copy size={10} /> Copy
                      </button>
                    </summary>
                    <div className="px-4 pb-3 border-t border-zinc-100 dark:border-zinc-800 pt-2 mt-1 space-y-3">
                      <div className="text-xs whitespace-pre-wrap font-mono leading-relaxed text-zinc-700 dark:text-zinc-300">
                        {em.body}
                      </div>
                      <div className="flex items-center flex-wrap gap-2 pt-1">
                        <button
                          onClick={(e) => { e.preventDefault(); sendTest(em.id, meta.label); }}
                          disabled={busyAction === `test:${em.id}`}
                          className="px-2.5 py-1 text-[11px] font-bold rounded-md border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-zinc-50 dark:hover:bg-zinc-800 inline-flex items-center gap-1.5 disabled:opacity-50"
                          data-testid={`starter-pack-test-send-${em.id}`}>
                          {busyAction === `test:${em.id}`
                            ? <Loader2 size={10} className="animate-spin" />
                            : <Send size={10} />}
                          Send test to me
                        </button>
                        {testSentAt && (
                          <span className="text-[10px] text-emerald-600 dark:text-emerald-400 inline-flex items-center gap-1"
                            data-testid={`starter-pack-test-sent-${em.id}`}>
                            <CheckCircle2 size={10} /> Sent {formatRelative(testSentAt)}
                          </span>
                        )}
                        {campaignId ? (
                          <button
                            onClick={(e) => {
                              e.preventDefault();
                              navigate(`/marketing?tab=campaigns&campaign=${encodeURIComponent(campaignId)}`);
                            }}
                            className="px-2.5 py-1 text-[11px] font-bold rounded-md border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-200 inline-flex items-center gap-1.5"
                            data-testid={`starter-pack-open-campaign-${em.id}`}>
                            <CheckCircle2 size={10} /> Campaign · Open
                            <ExternalLink size={9} />
                          </button>
                        ) : (
                          <button
                            onClick={(e) => { e.preventDefault(); createCampaign(em.id, meta.label); }}
                            disabled={busyAction === `campaign:${em.id}`}
                            className="px-2.5 py-1 text-[11px] font-bold rounded-md bg-purple-600 hover:bg-purple-700 text-white inline-flex items-center gap-1.5 disabled:opacity-50"
                            data-testid={`starter-pack-create-campaign-${em.id}`}>
                            {busyAction === `campaign:${em.id}`
                              ? <Loader2 size={10} className="animate-spin" />
                              : <FilePlus size={10} />}
                            Create campaign
                          </button>
                        )}
                      </div>
                    </div>
                  </details>
                );
              })}
            </div>
          </Section>

          {/* Social */}
          <Section icon={Sparkles} title="Social posts">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {(pack.social || []).map((sp) => {
                const meta = SOCIAL_META[sp.id] || { label: sp.platform, Icon: Sparkles, color: '#71717a' };
                const Icon = meta.Icon;
                return (
                  <div key={sp.id} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-3" data-testid={`starter-pack-social-${sp.id}`}>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider" style={{ color: meta.color }}>
                        <Icon size={11} /> {meta.label}
                      </div>
                      <button
                        onClick={() => copyToClipboard(sp.body, `${meta.label} post`)}
                        className="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded flex items-center gap-0.5"
                        data-testid={`starter-pack-copy-social-${sp.id}`}>
                        <Copy size={9} /> Copy
                      </button>
                    </div>
                    <p className="text-xs whitespace-pre-wrap leading-relaxed text-zinc-700 dark:text-zinc-300">{sp.body}</p>
                  </div>
                );
              })}
            </div>
          </Section>

          <div className="rounded-md bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-900 p-2.5 text-xs flex items-start gap-2">
            <CheckCircle2 size={12} className="text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
            <span className="text-emerald-700 dark:text-emerald-200">
              <strong>Drafts saved.</strong> Send a test to yourself before sharing, push any email straight to Campaigns, or bundle all three into a Welcome Journey above.
            </span>
          </div>

          <div className="flex justify-end pt-1">
            <button onClick={generate} disabled={busy}
              className="px-3 py-1.5 text-xs font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded-md flex items-center gap-1.5 disabled:opacity-50"
              data-testid="starter-pack-regenerate">
              {busy ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
              Re-generate
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ icon: Icon, title, children }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5 mb-2">
        {Icon && <Icon size={11} />} {title}
      </div>
      {children}
    </div>
  );
}

function formatRelative(iso) {
  if (!iso) return '';
  try {
    const then = new Date(iso).getTime();
    const diff = Math.max(0, Date.now() - then);
    const m = Math.round(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.round(h / 24);
    return `${d}d ago`;
  } catch {
    return '';
  }
}
