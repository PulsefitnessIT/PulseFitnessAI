/**
 * GymAxis Help Centre — authenticated-only help + tutorial hub.
 *
 * Access: `/help` (and `/help/:guideId` for a specific guide). Linked from
 * the user dropdown in every module. NOT linked from any public page and
 * blocked via `<meta name="robots" content="noindex,nofollow">` to keep
 * the content off search engines (per user requirement).
 *
 * Layout: left category sidebar · main content · right AI assistant rail.
 * All data comes from `/api/help/*` — role-filtered server-side.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import {
  Search, Sparkles, BookOpen, ChevronRight, ArrowLeft, Clock, Star,
  CheckCircle2, AlertTriangle, LifeBuoy, Send, Lightbulb, X,
  GraduationCap, Zap, Users, Wrench, Settings, Megaphone, BarChart3,
  Plug, Bot, Rocket, Newspaper,
} from 'lucide-react';
import { useAuth } from '@/App';
import Navbar from '@/components/shared/Navbar';
import { startWalkthrough, getCompletedWalkthroughs } from '@/components/shared/GuidedTour';

// Category-id → Lucide icon (falls back to BookOpen). Keeps the sidebar
// visually distinctive without depending on fragile per-guide iconography.
const CATEGORY_ICON = {
  'getting-started': Rocket,
  'release-notes':   Newspaper,
  'crm':             Users,
  'service':         Wrench,
  'memberships':     GraduationCap,
  'marketing':       Megaphone,
  'staff':           Users,
  'staffing':        Users,
  'reporting':       BarChart3,
  'admin':           Settings,
  'integrations':    Plug,
  'ai':              Bot,
};

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function HelpCentrePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { guideId } = useParams();
  const [searchParams] = useSearchParams();
  const moduleHint = searchParams.get('module');
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [categories, setCategories] = useState([]);
  const [activeCat, setActiveCat] = useState(moduleHint ? null : 'all');
  const [guides, setGuides] = useState([]);
  const [popular, setPopular] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentGuide, setCurrentGuide] = useState(null);
  const [guideLoading, setGuideLoading] = useState(false);
  const [q, setQ] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [showSupport, setShowSupport] = useState(false);

  // Redirect unauthenticated users to login (rather than 401-ing).
  useEffect(() => {
    if (!token) navigate('/login', { replace: true });
  }, [token, navigate]);

  // Inject noindex meta tag on mount/unmount. Plain DOM manipulation
  // (no react-helmet) — title is set separately to follow the brand.
  useEffect(() => {
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex,nofollow,noarchive';
    meta.setAttribute('data-help-noindex', 'true');
    document.head.appendChild(meta);
    return () => {
      if (meta.parentNode) meta.parentNode.removeChild(meta);
    };
  }, []);

  // Load categories + popular rail on mount.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      axios.get(`${API}/help/categories`, { headers }).then(r => r.data).catch(() => ({ categories: [] })),
      axios.get(`${API}/help/guides`, { headers, params: { popular: true } }).then(r => r.data).catch(() => ({ guides: [] })),
    ]).then(([catResp, popResp]) => {
      if (cancelled) return;
      setCategories(catResp.categories || []);
      setPopular(popResp.guides || []);
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [headers, token]);

  // Load guides for the active category (or all, or module-filtered).
  const loadGuides = useCallback(() => {
    if (!token) return;
    const params = {};
    if (activeCat && activeCat !== 'all') params.category = activeCat;
    if (moduleHint && activeCat === null) params.module = moduleHint;
    axios.get(`${API}/help/guides`, { headers, params })
      .then(r => setGuides(r.data.guides || []))
      .catch(() => setGuides([]));
  }, [activeCat, moduleHint, headers, token]);

  useEffect(() => { if (!guideId) loadGuides(); }, [loadGuides, guideId]);

  // Load a single guide's full body when the route parameter changes.
  useEffect(() => {
    if (!guideId || !token) { setCurrentGuide(null); return; }
    setGuideLoading(true);
    axios.get(`${API}/help/guides/${guideId}`, { headers })
      .then(r => setCurrentGuide(r.data))
      .catch(() => setCurrentGuide(null))
      .finally(() => setGuideLoading(false));
  }, [guideId, headers, token]);

  // Debounced live search.
  const [capabilityResults, setCapabilityResults] = useState([]);
  useEffect(() => {
    if (!q || q.length < 2) { setSearchResults(null); setCapabilityResults([]); return; }
    const t = setTimeout(() => {
      axios.get(`${API}/help/search`, { headers, params: { q } })
        .then(r => {
          setSearchResults(r.data.results || []);
          setCapabilityResults(r.data.capabilities || []);
        })
        .catch(() => { setSearchResults([]); setCapabilityResults([]); });
    }, 250);
    return () => clearTimeout(t);
  }, [q, headers]);

  const openGuide = (id) => { setQ(''); setSearchResults(null); navigate(`/help/${id}`); };
  const backToList = () => navigate('/help');

  // Brand the user sees — drives every "GymAxis" → "Pulse Fitness"
  // swap. Backend also white-labels content; this just keeps the UI
  // chrome (titles, subtitles, AI rail header) consistent.
  const brand = useMemo(() => {
    const accountType = (user?.account_type || '').toLowerCase();
    const isPulse = accountType === 'pulse_pro' || accountType === 'lite';
    return isPulse
      ? { id: 'pulse',   name: 'Pulse Fitness', assistantHeading: 'Ask Pulse Fitness' }
      : { id: 'gymaxis', name: 'GymAxis',       assistantHeading: 'Ask GymAxis' };
  }, [user?.account_type]);

  // Keep the document title in sync with the active brand.
  useEffect(() => {
    document.title = `Help Centre · ${brand.name}`;
  }, [brand.name]);

  if (!token || !user) return null;

  return (
    <div className="min-h-screen pulse-font-body" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }} data-testid="help-centre">
        <Navbar />

        {/* Hero — pt-24 matches every other module (Navbar is fixed top). */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <LifeBuoy size={16} style={{ color: 'var(--color-brand-cyan)' }} />
                <div className="text-[11px] font-bold uppercase tracking-[0.18em]" style={{ color: 'var(--color-brand-cyan)' }}>Help Centre</div>
              </div>
              <h1 className="text-3xl sm:text-4xl font-semibold pulse-font-heading tracking-tight mb-2" style={{ color: 'var(--theme-text)' }}>
                How can we help?
              </h1>
              <p className="text-sm mb-5" style={{ color: 'var(--theme-text-muted)' }} data-testid="help-subtitle">
                Step-by-step guides, best practices, and an AI assistant that&apos;s trained only on {brand.name}.
              </p>
            </div>
            <button
              onClick={() => setShowSupport(true)}
              className="inline-flex items-center gap-1.5 mt-1 px-3 py-2 text-xs font-semibold rounded-md bg-[var(--color-brand-cyan)] text-zinc-900 hover:brightness-95 flex-shrink-0"
              data-testid="help-log-support-btn"
            >
              <LifeBuoy size={13} /> Log a support ticket
            </button>
          </div>

          {/* Global search */}
          <div className="relative max-w-2xl">
            <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search for a guide, feature, or 'how do I…'"
              className="w-full h-12 pl-11 pr-12 rounded-full text-sm focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
              style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="help-search-input"
            />
            {q && (
              <button type="button" onClick={() => { setQ(''); setSearchResults(null); }} className="absolute right-4 top-1/2 -translate-y-1/2 opacity-60 hover:opacity-100" aria-label="Clear" data-testid="help-search-clear">
                <X size={14} style={{ color: 'var(--theme-text-muted)' }} />
              </button>
            )}
            {searchResults && searchResults.length > 0 && (
              <div
                className="absolute left-0 right-0 top-full mt-2 rounded-2xl border z-10 overflow-hidden"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
                data-testid="help-search-results"
              >
                {capabilityResults && capabilityResults.length > 0 && (
                  <div className="px-3 py-2 text-[10px] uppercase tracking-wide font-bold" style={{ color: 'var(--theme-text-muted)', borderBottom: '1px solid var(--theme-border)' }}>
                    Jump to feature
                  </div>
                )}
                {capabilityResults && capabilityResults.map((cap, idx) => (
                  <button
                    key={`cap-${idx}`}
                    type="button"
                    onClick={() => { setQ(''); setSearchResults(null); navigate(cap.url); }}
                    className="w-full text-left px-4 py-3 hover:bg-[color:var(--theme-bg)] transition-colors flex items-start gap-3"
                    data-testid={`help-capability-result-${idx}`}
                  >
                    <Search size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--color-brand-cyan)' }} />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold pulse-font-heading truncate" style={{ color: 'var(--theme-text)' }}>{cap.title}</div>
                      <div className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>{cap.summary}</div>
                    </div>
                  </button>
                ))}
                {searchResults.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => openGuide(r.id)}
                    className="w-full text-left px-4 py-3 hover:bg-[color:var(--theme-bg)] transition-colors flex items-start gap-3"
                    data-testid={`help-search-result-${r.id}`}
                  >
                    <BookOpen size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--color-brand-cyan)' }} />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold pulse-font-heading truncate" style={{ color: 'var(--theme-text)' }}>{r.title}</div>
                      <div className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>{r.description}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
            {searchResults && searchResults.length === 0 && q.length >= 2 && (
              <div
                className="absolute left-0 right-0 top-full mt-2 rounded-2xl border p-4 z-10 text-sm"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
              >
                No guides match "{q}" — try another phrase, ask the AI assistant on the right, or{' '}
                <button
                  type="button"
                  onClick={() => setShowSupport(true)}
                  className="underline font-semibold"
                  style={{ color: 'var(--color-brand-cyan)' }}
                  data-testid="help-search-empty-support"
                >
                  log a support ticket
                </button>
                .
              </div>
            )}
          </div>
        </div>

        {/* Body: sidebar + content + AI rail */}
        <div className="max-w-7xl mx-auto px-4 md:px-8 pb-12 grid grid-cols-1 lg:grid-cols-[220px_1fr_340px] gap-6">
          {/* Sidebar: categories */}
          <aside className="hidden lg:block">
            <div className="sticky top-24">
              <CategoryList
                categories={[{ id: 'all', label: 'All guides', count: categories.reduce((s, c) => s + (c.count || 0), 0) }, ...categories]}
                activeCat={activeCat}
                onSelect={(id) => { setActiveCat(id); if (guideId) navigate('/help'); }}
              />
            </div>
          </aside>

          {/* Main */}
          <main className="min-w-0" data-testid="help-main">
            {/* Mobile category chips */}
            <div className="lg:hidden mb-4 flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1">
              {[{ id: 'all', label: 'All guides' }, ...categories].map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => { setActiveCat(c.id); if (guideId) navigate('/help'); }}
                  className="flex-shrink-0 px-4 py-2 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
                  style={activeCat === c.id
                    ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                    : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
                  data-testid={`help-cat-mobile-${c.id}`}
                >
                  {c.label}
                </button>
              ))}
            </div>

            {guideId ? (
              <GuideDetail guide={currentGuide} loading={guideLoading} onBack={backToList} onOpen={openGuide} />
            ) : (
              <GuideListView
                activeCat={activeCat}
                categories={categories}
                guides={guides}
                popular={popular}
                onOpen={openGuide}
                loading={loading}
              />
            )}
          </main>

          {/* AI Assistant rail */}
          <aside className="hidden lg:block">
            <div className="sticky top-24">
              <HelpAssistantRail
                headers={headers}
                currentModule={moduleHint}
                currentGuide={currentGuide}
                onOpenGuide={openGuide}
                brand={brand}
              />
            </div>
          </aside>

          {/* Mobile: AI assistant appears after list */}
          <div className="lg:hidden">
            <HelpAssistantRail
              headers={headers}
              currentModule={moduleHint}
              currentGuide={currentGuide}
              onOpenGuide={openGuide}
              brand={brand}
            />
          </div>
        </div>
        {showSupport && (
          <SupportTicketModal
            API={API}
            headers={headers}
            onClose={() => setShowSupport(false)}
          />
        )}
      </div>
  );
}

