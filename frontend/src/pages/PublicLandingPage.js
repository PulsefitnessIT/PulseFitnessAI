import { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams } from 'react-router-dom';
import { useAuth } from '@/App';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, CheckCircle2 } from 'lucide-react';

/**
 * Iter 228 — Public landing page.
 *
 * Mounted at /p/:slug. Renders hero + body + (optional) embedded form.
 * Tracks pageviews + UTM via /api/marketing/pages/by-slug/:slug/visit.
 */
const PublicLandingPage = () => {
  const { slug } = useParams();
  const { API } = useAuth();
  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [values, setValues] = useState({});
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(null);
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/marketing/pages/by-slug/${encodeURIComponent(slug)}`)
      .then((r) => {
        if (cancelled) return;
        setPage(r.data);
        // Update SEO tags
        if (r.data?.seo_title) document.title = r.data.seo_title;
        if (r.data?.seo_description) {
          let m = document.querySelector("meta[name='description']");
          if (!m) {
            m = document.createElement('meta');
            m.setAttribute('name', 'description');
            document.head.appendChild(m);
          }
          m.setAttribute('content', r.data.seo_description);
        }
        // Track visit (best-effort)
        const utm = {};
        const sp = new URLSearchParams(window.location.search);
        ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach((k) => {
          if (sp.get(k)) utm[k] = sp.get(k);
        });
        axios.post(`${API}/marketing/pages/by-slug/${encodeURIComponent(slug)}/visit`, {
          utm, user_agent: navigator.userAgent,
        }).catch(() => {});
      })
      .catch((e) => { if (!cancelled) setError(e.response?.data?.detail || 'Page not found'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [API, slug]);

  const setVal = (id, v) => setValues((s) => ({ ...s, [id]: v }));

  const submitEmbeddedForm = async (e) => {
    e.preventDefault();
    const form = page.form;
    if (!form) return;
    if (form.require_consent && !consent) { setFormError('Please tick consent.'); return; }
    setFormError(null); setSubmitting(true);
    try {
      const utm = {};
      const sp = new URLSearchParams(window.location.search);
      ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach((k) => {
        if (sp.get(k)) utm[k] = sp.get(k);
      });
      const r = await axios.post(`${API}/marketing/forms/by-slug/${encodeURIComponent(form.slug)}/submit`, {
        values, consent, user_agent: navigator.userAgent, utm,
      });
      setSuccess(r.data);
      if (r.data.redirect_url) window.location.href = r.data.redirect_url;
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Could not submit form.');
    }
    setSubmitting(false);
  };

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-white">
      <Loader2 size={28} className="animate-spin text-zinc-400" />
    </div>
  );
  if (!page) return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50">
      <p className="text-zinc-600 text-center">{error || 'Page not found'}</p>
    </div>
  );

  return (
    <div className="min-h-screen bg-white" data-testid="public-landing-page">
      {/* Hero */}
      <section className="bg-zinc-900 text-white py-16 px-6">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight mb-3" data-testid="public-page-title">
            {page.title}
          </h1>
          {page.subtitle && <p className="text-zinc-300 text-lg max-w-2xl" data-testid="public-page-subtitle">{page.subtitle}</p>}
          {page.cta_label && page.cta_url && (
            <a
              href={page.cta_url}
              className="inline-block mt-6 bg-white text-zinc-900 px-6 py-3 rounded-md font-medium hover:bg-zinc-100"
              data-testid="public-page-cta"
            >
              {page.cta_label}
            </a>
          )}
        </div>
      </section>

      {/* Optional hero image */}
      {page.hero_image_url && (
        <section className="max-w-4xl mx-auto px-6 -mt-10">
          <img src={page.hero_image_url} alt={page.title} className="w-full rounded-lg shadow-lg border border-zinc-200" />
        </section>
      )}

      {/* Body */}
      {page.body_markdown && (
        <section className="max-w-3xl mx-auto px-6 py-12 prose prose-zinc">
          {/* Light markdown — paragraphs split on double newline. Heavy lifting deferred. */}
          {page.body_markdown.split(/\n{2,}/).map((para, i) => (
            <p key={i} className="text-zinc-700 leading-relaxed mb-4">{para}</p>
          ))}
        </section>
      )}

      {/* Embedded form */}
      {page.form && !success && (
        <section className="max-w-lg mx-auto px-6 pb-16">
          <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-6" data-testid="public-page-form">
            <h2 className="text-xl font-semibold text-zinc-900 mb-4">{page.form.name}</h2>
            <form onSubmit={submitEmbeddedForm} className="space-y-3">
              {page.form.fields.map((f) => (
                <div key={f.id}>
                  <Label className="text-zinc-700 text-sm">
                    {f.label} {f.required && <span className="text-rose-500">*</span>}
                  </Label>
                  {f.field_type === 'textarea' ? (
                    <Textarea value={values[f.id] || ''} onChange={(e) => setVal(f.id, e.target.value)} required={f.required} rows={3} className="mt-1" />
                  ) : f.field_type === 'select' ? (
                    <select
                      value={values[f.id] || ''}
                      onChange={(e) => setVal(f.id, e.target.value)}
                      required={f.required}
                      className="mt-1 w-full bg-white border border-zinc-200 rounded-md px-3 py-2 text-sm"
                    >
                      <option value="">— Select —</option>
                      {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : f.field_type === 'checkbox' ? (
                    <label className="flex items-center gap-2 mt-1 text-sm text-zinc-700">
                      <input type="checkbox" checked={!!values[f.id]} onChange={(e) => setVal(f.id, e.target.checked)} required={f.required} />
                      {f.placeholder || 'Yes'}
                    </label>
                  ) : (
                    <Input
                      type={f.field_type === 'email' ? 'email' : f.field_type === 'phone' ? 'tel' : f.field_type === 'number' ? 'number' : 'text'}
                      value={values[f.id] || ''} onChange={(e) => setVal(f.id, e.target.value)}
                      required={f.required} placeholder={f.placeholder} className="mt-1"
                    />
                  )}
                </div>
              ))}
              {page.form.require_consent && (
                <label className="flex items-start gap-2 mt-2 text-xs text-zinc-600">
                  <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} required className="mt-1" />
                  <span>{page.form.consent_text}</span>
                </label>
              )}
              {formError && <p className="text-rose-600 text-sm">{formError}</p>}
              <Button type="submit" disabled={submitting} className="w-full bg-zinc-900 hover:bg-zinc-800 text-white">
                {submitting ? 'Submitting…' : (page.form.submit_button_label || 'Submit')}
              </Button>
            </form>
          </div>
        </section>
      )}

      {success && (
        <section className="max-w-md mx-auto px-6 pb-16">
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-6 text-center">
            <CheckCircle2 size={32} className="mx-auto text-emerald-500 mb-2" />
            <p className="text-zinc-900">{success.success_message || "Thanks — we'll be in touch."}</p>
          </div>
        </section>
      )}
    </div>
  );
};

export default PublicLandingPage;
