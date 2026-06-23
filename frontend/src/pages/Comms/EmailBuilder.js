/**
 * Pulse Fitness AI — drag-and-drop email builder.
 *
 * Left: block palette (drag onto canvas). Centre: canvas (reorder by
 * dragging, click to select). Right: properties for the selected block +
 * merge-tag inserter. Top: device/dark preview, quality checks, test send,
 * save. Content model = `{ subject, blocks:[{id,type,props}] }` — the same
 * shape the shared Comms engine renders server-side.
 */
import React, { useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Type, Heading1, Image as ImageIcon, MousePointerClick, Minus, MoveVertical,
  Share2, Video, Code, LayoutPanelTop, Sparkles, Monitor, Smartphone, Moon,
  Send, Save, Trash2, ArrowUp, ArrowDown, X, GripVertical, AlertTriangle, CheckCircle2, Wand2, Loader2,
} from 'lucide-react';

const CYAN = '#19CDFF';
const uid = () => Math.random().toString(36).slice(2, 10);

const PALETTE = [
  { type: 'logo', label: 'Logo', icon: ImageIcon },
  { type: 'heading', label: 'Heading', icon: Heading1 },
  { type: 'text', label: 'Paragraph', icon: Type },
  { type: 'image', label: 'Image', icon: ImageIcon },
  { type: 'button', label: 'Button', icon: MousePointerClick },
  { type: 'divider', label: 'Divider', icon: Minus },
  { type: 'spacer', label: 'Spacer', icon: MoveVertical },
  { type: 'social', label: 'Social', icon: Share2 },
  { type: 'video', label: 'Video', icon: Video },
  { type: 'html', label: 'HTML', icon: Code },
  { type: 'footer', label: 'Footer', icon: LayoutPanelTop },
];

const DEFAULTS = {
  logo: { align: 'center', src: '/brand/pulse-mark.svg' },
  heading: { text: 'Your heading', size: 24, align: 'left', color: '#0B1220' },
  text: { text: 'Write something your members or clients will care about. Use merge tags like {{first_name}} to personalise.', align: 'left' },
  image: { src: 'https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=800', alt: 'Description of the image' },
  button: { text: 'Book now', url: '{{booking_link}}', color: CYAN, align: 'center' },
  divider: {},
  spacer: { height: 24 },
  social: { links: [{ label: 'Instagram', url: '#' }, { label: 'Facebook', url: '#' }] },
  video: { url: '#', thumbnail: 'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=800' },
  html: { html: '<p style="padding:0 24px">Custom HTML</p>' },
  footer: { text: 'You are receiving this email from Pulse Fitness AI because you opted in.' },
};

const MERGE_GROUPS = {
  Member: ['{{first_name}}', '{{last_name}}', '{{membership_type}}', '{{renewal_link}}', '{{booking_link}}', '{{payment_link}}'],
  B2B: ['{{contact_first_name}}', '{{company_name}}', '{{quote_link}}', '{{proposal_link}}', '{{invoice_link}}'],
  System: ['{{unsubscribe_link}}', '{{preferences_link}}', '{{view_in_browser_link}}'],
};