// ───────────────────────────── Subcomponents ──────────────────────

function CategoryList({ categories, activeCat, onSelect }) {
  return (
    <nav aria-label="Help categories" className="space-y-1" data-testid="help-categories">
      {categories.map((c) => {
        const Icon = CATEGORY_ICON[c.id] || BookOpen;
        const active = activeCat === c.id;
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => onSelect(c.id)}
            className="w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors"
            style={active
              ? { background: 'var(--color-brand-cyan)15', border: '1px solid var(--color-brand-cyan)' }
              : { background: 'transparent', border: '1px solid transparent' }}
            data-testid={`help-cat-${c.id}`}
          >
            <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: active ? 'var(--color-brand-cyan)' : 'var(--theme-surface)', color: active ? 'var(--color-ink)' : 'var(--color-brand-cyan)' }}>
              <Icon size={14} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold truncate pulse-font-heading" style={{ color: active ? 'var(--theme-text)' : 'var(--theme-text)' }}>{c.label}</div>
              {c.blurb && <div className="text-[11px] truncate" style={{ color: 'var(--theme-text-muted)' }}>{c.blurb}</div>}
            </div>
            {typeof c.count === 'number' && c.count > 0 && (
              <div className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full" style={{ background: 'var(--theme-surface)', color: 'var(--theme-text-muted)' }}>{c.count}</div>
            )}
          </button>
        );
      })}
    </nav>
  );
}

