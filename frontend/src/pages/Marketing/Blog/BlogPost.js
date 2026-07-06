/**
 * /blog/:slug — single post view with schema.org Article + FAQPage JSON-LD.
 *
 * Lookup order:
 *   1. File-based registry (legacy posts under ./posts/)
 *   2. SEO Autopilot DB fetch (/api/blog/posts/:slug)
 *
 * If neither matches → /blog redirect.
 */
import React from 'react';
import axios from 'axios';
import { useParams, Link, Navigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Clock, User, Loader2 } from 'lucide-react';

import '../marketing.css';
import PulseMarketingShell from '../PulseMarketingShell';
import { getPost, posts } from './posts';

const API = process.env.REACT_APP_BACKEND_URL;

/** Minimal Markdown → plain HTML transformer. Handles H1-H3, paragraphs,
 * bold, italic, unordered/ordered lists, and links. Pure client-side,
 * no deps. */
function mdToHtml(md) {
  if (!md) return '';
  const escape = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  let html = escape(md);
  // Headings
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Bold + italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Links — [text](url)
  html = html.replace(/\[(.+?)\]\((https?:\/\/[^\s)]+|\/[^\s)]+)\)/g, '<a href="$2" rel="noopener">$1</a>');
  // Unordered lists
  html = html.replace(/(?:^- .+(?:\n|$))+/gm, (block) => {
    const items = block.trim().split(/\n/).map((l) => l.replace(/^- /, '')).map((l) => `<li>${l}</li>`).join('');
    return `<ul>${items}</ul>`;
  });
  // Ordered lists
  html = html.replace(/(?:^\d+\. .+(?:\n|$))+/gm, (block) => {
    const items = block.trim().split(/\n/).map((l) => l.replace(/^\d+\. /, '')).map((l) => `<li>${l}</li>`).join('');
    return `<ol>${items}</ol>`;
  });
  // Paragraphs — wrap remaining lines
  html = html
    .split(/\n{2,}/)
    .map((block) => {
      if (/^<(h1|h2|h3|ul|ol|p)/.test(block.trim())) return block;
      return `<p>${block.replace(/\n/g, '<br/>')}</p>`;
    })
    .join('\n');
  return html;
}

