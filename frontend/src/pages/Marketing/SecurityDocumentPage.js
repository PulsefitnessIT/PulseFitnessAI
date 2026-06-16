/**
 * /security/details — full rendered SECURITY.md with download links.
 * Iter 220by — replaces the broken github.com/gymaxis/security link.
 */
import React from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { ArrowLeft, Download, FileText, FileType2, ShieldCheck, Loader2 } from 'lucide-react';

import '../Marketing/marketing.css';
import MarketingShell from './MarketingShell';

const API = process.env.REACT_APP_BACKEND_URL;

export default function SecurityDocumentPage() {
  const [doc, setDoc] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/api/security/document`)
      .then((r) => { if (!cancelled) setDoc(r.data); })
      .catch((e) => { if (!cancelled) setError(e?.response?.data?.detail || 'Failed to load'); });
    return () => { cancelled = true; };
  }, []);

  React.useEffect(() => {
    const prev = document.title;
    const prevMeta = document.querySelector('meta[name="description"]')?.getAttribute('content');
    document.title = 'Pulse Fitness Security — Hardening summary, posture & download';
    let m = document.querySelector('meta[name="description"]');
    if (!m) { m = document.createElement('meta'); m.setAttribute('name', 'description'); document.head.appendChild(m); }
    m.setAttribute('content', 'Pulse Fitness security posture: JWT, MFA, rate limits, audit trail, GDPR. Read in-browser or download as PDF / TXT.');
    return () => {
      document.title = prev;
      if (m && prevMeta) m.setAttribute('content', prevMeta);
    };
  }, []);

  return (
    <MarketingShell>
      <section className="bg-white dark:bg-zinc-950">
        <div className="max-w-4xl mx-auto px-6 lg:px-8 pt-14 pb-12 lg:pt-20">
          <Link
            to="/security"
            className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-600 hover:text-slate-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            data-testid="security-doc-back"
          >
            <ArrowLeft size={14} /> Back to Security
          </Link>

          <span className="mt-6 inline-flex items-center gap-2 rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-emerald-700">
            <ShieldCheck size={12} /> Security document
          </span>

          <h1 className="mt-4 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05]">
            Pulse Fitness AI — <span className="gx-gradient-text">Security</span>
          </h1>
          <p className="mt-5 text-base md:text-lg text-slate-600 dark:text-zinc-300 max-w-3xl">
            The full hardening summary, vulnerability-disclosure policy, and the
            audit you can run yourself. Same source file our engineers ship from,
            published verbatim so procurement teams can verify rather than trust.
          </p>

          <div className="mt-8 flex flex-wrap gap-3" data-testid="security-doc-actions">
            <a
              href={`${API}/api/security/document.pdf`}
              className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white hover:bg-slate-700 transition dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
              data-testid="security-doc-pdf"
            >
              <Download size={14} /> Download PDF
            </a>
            <a
              href={`${API}/api/security/document.txt`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-bold text-slate-700 hover:border-slate-400 transition dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
              data-testid="security-doc-txt"
            >
              <FileType2 size={14} /> View as plain text
            </a>
            <a
              href="/.well-known/security.txt"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-bold text-slate-700 hover:border-slate-400 transition dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
              data-testid="security-doc-rfc"
            >
              <FileText size={14} /> security.txt (RFC 9116)
            </a>
          </div>
        </div>
      </section>

      <section className="bg-slate-50/60 dark:bg-zinc-900 pb-24">
        <div className="max-w-4xl mx-auto px-6 lg:px-8">
          <div
            className="rounded-3xl border border-slate-200 bg-white p-6 md:p-10 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
            data-testid="security-doc-body"
          >
            {error ? (
              <p className="text-sm text-rose-600" data-testid="security-doc-error">
                Couldn't load the document: {error}. Try the
                {' '}<a className="underline" href={`${API}/api/security/document.pdf`}>PDF download</a>{' '}
                instead.
              </p>
            ) : !doc ? (
              <p className="flex items-center gap-2 text-sm text-slate-500" data-testid="security-doc-loading">
                <Loader2 size={14} className="animate-spin" /> Loading…
              </p>
            ) : (
              <article
                className="gx-prose"
                /* Source is a static, repo-committed markdown file
                   rendered server-side by markdown2; safe. */
                dangerouslySetInnerHTML={{ __html: doc.html }}
              />
            )}
          </div>
          {doc?.generated_at ? (
            <p className="mt-4 text-xs text-slate-400 dark:text-zinc-500" data-testid="security-doc-meta">
              Source: {doc.source_filename} · Rendered {new Date(doc.generated_at).toLocaleString()}
            </p>
          ) : null}
        </div>
      </section>
    </MarketingShell>
  );
}
