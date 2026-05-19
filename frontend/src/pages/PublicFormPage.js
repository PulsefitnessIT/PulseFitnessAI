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
 * Iter 228 — Public hosted form.
 *
 * Mounted at /forms/:slug and /forms/:slug.html (no auth required).
 * Reuses our shadcn primitives so it inherits brand fonts/colours.
 */
const PublicFormPage = () => {
  const { slug } = useParams();
  const { API } = useAuth();
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [values, setValues] = useState({});
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/marketing/forms/by-slug/${encodeURIComponent(slug)}`)
      .then((r) => { if (!cancelled) setForm(r.data); })
      .catch((e) => { if (!cancelled) setError(e.response?.data?.detail || 'Form not found'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [API, slug]);

  const setVal = (id, v) => setValues((s) => ({ ...s, [id]: v }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (form.require_consent && !consent) {
      setError('Please tick the consent checkbox.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const utm = {};
      const sp = new URLSearchParams(window.location.search);
      ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach((k) => {
        if (sp.get(k)) utm[k] = sp.get(k);
      });
      const r = await axios.post(`${API}/marketing/forms/by-slug/${encodeURIComponent(slug)}/submit`, {
        values, consent,
        user_agent: navigator.userAgent,
        utm,
      });
      setSuccess(r.data);
      if (r.data.redirect_url) window.location.href = r.data.redirect_url;
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not submit form. Please try again.');
    }
    setSubmitting(false);
  };

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50">
      <Loader2 size={28} className="animate-spin text-zinc-400" />
    </div>
  );
  if (!form) return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50">
      <p className="text-zinc-600 text-center">{error || 'Form not found'}</p>
    </div>
  );

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 px-4">
        <div className="max-w-md w-full bg-white border border-zinc-200 rounded-lg p-8 text-center" data-testid="form-success">
          <CheckCircle2 size={48} className="mx-auto text-emerald-500 mb-3" />
          <p className="text-lg text-zinc-900">{success.success_message || "Thanks — we'll be in touch."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 py-12 px-4">
      <div className="max-w-lg mx-auto bg-white border border-zinc-200 rounded-lg p-8" data-testid="public-form">
        <h1 className="text-2xl font-semibold text-zinc-900 mb-2">{form.name}</h1>
        {form.description && <p className="text-zinc-600 text-sm mb-6">{form.description}</p>}

        <form onSubmit={onSubmit} className="space-y-4">
          {form.fields.map((f) => (
            <div key={f.id}>
              <Label className="text-zinc-700 text-sm">
                {f.label} {f.required && <span className="text-rose-500">*</span>}
              </Label>
              {f.field_type === 'textarea' ? (
                <Textarea
                  value={values[f.id] || ''}
                  onChange={(e) => setVal(f.id, e.target.value)}
                  required={f.required}
                  placeholder={f.placeholder}
                  rows={3}
                  className="mt-1"
                  data-testid={`public-form-field-${f.id}`}
                />
              ) : f.field_type === 'select' ? (
                <select
                  value={values[f.id] || ''}
                  onChange={(e) => setVal(f.id, e.target.value)}
                  required={f.required}
                  className="mt-1 w-full bg-white border border-zinc-200 rounded-md px-3 py-2 text-sm"
                  data-testid={`public-form-field-${f.id}`}
                >
                  <option value="">— Select —</option>
                  {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : f.field_type === 'checkbox' ? (
                <label className="flex items-center gap-2 mt-1 text-sm text-zinc-700">
                  <input
                    type="checkbox"
                    checked={!!values[f.id]}
                    onChange={(e) => setVal(f.id, e.target.checked)}
                    required={f.required}
                    data-testid={`public-form-field-${f.id}`}
                  />
                  {f.placeholder || 'Yes'}
                </label>
              ) : (
                <Input
                  type={f.field_type === 'email' ? 'email' : f.field_type === 'phone' ? 'tel' : f.field_type === 'number' ? 'number' : 'text'}
                  value={values[f.id] || ''}
                  onChange={(e) => setVal(f.id, e.target.value)}
                  required={f.required}
                  placeholder={f.placeholder}
                  className="mt-1"
                  data-testid={`public-form-field-${f.id}`}
                />
              )}
            </div>
          ))}

          {form.require_consent && (
            <label className="flex items-start gap-2 mt-1 text-xs text-zinc-600">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                required
                className="mt-1"
                data-testid="public-form-consent"
              />
              <span>{form.consent_text}</span>
            </label>
          )}

          {error && <p className="text-rose-600 text-sm">{error}</p>}

          <Button
            type="submit"
            disabled={submitting}
            className="w-full bg-zinc-900 hover:bg-zinc-800 text-white"
            data-testid="public-form-submit"
          >
            {submitting ? 'Submitting…' : (form.submit_button_label || 'Submit')}
          </Button>
        </form>
      </div>
    </div>
  );
};

export default PublicFormPage;