function GuideListView({ activeCat, categories, guides, popular, onOpen, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="help-loading">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-2xl p-5 border animate-pulse" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', minHeight: 120 }} />
        ))}
      </div>
    );
  }

  const catLabel = activeCat && activeCat !== 'all'
    ? categories.find(c => c.id === activeCat)?.label
    : null;

  return (
    <div className="space-y-8">
      {/* Most popular rail — only on 'all' view */}
      {(!activeCat || activeCat === 'all') && popular && popular.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Star size={14} style={{ color: 'var(--color-warning)' }} />
            <div className="text-[11px] font-bold uppercase tracking-[0.18em]" style={{ color: 'var(--color-brand-cyan)' }}>Most popular</div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {popular.slice(0, 4).map((g) => <GuideCard key={g.id} guide={g} onOpen={onOpen} />)}
          </div>
        </section>
      )}

      <section>
        <div className="flex items-center gap-2 mb-3">
          <BookOpen size={14} style={{ color: 'var(--color-brand-cyan)' }} />
          <div className="text-[11px] font-bold uppercase tracking-[0.18em]" style={{ color: 'var(--color-brand-cyan)' }}>
            {catLabel ? catLabel : 'All guides'}
          </div>
          <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{guides.length} article{guides.length === 1 ? '' : 's'}</div>
        </div>
        {guides.length === 0 ? (
          <div className="rounded-2xl p-8 border text-center" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>
            No guides available for your role in this category yet.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {guides.map((g) => <GuideCard key={g.id} guide={g} onOpen={onOpen} />)}
          </div>
        )}
      </section>
    </div>
  );
}