export default function BlogPost() {
  const { slug } = useParams();
  const staticPost = getPost(slug);
  const [dbPost, setDbPost] = React.useState(null);
  const [loading, setLoading] = React.useState(!staticPost);
  const [notFound, setNotFound] = React.useState(false);

  // Fetch from DB if not in the file-based registry.
  React.useEffect(() => {
    if (staticPost) return;
    let cancelled = false;
    setLoading(true);
    axios.get(`${API}/api/blog/posts/${encodeURIComponent(slug)}`)
      .then((r) => { if (!cancelled) setDbPost(r.data); })
      .catch(() => { if (!cancelled) setNotFound(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [slug, staticPost]);

  // Iter 220ea·3 — wrap derived `post` in useMemo so the
  // document-title useEffect below doesn't churn on every render.
  const post = React.useMemo(() => staticPost || (dbPost ? {
    slug: dbPost.slug,
    title: dbPost.title,
    excerpt: dbPost.excerpt,
    publishedAt: dbPost.published_at,
    author: 'Pulse Fitness',
    readingMinutes: dbPost.read_time_min || 7,
    tags: dbPost.tags || [],
    body: (
      <>
        {dbPost.hero_image_url ? (
          <img
            src={dbPost.hero_image_url}
            alt={dbPost.hero_image_alt || dbPost.title}
            className="w-full rounded-2xl border border-slate-200 dark:border-slate-700 mb-8"
            data-testid="blog-hero"
          />
        ) : null}
        <div
           
          dangerouslySetInnerHTML={{ __html: mdToHtml(dbPost.body_md) }}
        />
        {dbPost.qa_blocks?.length ? (
          <section className="mt-12" data-testid="blog-faq">
            <h2>Frequently asked questions</h2>
            {dbPost.qa_blocks.map((q, i) => (
              <div key={i} className="mt-5">
                <h3>{q.question}</h3>
                <p>{q.answer}</p>
              </div>
            ))}
          </section>
        ) : null}
      </>
    ),
    qa_blocks: dbPost.qa_blocks,
    meta_description: dbPost.meta_description,
  } : null), [staticPost, dbPost]);

  React.useEffect(() => {
    if (!post) return undefined;
    const prev = document.title;
    const prevMeta = document.querySelector('meta[name="description"]')?.getAttribute('content');
    document.title = `${post.title} — Pulse Fitness Blog`;
    let m = document.querySelector('meta[name="description"]');
    if (!m) { m = document.createElement('meta'); m.setAttribute('name', 'description'); document.head.appendChild(m); }
    m.setAttribute('content', post.meta_description || post.excerpt);
    return () => {
      document.title = prev;
      if (m && prevMeta) m.setAttribute('content', prevMeta);
    };
  }, [post]);

  if (loading) {
    return (
      <PulseMarketingShell>
        <div className="min-h-[60vh] flex items-center justify-center text-slate-400">
          <Loader2 size={20} className="animate-spin"/>
        </div>
      </PulseMarketingShell>
    );
  }
  if (!post || notFound) return <Navigate to="/blog" replace />;

  const articleJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: post.title,
    description: post.excerpt,
    datePublished: post.publishedAt,
    author: { '@type': 'Person', name: post.author },
    publisher: { '@type': 'Organization', name: 'Pulse Fitness', logo: { '@type': 'ImageObject', url: 'https://pulsefitness.ai/brand/logo.svg' } },
    mainEntityOfPage: { '@type': 'WebPage', '@id': `https://pulsefitness.ai/blog/${post.slug}` },
  };

  // FAQPage JSON-LD — what gets us cited in ChatGPT / Perplexity / AI overviews.
  const faqJsonLd = post.qa_blocks?.length ? {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: post.qa_blocks.map((q) => ({
      '@type': 'Question',
      name: q.question,
      acceptedAnswer: { '@type': 'Answer', text: q.answer },
    })),
  } : null;

  const other = posts.filter((p) => p.slug !== post.slug).slice(0, 2);

  return (
    <PulseMarketingShell>
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{ __html: JSON.stringify(articleJsonLd) }}
      />
      {faqJsonLd ? (
        <script
          type="application/ld+json"
           
          dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
        />
      ) : null}
      <article className="bg-white">
        <div className="max-w-3xl mx-auto px-6 lg:px-8 pt-10 pb-20" data-testid={`blog-post-${post.slug}`}>
          <Link to="/blog" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-[#19CDFF] transition-colors mb-6">
            <ArrowLeft size={14} /> All posts
          </Link>
          <div className="flex flex-wrap items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
            {post.tags?.map((t) => <span key={t} className="rounded-full bg-slate-100 px-2.5 py-1">{t}</span>)}
          </div>
          <h1 className="mt-4 text-4xl md:text-5xl lg:text-6xl tracking-tight font-black leading-[1.05]" style={{ color: '#1B1C1D' }}>
            {post.title}
          </h1>
          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-slate-500">
            <span className="inline-flex items-center gap-1.5"><User size={13} /> {post.author}</span>
            {post.publishedAt ? <><span>·</span><span>{new Date(post.publishedAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}</span></> : null}
            <span>·</span>
            <span className="inline-flex items-center gap-1.5"><Clock size={13} /> {post.readingMinutes} min read</span>
          </div>
          <div className="mt-10 gx-prose">
            {post.body}
          </div>
        </div>
      </article>

      {/* CTA — Pulse Fitness brand */}
      <section className="bg-slate-50 py-16">
        <div className="max-w-4xl mx-auto px-6 lg:px-8 rounded-3xl p-10 text-center text-white" style={{ background: '#1B1C1D' }}>
          <h2 className="text-3xl md:text-4xl font-black tracking-tight text-white">Run the playbook on your own floor.</h2>
          <p className="mt-3 text-white/80 max-w-xl mx-auto">
            See how Pulse Fitness helps operators cut equipment downtime and run the floor with confidence.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Link to="/pulse-pricing" className="inline-flex items-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold text-[#1B1C1D] transition-opacity hover:opacity-90" style={{ background: '#19CDFF' }}>
              Explore Pulse Fitness <ArrowRight size={14} />
            </Link>
            <Link to="/pulse-pricing" className="inline-flex items-center gap-1.5 rounded-full border border-white/40 px-6 py-3 text-sm font-bold text-white hover:bg-white/10">
              See plans
            </Link>
          </div>
        </div>
      </section>

      {/* Related */}
      {other.length ? (
        <section className="bg-white py-16">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
            <h2 className="text-2xl font-black tracking-tight" style={{ color: '#1B1C1D' }}>Keep reading</h2>
            <div className="mt-6 grid md:grid-cols-2 gap-5">
              {other.map((o) => (
                <Link key={o.slug} to={`/blog/${o.slug}`} className="rounded-2xl border border-slate-200 p-6 hover:shadow-lg hover:border-[#19CDFF] transition">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{o.tags?.[0] || 'Article'}</p>
                  <h3 className="mt-2 text-lg font-bold tracking-tight" style={{ color: '#1B1C1D' }}>{o.title}</h3>
                  <p className="mt-2 text-sm text-slate-600">{o.excerpt}</p>
                </Link>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </PulseMarketingShell>
  );
}
