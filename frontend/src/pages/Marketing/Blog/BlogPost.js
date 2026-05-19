/**
 * /blog/:slug — single post view with schema.org Article JSON-LD.
 */
import React from 'react';
import { useParams, Link, Navigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Clock, User } from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import { getPost, posts } from './posts';
import { openTrial } from '../TrialSignupModal';

export default function BlogPost() {
  const { slug } = useParams();
  const post = getPost(slug);

  React.useEffect(() => {
    if (!post) return undefined;
    const prev = document.title;
    const prevMeta = document.querySelector('meta[name="description"]')?.getAttribute('content');
    document.title = `${post.title} — GymAxis Blog`;
    let m = document.querySelector('meta[name="description"]');
    if (!m) { m = document.createElement('meta'); m.setAttribute('name', 'description'); document.head.appendChild(m); }
    m.setAttribute('content', post.excerpt);
    return () => {
      document.title = prev;
      if (m && prevMeta) m.setAttribute('content', prevMeta);
    };
  }, [post]);

  if (!post) return <Navigate to="/blog" replace />;

  const articleJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: post.title,
    description: post.excerpt,
    datePublished: post.publishedAt,
    author: { '@type': 'Person', name: post.author },
    publisher: { '@type': 'Organization', name: 'GymAxis', logo: { '@type': 'ImageObject', url: 'https://www.gymaxisai.com/brand/logo.svg' } },
    mainEntityOfPage: { '@type': 'WebPage', '@id': `https://www.gymaxisai.com/blog/${post.slug}` },
  };

  const other = posts.filter((p) => p.slug !== post.slug).slice(0, 2);

  return (
    <MarketingShell>
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{ __html: JSON.stringify(articleJsonLd) }}
      />
      <article className="bg-white dark:bg-zinc-900">
        <div className="max-w-3xl mx-auto px-6 lg:px-8 pt-10 pb-20" data-testid={`blog-post-${post.slug}`}>
          <Link to="/blog" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mb-6">
            <ArrowLeft size={14} /> All posts
          </Link>
          <div className="flex flex-wrap items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
            {post.tags?.map((t) => <span key={t} className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-zinc-800">{t}</span>)}
          </div>
          <h1 className="mt-4 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05]">
            {post.title}
          </h1>
          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-slate-500">
            <span className="inline-flex items-center gap-1.5"><User size={13} /> {post.author}</span>
            <span>·</span>
            <span>{new Date(post.publishedAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
            <span>·</span>
            <span className="inline-flex items-center gap-1.5"><Clock size={13} /> {post.readingMinutes} min read</span>
          </div>
          <div className="mt-10 gx-prose">
            {post.body}
          </div>
        </div>
      </article>

      {/* CTA */}
      <section className="bg-slate-50 py-16 dark:bg-zinc-900">
        <div className="max-w-4xl mx-auto px-6 lg:px-8 rounded-3xl p-10 text-center text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
          <h2 className="text-3xl md:text-4xl font-black tracking-tight">Run the playbook on your own floor.</h2>
          <p className="mt-3 text-white/85 max-w-xl mx-auto">
            Start a 3-day trial with all modules unlocked. No card, no sales call required.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-6 py-3 text-sm font-bold hover:bg-slate-100 dark:bg-zinc-900 dark:bg-zinc-800 dark:text-zinc-100">
              Start trial <ArrowRight size={14} />
            </button>
            <Link to="/pricing" className="inline-flex items-center gap-1.5 rounded-full border border-white/40 px-6 py-3 text-sm font-bold hover:bg-white/10">
              See pricing
            </Link>
          </div>
        </div>
      </section>

      {/* Related */}
      {other.length ? (
        <section className="bg-white py-16 dark:bg-zinc-900">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
            <h2 className="text-2xl font-black tracking-tight">Keep reading</h2>
            <div className="mt-6 grid md:grid-cols-2 gap-5">
              {other.map((o) => (
                <Link key={o.slug} to={`/blog/${o.slug}`} className="rounded-2xl border border-slate-200 p-6 hover:shadow-md transition dark:border-zinc-800">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{o.tags?.[0] || 'Article'}</p>
                  <h3 className="mt-2 text-lg font-bold tracking-tight">{o.title}</h3>
                  <p className="mt-2 text-sm text-slate-600">{o.excerpt}</p>
                </Link>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </MarketingShell>
  );
}