function GuideCard({ guide, onOpen }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(guide.id)}
      className="group text-left rounded-2xl p-5 border transition-all hover:-translate-y-0.5 hover:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid={`help-guide-card-${guide.id}`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {guide.popular && <Star size={12} style={{ color: 'var(--color-warning)' }} />}
          <div className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-brand-cyan)' }}>{guide.category?.replace('-', ' ')}</div>
        </div>
        <ChevronRight size={16} className="opacity-40 group-hover:opacity-100 transition-opacity" style={{ color: 'var(--color-brand-cyan)' }} />
      </div>
      <div className="text-base font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{guide.title}</div>
      <div className="text-xs mb-3 leading-relaxed" style={{ color: 'var(--theme-text-muted)' }}>{guide.description}</div>
      <div className="flex items-center gap-1 text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
        <Clock size={11} /> {guide.read_minutes || 2} min read
      </div>
    </button>
  );
}

function GuideDetail({ guide, loading, onBack, onOpen }) {
  if (loading) return <div className="rounded-2xl p-8 border animate-pulse" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', minHeight: 400 }} />;
  if (!guide) return (
    <div className="rounded-2xl p-8 border text-center" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
      <div className="text-sm font-semibold mb-2">Guide not found</div>
      <button type="button" onClick={onBack} className="btn-secondary" data-testid="help-back-btn"><ArrowLeft size={12} /> Back to list</button>
    </div>
  );

  return (
    <article data-testid={`help-guide-detail-${guide.id}`}>
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-xs mb-4 opacity-70 hover:opacity-100" style={{ color: 'var(--theme-text-muted)' }} data-testid="help-back-btn">
        <ArrowLeft size={12} /> Back to guides
      </button>
      <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>{guide.category?.replace('-', ' ')}</div>
      <h1 className="text-2xl sm:text-3xl font-semibold mb-2 pulse-font-heading tracking-tight" style={{ color: 'var(--theme-text)' }}>{guide.title}</h1>
      <div className="text-sm mb-4 leading-relaxed" style={{ color: 'var(--theme-text-muted)' }}>{guide.description}</div>
      <div className="flex items-center gap-3 text-[11px] mb-6 flex-wrap" style={{ color: 'var(--theme-text-muted)' }}>
        <span className="inline-flex items-center gap-1"><Clock size={11} /> {guide.read_minutes || 2} min read</span>
        {guide.updated_at && <span>Updated {guide.updated_at}</span>}
      </div>

      {/* Walkthrough — only renders when the guide has one. Reuses
          GuidedTour (Joyride) so the user is taught inside the live
          UI itself, not just on this page. */}
      {guide.walkthrough && Array.isArray(guide.walkthrough.steps) && guide.walkthrough.steps.length > 0 && (
        <div
          className="mb-6 rounded-2xl p-4 border flex items-start gap-3"
          style={{ background: 'rgba(25,205,255,0.06)', borderColor: 'var(--color-brand-cyan)55' }}
          data-testid="help-walkthrough-cta"
        >
          <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
            <Zap size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold mb-0.5 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>
              {getCompletedWalkthroughs().includes(guide.id) ? 'Run the walkthrough again' : 'Try it with a guided walkthrough'}
            </div>
            <div className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>
              We'll take you to the right module and highlight every click — no instructions to read mid-flow.
            </div>
            <button
              type="button"
              onClick={() => startWalkthrough({
                tourId: guide.id,
                steps: guide.walkthrough.steps,
                initialRoute: guide.walkthrough.initial_route,
              })}
              className="text-xs font-semibold inline-flex items-center gap-1.5 rounded-full px-3.5 h-8 transition-colors"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}
              data-testid={`help-walkthrough-start-${guide.id}`}
            >
              <Sparkles size={12} /> Start walkthrough
            </button>
          </div>
        </div>
      )}

      {/* Steps */}
      {guide.steps && guide.steps.length > 0 && (
        <section className="mb-8" data-testid="help-guide-steps">
          <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>Step by step</div>
          <ol className="space-y-3">
            {guide.steps.map((s, i) => (
              <li key={i} className="rounded-2xl p-4 border flex items-start gap-3" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
                <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold pulse-font-heading" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
                  {i + 1}
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{s.title}</div>
                  <div className="text-sm leading-relaxed" style={{ color: 'var(--theme-text-muted)' }}>{s.body}</div>
                  {s.ui_hint && (
                    <div className="mt-2 text-xs inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full" style={{ background: 'var(--theme-bg)', color: 'var(--color-brand-cyan)', border: '1px solid var(--color-brand-cyan)33' }}>
                      <Zap size={10} /> {s.ui_hint}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Tips */}
      {guide.tips && guide.tips.length > 0 && (
        <section className="mb-8" data-testid="help-guide-tips">
          <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-success)' }}>Best-practice tips</div>
          <ul className="space-y-2">
            {guide.tips.map((t, i) => (
              <li key={i} className="rounded-xl p-3 border flex items-start gap-2" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
                <Lightbulb size={14} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--color-warning)' }} />
                <div className="text-sm leading-relaxed" style={{ color: 'var(--theme-text)' }}>{t}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Common mistakes */}
      {guide.mistakes && guide.mistakes.length > 0 && (
        <section className="mb-8" data-testid="help-guide-mistakes">
          <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-danger)' }}>Common mistakes to avoid</div>
          <ul className="space-y-2">
            {guide.mistakes.map((m, i) => (
              <li key={i} className="rounded-xl p-3 border flex items-start gap-2" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
                <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--color-danger)' }} />
                <div className="text-sm leading-relaxed" style={{ color: 'var(--theme-text)' }}>{m}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Related */}
      {guide.related_resolved && guide.related_resolved.length > 0 && (
        <section data-testid="help-guide-related">
          <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>Related actions</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {guide.related_resolved.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => onOpen(r.id)}
                className="text-left rounded-xl p-3 border flex items-center gap-3 transition-colors hover:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
                style={{ background: 'transparent', borderColor: 'var(--theme-border)' }}
                data-testid={`help-related-${r.id}`}
              >
                <CheckCircle2 size={14} className="flex-shrink-0" style={{ color: 'var(--color-brand-cyan)' }} />
                <div className="text-sm flex-1 min-w-0 pulse-font-heading truncate" style={{ color: 'var(--theme-text)' }}>{r.title}</div>
                <ChevronRight size={14} className="opacity-50" style={{ color: 'var(--theme-text-muted)' }} />
              </button>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}

function HelpAssistantRail({ headers, currentModule, currentGuide, onOpenGuide, brand }) {
  const intro = `Hi! Ask me anything about ${brand?.name || 'GymAxis'}. I'm trained on every Help Centre guide and won't make things up.`;
  const [messages, setMessages] = useState([
    { role: 'assistant', text: intro },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const scrollerRef = useRef(null);

  // Re-seed the intro line whenever the brand changes (e.g. role
  // switch) so the rail never displays the wrong brand name.
  useEffect(() => {
    setMessages((prev) => prev.length === 1 && prev[0].role === 'assistant' ? [{ role: 'assistant', text: intro }] : prev);
  }, [intro]);

  useEffect(() => {
    if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages]);

  const ask = async (e) => {
    e?.preventDefault?.();
    const q = input.trim();
    if (!q || sending) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', text: q }]);
    setSending(true);
    try {
      const resp = await axios.post(`${API}/help/ask`, {
        question: q,
        current_module: currentModule || currentGuide?.module || null,
      }, { headers });
      const { answer, guide_ids } = resp.data || {};
      setMessages((prev) => [...prev, { role: 'assistant', text: answer || 'Sorry, no answer.', guideIds: guide_ids || [] }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', text: 'I had trouble reaching the assistant. Try again in a moment.' }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="rounded-2xl border p-4 flex flex-col" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', maxHeight: '70vh' }} data-testid="help-ai-rail">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Sparkles size={14} /></div>
        <div className="min-w-0">
          <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }} data-testid="help-ai-heading">{brand?.assistantHeading || 'Ask GymAxis'}</div>
          <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>Guide-grounded · never invents features</div>
        </div>
      </div>
      <div ref={scrollerRef} className="flex-1 overflow-y-auto space-y-3 pr-1 mb-3" style={{ minHeight: 180 }} data-testid="help-ai-messages">
        {messages.map((m, i) => (
          <div key={i} className="text-sm leading-relaxed" data-testid={`help-ai-msg-${m.role}`}>
            {m.role === 'assistant' ? (
              <>
                <div className="rounded-xl p-3" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }}>{m.text}</div>
                {m.guideIds && m.guideIds.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.guideIds.map((gid) => (
                      <button
                        key={gid}
                        type="button"
                        onClick={() => onOpenGuide(gid)}
                        className="text-[11px] inline-flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors hover:border-[rgb(var(--rgb-brand-cyan)/0.8)]"
                        style={{ background: 'transparent', border: '1px solid var(--theme-border)', color: 'var(--color-brand-cyan)' }}
                        data-testid={`help-ai-source-${gid}`}
                      >
                        <BookOpen size={10} /> {gid}
                      </button>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="rounded-xl p-3 ml-6 text-right" style={{ background: 'var(--color-brand-cyan)15', color: 'var(--theme-text)' }}>{m.text}</div>
            )}
          </div>
        ))}
        {sending && (
          <div className="text-xs inline-flex items-center gap-1.5" style={{ color: 'var(--theme-text-muted)' }}>
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-brand-cyan)' }} /> Thinking…
          </div>
        )}
      </div>
      <form onSubmit={ask} className="flex items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          className="flex-1 h-10 px-4 rounded-full text-sm focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
          style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
          data-testid="help-ai-input"
        />
        <button
          type="submit"
          disabled={!input.trim() || sending}
          className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}
          data-testid="help-ai-send"
          aria-label="Send"
        >
          <Send size={14} />
        </button>
      </form>
    </div>
  );
}



/* ─────────────────── Support ticket modal ─────────────────── */

function SupportTicketModal({ API, headers, onClose }) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const submit = async () => {
    if (!reason.trim() || reason.trim().length < 10) {
      return;
    }
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${API}/support/escalate`,
        { reason, last_message: reason, session_id: `helpcentre-${Date.now()}` },
        { headers },
      );
      setResult(r.data);
    } catch (e) {
      setResult({ success: false, error: e?.response?.data?.detail || 'Failed to log ticket' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60"
      data-testid="help-support-dialog"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-100">
          <div className="flex items-center gap-2">
            <LifeBuoy size={16} className="text-[var(--color-brand-cyan)]" />
            <h3 className="text-base font-semibold text-zinc-900">Log a support ticket</h3>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-zinc-100 rounded" data-testid="help-support-close">
            <X size={16} />
          </button>
        </div>
        <div className="p-5 space-y-3 text-sm">
          {result ? (
            result.success ? (
              <>
                <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-emerald-800" data-testid="help-support-success">
                  <div className="font-bold">Ticket logged.</div>
                  <div className="mt-1 text-xs">
                    Reference: <span className="font-mono">{result.case_ref}</span>
                  </div>
                  {result.email_sent ? (
                    <div className="mt-1 text-xs">Our team has been notified by email — we'll be in touch shortly.</div>
                  ) : (
                    <div className="mt-1 text-xs">Saved to the support queue. Email notification was unavailable; the team will see this on their next check.</div>
                  )}
                </div>
                <div className="flex justify-end pt-2">
                  <button
                    onClick={onClose}
                    className="px-4 py-1.5 text-sm font-semibold rounded bg-[var(--color-brand-cyan)] text-zinc-900"
                    data-testid="help-support-done"
                  >
                    Done
                  </button>
                </div>
              </>
            ) : (
              <div className="rounded-md bg-rose-50 border border-rose-200 p-3 text-rose-800">
                {result.error || 'Failed to log ticket — please try again or email support@gymaxisai.com.'}
              </div>
            )
          ) : (
            <>
              <p className="text-zinc-600 leading-relaxed">
                Tell us what you were trying to do and where it went wrong. We'll get back to you on the email you logged in with.
              </p>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={6}
                placeholder="e.g. I tried to add a piece of equipment in the maintenance module but the photo upload kept failing on iPhone Safari…"
                className="w-full px-3 py-2 rounded border border-zinc-200 text-sm"
                data-testid="help-support-reason"
                autoFocus
              />
              <div className="text-[11px] text-zinc-400">
                {reason.trim().length < 10 ? `${10 - reason.trim().length} more characters needed.` : `${reason.length} characters.`}
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-100">
                <button onClick={onClose} className="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
                <button
                  onClick={submit}
                  disabled={submitting || reason.trim().length < 10}
                  className="px-4 py-1.5 text-sm font-semibold rounded bg-[var(--color-brand-cyan)] text-zinc-900 disabled:opacity-50"
                  data-testid="help-support-submit"
                >
                  {submitting ? 'Sending…' : 'Submit ticket'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