function esc(v) {
  return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Client-side mirror of the backend renderer for live preview.
function renderBlock(b) {
  const p = b.props || {};
  switch (b.type) {
    case 'logo':
      return `<div style="padding:24px 24px 8px;text-align:${p.align || 'center'}"><img src="${esc(p.src)}" alt="Pulse Fitness AI" style="height:40px"></div>`;
    case 'heading':
      return `<div style="padding:8px 24px;font-family:Arial;font-size:${p.size || 24}px;font-weight:800;color:${esc(p.color || '#0B1220')};text-align:${p.align || 'left'}">${esc(p.text)}</div>`;
    case 'text':
      return `<div style="padding:8px 24px;font-family:Arial;font-size:15px;line-height:1.6;color:#374151;text-align:${p.align || 'left'}">${p.text || ''}</div>`;
    case 'image':
      return `<div style="padding:12px 24px;text-align:center"><img src="${esc(p.src)}" alt="${esc(p.alt)}" style="max-width:100%;border-radius:10px"></div>`;
    case 'button':
      return `<div style="padding:16px 24px;text-align:${p.align || 'center'}"><a href="#" style="background:${esc(p.color || CYAN)};color:#03212b;text-decoration:none;font-weight:700;font-family:Arial;padding:13px 26px;border-radius:999px;display:inline-block;font-size:15px">${esc(p.text)}</a></div>`;
    case 'divider':
      return `<div style="padding:8px 24px"><hr style="border:none;border-top:1px solid #E5E7EB;margin:0"></div>`;
    case 'spacer':
      return `<div style="height:${parseInt(p.height, 10) || 24}px"></div>`;
    case 'social':
      return `<div style="padding:12px 24px;text-align:center">${(p.links || []).map((l) => `<a href="#" style="color:${CYAN};text-decoration:none;font-weight:700;margin:0 8px;font-family:Arial;font-size:13px">${esc(l.label)}</a>`).join('')}</div>`;
    case 'video':
      return `<div style="padding:12px 24px;text-align:center"><img src="${esc(p.thumbnail)}" alt="Watch video" style="max-width:100%;border-radius:10px"></div>`;
    case 'html':
      return p.html || '';
    case 'footer':
      return `<div style="padding:20px 24px;font-family:Arial;font-size:12px;line-height:1.6;color:#9CA3AF;text-align:center;border-top:1px solid #F1F5F9">${esc(p.text)}<br><span style="color:#9CA3AF">Unsubscribe · Update preferences · View in browser</span></div>`;
    default:
      return '';
  }
}

function PaletteItem({ item, onAdd }) {
  const Icon = item.icon;
  return (
    <button
      type="button"
      draggable
      onDragStart={(e) => { e.dataTransfer.setData('text/new-block', item.type); e.dataTransfer.effectAllowed = 'copy'; }}
      onClick={() => onAdd(item.type)}
      data-testid={`palette-${item.type}`}
      className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-700 text-sm font-semibold hover:border-[var(--c)] hover:text-slate-900 transition-colors cursor-grab active:cursor-grabbing"
      style={{ '--c': CYAN }}
    >
      <Icon size={15} />{item.label}
    </button>
  );
}

export default function EmailBuilder({ campaign, API, headers, onClose, onSaved }) {
  const [subject, setSubject] = useState(campaign?.content?.subject || '');
  const [blocks, setBlocks] = useState(() => {
    const b = campaign?.content?.blocks;
    return Array.isArray(b) && b.length ? b : [
      { id: uid(), type: 'logo', props: { ...DEFAULTS.logo } },
      { id: uid(), type: 'heading', props: { ...DEFAULTS.heading, text: campaign?.name || 'Your heading' } },
      { id: uid(), type: 'text', props: { ...DEFAULTS.text } },
      { id: uid(), type: 'footer', props: { ...DEFAULTS.footer } },
    ];
  });
  const [selId, setSelId] = useState(null);
  const [device, setDevice] = useState('desktop');
  const [dark, setDark] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testTo, setTestTo] = useState('');
  const [showTest, setShowTest] = useState(false);
  const [showAI, setShowAI] = useState(false);
  const [aiBrief, setAiBrief] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [subjIdeas, setSubjIdeas] = useState([]);
  const [subjBusy, setSubjBusy] = useState(false);
  const dragIndex = useRef(null);

  const sel = blocks.find((b) => b.id === selId) || null;

  const aiGenerate = async () => {
    if (!aiBrief.trim()) { toast.error('Describe what the email is about'); return; }
    setAiBusy(true);
    try {
      const r = await axios.post(`${API}/api/comms/ai/write`, {
        brief: aiBrief, campaign_type: campaign?.campaign_type, tone: 'friendly professional',
      }, { headers });
      const newBlocks = (r.data.blocks || []).map((b) => ({ id: uid(), type: b.type, props: b.props || {} }));
      if (newBlocks.length) {
        setBlocks([
          { id: uid(), type: 'logo', props: { ...DEFAULTS.logo } },
          ...newBlocks,
          { id: uid(), type: 'footer', props: { ...DEFAULTS.footer } },
        ]);
      }
      if (r.data.subject) setSubject(r.data.subject);
      toast.success('Draft generated — tweak it as you like');
      setShowAI(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'AI is unavailable right now');
    } finally { setAiBusy(false); }
  };

  const aiSuggestSubjects = async () => {
    setSubjBusy(true);
    try {
      const r = await axios.post(`${API}/api/comms/ai/subjects`, {
        topic: aiBrief || subject || campaign?.name, audience: campaign?.related_module, tone: 'engaging', n: 5,
      }, { headers });
      setSubjIdeas(r.data.subjects || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'AI is unavailable right now');
    } finally { setSubjBusy(false); }
  };

  const aiImproveSelected = async () => {
    if (!sel || !['text', 'heading'].includes(sel.type)) return;
    setAiBusy(true);
    try {
      const r = await axios.post(`${API}/api/comms/ai/improve`, {
        text: sel.props?.text || '', goal: 'clarity and engagement',
      }, { headers });
      if (r.data.text) { updateProps({ text: r.data.text }); toast.success('Improved'); }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'AI is unavailable right now');
    } finally { setAiBusy(false); }
  };

  const addBlock = (type, atIndex = null) => {
    const nb = { id: uid(), type, props: { ...(DEFAULTS[type] || {}) } };
    setBlocks((prev) => {
      const next = [...prev];
      if (atIndex == null || atIndex >= next.length) next.push(nb);
      else next.splice(atIndex, 0, nb);
      return next;
    });
    setSelId(nb.id);
  };

  const updateProps = (patch) => {
    setBlocks((prev) => prev.map((b) => (b.id === selId ? { ...b, props: { ...b.props, ...patch } } : b)));
  };
  const removeBlock = (id) => { setBlocks((prev) => prev.filter((b) => b.id !== id)); if (selId === id) setSelId(null); };
  const move = (id, dir) => {
    setBlocks((prev) => {
      const i = prev.findIndex((b) => b.id === id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  };

  const onCanvasDrop = (e, atIndex) => {
    e.preventDefault();
    const newType = e.dataTransfer.getData('text/new-block');
    if (newType) { addBlock(newType, atIndex); return; }
    const from = dragIndex.current;
    if (from == null) return;
    setBlocks((prev) => {
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      let to = atIndex;
      if (from < atIndex) to -= 1;
      next.splice(to, 0, moved);
      return next;
    });
    dragIndex.current = null;
  };

  const quality = useMemo(() => {
    const w = [];
    if (!subject.trim()) w.push({ level: 'error', message: 'Subject line is missing.' });
    else if (subject.length > 90) w.push({ level: 'warn', message: 'Subject line is over 90 characters.' });
    const all = subject + ' ' + blocks.map((b) => JSON.stringify(b.props)).join(' ');
    if (!all.includes('{{unsubscribe_link}}') && campaign?.campaign_type !== 'transactional') {
      w.push({ level: 'warn', message: 'No unsubscribe link found (footer block includes one).' });
    }
    if (blocks.some((b) => b.type === 'image' && !(b.props || {}).alt)) {
      w.push({ level: 'warn', message: 'An image is missing alt text (accessibility).' });
    }
    if (!blocks.length) w.push({ level: 'error', message: 'The email has no content.' });
    return w;
  }, [subject, blocks, campaign]);

  const previewHtml = useMemo(() => {
    const inner = blocks.map(renderBlock).join('');
    return `<div style="background:${dark ? '#0B1220' : '#F3F4F6'};padding:24px 0"><div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden">${inner}</div></div>`;
  }, [blocks, dark]);

  const save = async () => {
    setSaving(true);
    try {
      const r = await axios.put(`${API}/api/comms/campaigns/${campaign.id}`, {
        content: { subject, blocks },
      }, { headers });
      toast.success('Campaign saved');
      onSaved && onSaved(r.data.campaign);
      return r.data.campaign;
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
      return null;
    } finally { setSaving(false); }
  };

  const sendTest = async () => {
    const saved = await save();
    if (!saved) return;
    try {
      const r = await axios.post(`${API}/api/comms/campaigns/${campaign.id}/test-send`, { to: testTo }, { headers });
      if (r.data.ok) toast.success(`Test sent to ${r.data.sent_to}`);
      else toast.error('Test send failed — check email settings');
      setShowTest(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Test send failed');
    }
  };

  const errors = quality.filter((q) => q.level === 'error').length;
  const warns = quality.filter((q) => q.level === 'warn').length;

  return (
    <div className="fixed inset-0 z-[200] bg-slate-100 flex flex-col" data-testid="email-builder">
      {/* Toolbar */}
      <div className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 gap-3 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-500" data-testid="builder-close"><X size={18} /></button>
          <span className="font-bold text-slate-900 truncate pulse-font-heading">{campaign?.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-1 bg-slate-100 rounded-full p-1">
            <button onClick={() => setDevice('desktop')} className={`p-1.5 rounded-full ${device === 'desktop' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`} data-testid="preview-desktop"><Monitor size={15} /></button>
            <button onClick={() => setDevice('mobile')} className={`p-1.5 rounded-full ${device === 'mobile' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`} data-testid="preview-mobile"><Smartphone size={15} /></button>
            <button onClick={() => setDark((d) => !d)} className={`p-1.5 rounded-full ${dark ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`} data-testid="preview-dark"><Moon size={15} /></button>
          </div>
          <div className="flex items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-full bg-slate-100" data-testid="quality-badge" title={quality.map((q) => q.message).join('\n') || 'No issues'}>
            {errors ? <AlertTriangle size={13} className="text-rose-500" /> : <CheckCircle2 size={13} className="text-emerald-500" />}
            <span className={errors ? 'text-rose-600' : 'text-slate-600'}>{errors} err · {warns} warn</span>
          </div>
          <button onClick={() => setShowAI(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm font-bold text-white" style={{ backgroundImage: 'linear-gradient(135deg,#7C3AED,#19CDFF)' }} data-testid="builder-ai"><Wand2 size={14} />AI</button>
          <button onClick={() => setShowTest(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-full border border-slate-200 text-sm font-semibold text-slate-700 hover:bg-slate-50" data-testid="builder-test"><Send size={14} />Test</button>
          <button onClick={save} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold text-[#03212b] disabled:opacity-50" style={{ background: CYAN }} data-testid="builder-save"><Save size={14} />{saving ? 'Saving…' : 'Save'}</button>
        </div>
      </div>

      <div className="flex-1 flex min-h-0">
        {/* Palette */}
        <aside className="w-48 bg-white border-r border-slate-200 p-3 overflow-y-auto hidden md:block shrink-0">
          <p className="text-[11px] uppercase tracking-wider font-bold text-slate-400 mb-2 px-1">Blocks</p>
          <div className="space-y-1.5">
            {PALETTE.map((it) => <PaletteItem key={it.type} item={it} onAdd={addBlock} />)}
          </div>
        </aside>

        {/* Canvas */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-8">
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject line…"
            data-testid="builder-subject"
            className="w-full max-w-[600px] mx-auto block mb-2 px-4 py-3 rounded-xl border border-slate-200 font-semibold text-slate-900 focus:border-[#19CDFF] focus:outline-none"
          />
          <div className="max-w-[600px] mx-auto mb-4">
            <button onClick={aiSuggestSubjects} disabled={subjBusy} className="inline-flex items-center gap-1.5 text-xs font-bold text-violet-600 hover:text-violet-700 disabled:opacity-50" data-testid="builder-suggest-subjects">
              {subjBusy ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />} Suggest subject lines
            </button>
            {subjIdeas.length > 0 && (
              <div className="mt-2 flex flex-col gap-1.5" data-testid="subject-ideas">
                {subjIdeas.map((s, i) => (
                  <button key={i} onClick={() => { setSubject(s); setSubjIdeas([]); }} className="text-left text-sm px-3 py-2 rounded-lg bg-violet-50 text-slate-700 hover:bg-violet-100">{s}</button>
                ))}
              </div>
            )}
          </div>
          <div
            className={`mx-auto bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden transition-all ${device === 'mobile' ? 'max-w-[380px]' : 'max-w-[600px]'}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onCanvasDrop(e, blocks.length)}
            data-testid="builder-canvas"
          >
            {blocks.length === 0 && (
              <div className="p-12 text-center text-slate-400 text-sm">Drag blocks here, or click a block in the palette.</div>
            )}
            {blocks.map((b, i) => (
              <div
                key={b.id}
                draggable
                onDragStart={() => { dragIndex.current = i; }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.stopPropagation(); onCanvasDrop(e, i); }}
                onClick={() => setSelId(b.id)}
                data-testid={`canvas-block-${b.type}`}
                className={`relative group ${selId === b.id ? 'ring-2 ring-[#19CDFF]' : 'hover:ring-1 hover:ring-slate-200'} cursor-pointer`}
              >
                <div className="absolute top-1 right-1 z-10 hidden group-hover:flex items-center gap-0.5 bg-white/95 rounded-lg shadow border border-slate-200 p-0.5">
                  <span className="p-1 text-slate-300 cursor-grab"><GripVertical size={13} /></span>
                  <button onClick={(e) => { e.stopPropagation(); move(b.id, -1); }} className="p-1 text-slate-500 hover:text-slate-900"><ArrowUp size={13} /></button>
                  <button onClick={(e) => { e.stopPropagation(); move(b.id, 1); }} className="p-1 text-slate-500 hover:text-slate-900"><ArrowDown size={13} /></button>
                  <button onClick={(e) => { e.stopPropagation(); removeBlock(b.id); }} className="p-1 text-rose-500 hover:text-rose-700" data-testid={`block-delete-${b.type}`}><Trash2 size={13} /></button>
                </div>
                {/* eslint-disable-next-line react/no-danger */}
                <div dangerouslySetInnerHTML={{ __html: renderBlock(b) }} />
              </div>
            ))}
          </div>
        </main>

        {/* Properties */}
        <aside className="w-72 bg-white border-l border-slate-200 p-4 overflow-y-auto hidden lg:block shrink-0" data-testid="builder-props">
          {!sel && <p className="text-sm text-slate-400">Select a block to edit it.</p>}
          {sel && ['text', 'heading'].includes(sel.type) && (
            <button onClick={aiImproveSelected} disabled={aiBusy} className="w-full mb-3 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold text-white disabled:opacity-50" style={{ backgroundImage: 'linear-gradient(135deg,#7C3AED,#19CDFF)' }} data-testid="props-ai-improve">
              {aiBusy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />} Improve with AI
            </button>
          )}
          {sel && <BlockProps block={sel} update={updateProps} />}
        </aside>
      </div>

      {showAI && (
        <div className="fixed inset-0 z-[210] bg-black/40 flex items-center justify-center p-4" onClick={() => setShowAI(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="ai-compose-modal">
            <h3 className="flex items-center gap-2 font-bold text-lg text-slate-900 mb-1 pulse-font-heading"><Wand2 size={18} className="text-violet-600" />Write with AI</h3>
            <p className="text-sm text-slate-500 mb-4">Describe your email and we'll draft a branded starting point.</p>
            <textarea value={aiBrief} onChange={(e) => setAiBrief(e.target.value)} rows={4} placeholder="e.g. Invite lapsed members to a free comeback week with a personal training taster" className="w-full px-4 py-3 rounded-xl border border-slate-200 mb-4 focus:border-[#19CDFF] focus:outline-none" data-testid="ai-brief" />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowAI(false)} className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 hover:bg-slate-100">Cancel</button>
              <button onClick={aiGenerate} disabled={aiBusy} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold text-white disabled:opacity-50" style={{ backgroundImage: 'linear-gradient(135deg,#7C3AED,#19CDFF)' }} data-testid="ai-generate">{aiBusy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}Generate</button>
            </div>
          </div>
        </div>
      )}

      {showTest && (
        <div className="fixed inset-0 z-[210] bg-black/40 flex items-center justify-center p-4" onClick={() => setShowTest(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="test-send-modal">
            <h3 className="font-bold text-lg text-slate-900 mb-1 pulse-font-heading">Send a test email</h3>
            <p className="text-sm text-slate-500 mb-4">We'll save your changes and send a branded preview.</p>
            <input value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="you@example.com" className="w-full px-4 py-3 rounded-xl border border-slate-200 mb-4 focus:border-[#19CDFF] focus:outline-none" data-testid="test-send-email" />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowTest(false)} className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 hover:bg-slate-100">Cancel</button>
              <button onClick={sendTest} className="px-4 py-2 rounded-full text-sm font-bold text-[#03212b]" style={{ background: CYAN }} data-testid="test-send-confirm">Send test</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="mb-3">
      <label className="block text-[11px] uppercase tracking-wider font-bold text-slate-400 mb-1">{label}</label>
      {children}
    </div>
  );
}
const inputCls = 'w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:border-[#19CDFF] focus:outline-none';

function MergeTags({ onInsert }) {
  return (
    <div className="mb-3">
      <p className="flex items-center gap-1 text-[11px] uppercase tracking-wider font-bold text-slate-400 mb-1"><Sparkles size={11} />Merge tags</p>
      {Object.entries(MERGE_GROUPS).map(([g, tags]) => (
        <div key={g} className="mb-1.5">
          <span className="text-[10px] text-slate-400">{g}</span>
          <div className="flex flex-wrap gap-1 mt-0.5">
            {tags.map((t) => (
              <button key={t} onClick={() => onInsert(t)} className="text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 hover:bg-[#19CDFF22] font-mono" data-testid={`merge-${t.replace(/[{}]/g, '')}`}>{t}</button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function BlockProps({ block, update }) {
  const p = block.props || {};
  const appendText = (key) => (t) => update({ [key]: (p[key] || '') + ' ' + t });
  switch (block.type) {
    case 'heading':
      return (
        <div data-testid="props-heading">
          <Field label="Text"><input className={inputCls} value={p.text || ''} onChange={(e) => update({ text: e.target.value })} /></Field>
          <Field label="Size"><input type="number" className={inputCls} value={p.size || 24} onChange={(e) => update({ size: parseInt(e.target.value, 10) || 24 })} /></Field>
          <Field label="Align"><AlignSelect value={p.align} onChange={(v) => update({ align: v })} /></Field>
          <Field label="Colour"><input type="color" className="w-full h-9 rounded-lg border border-slate-200" value={p.color || '#0B1220'} onChange={(e) => update({ color: e.target.value })} /></Field>
          <MergeTags onInsert={appendText('text')} />
        </div>
      );
    case 'text':
      return (
        <div data-testid="props-text">
          <Field label="Text"><textarea rows={5} className={inputCls} value={p.text || ''} onChange={(e) => update({ text: e.target.value })} /></Field>
          <Field label="Align"><AlignSelect value={p.align} onChange={(v) => update({ align: v })} /></Field>
          <MergeTags onInsert={appendText('text')} />
        </div>
      );
    case 'button':
      return (
        <div data-testid="props-button">
          <Field label="Label"><input className={inputCls} value={p.text || ''} onChange={(e) => update({ text: e.target.value })} /></Field>
          <Field label="URL"><input className={inputCls} value={p.url || ''} onChange={(e) => update({ url: e.target.value })} /></Field>
          <Field label="Align"><AlignSelect value={p.align} onChange={(v) => update({ align: v })} /></Field>
          <Field label="Colour"><input type="color" className="w-full h-9 rounded-lg border border-slate-200" value={p.color || CYAN} onChange={(e) => update({ color: e.target.value })} /></Field>
          <MergeTags onInsert={appendText('url')} />
        </div>
      );
    case 'image':
      return (
        <div data-testid="props-image">
          <Field label="Image URL"><input className={inputCls} value={p.src || ''} onChange={(e) => update({ src: e.target.value })} /></Field>
          <Field label="Alt text"><input className={inputCls} value={p.alt || ''} onChange={(e) => update({ alt: e.target.value })} /></Field>
        </div>
      );
    case 'logo':
      return (
        <div data-testid="props-logo">
          <Field label="Logo URL"><input className={inputCls} value={p.src || ''} onChange={(e) => update({ src: e.target.value })} /></Field>
          <Field label="Align"><AlignSelect value={p.align} onChange={(v) => update({ align: v })} /></Field>
        </div>
      );
    case 'spacer':
      return <div data-testid="props-spacer"><Field label="Height (px)"><input type="number" className={inputCls} value={p.height || 24} onChange={(e) => update({ height: parseInt(e.target.value, 10) || 24 })} /></Field></div>;
    case 'video':
      return (
        <div data-testid="props-video">
          <Field label="Video URL"><input className={inputCls} value={p.url || ''} onChange={(e) => update({ url: e.target.value })} /></Field>
          <Field label="Thumbnail URL"><input className={inputCls} value={p.thumbnail || ''} onChange={(e) => update({ thumbnail: e.target.value })} /></Field>
        </div>
      );
    case 'html':
      return <div data-testid="props-html"><Field label="HTML"><textarea rows={8} className={`${inputCls} font-mono text-xs`} value={p.html || ''} onChange={(e) => update({ html: e.target.value })} /></Field></div>;
    case 'footer':
      return <div data-testid="props-footer"><Field label="Footer text"><textarea rows={4} className={inputCls} value={p.text || ''} onChange={(e) => update({ text: e.target.value })} /></Field><p className="text-[11px] text-slate-400">Unsubscribe & preference links are added automatically.</p></div>;
    case 'social':
      return (
        <div data-testid="props-social">
          {(p.links || []).map((l, i) => (
            <div key={i} className="flex gap-1 mb-2">
              <input className={inputCls} value={l.label} placeholder="Label" onChange={(e) => { const links = [...p.links]; links[i] = { ...l, label: e.target.value }; update({ links }); }} />
              <input className={inputCls} value={l.url} placeholder="URL" onChange={(e) => { const links = [...p.links]; links[i] = { ...l, url: e.target.value }; update({ links }); }} />
            </div>
          ))}
          <button onClick={() => update({ links: [...(p.links || []), { label: 'Link', url: '#' }] })} className="text-xs font-semibold text-[#0891b2]">+ Add link</button>
        </div>
      );
    default:
      return <p className="text-sm text-slate-400">No options for this block.</p>;
  }
}

function AlignSelect({ value, onChange }) {
  return (
    <select className={inputCls} value={value || 'left'} onChange={(e) => onChange(e.target.value)}>
      <option value="left">Left</option>
      <option value="center">Center</option>
      <option value="right">Right</option>
    </select>
  );
}
