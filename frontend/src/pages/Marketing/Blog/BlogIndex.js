/**
 * /blog — index page listing all posts.
 *
 * Merges the file-based legacy registry with SEO Autopilot DB articles
 * (Iter 220ad). DB articles take precedence on slug conflicts.
 */
import React from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen, Clock } from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import { posts as staticPosts } from './posts';

const API = process.env.REACT_APP_BACKEND_URL;

export default function BlogIndex() {
  const [dbPosts, setDbPosts] = React.useState([]);
  React.useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/api/blog/posts`)
      .then((r) => { if (!cancelled) setDbPosts((r.data?.posts || []).map((p) => ({
        slug: p.slug,
        title: p.title,
        excerpt: p.excerpt,
        publishedAt: p.published_at,
        readingMinutes: p.read_time_min || 7,
        tags: p.tags || [],
        hero_image_url: p.hero_image_url,
      }))); })
      .catch(() => { /* silently fall back to static */ });
    return () => { cancelled = true; };
  }, []);

  const seen = new Set(dbPosts.map((p) => p.slug));
  const posts = [
    ...dbPosts,
    ...staticPosts.filter((p) => !seen.has(p.slug)),
  ].sort((a, b) => (b.publishedAt || '').localeCompare(a.publishedAt || ''));

  React.useEffect(() => {
    const prev = document.title;
    const prevMeta = document.querySelector('meta[name="description"]')?.getAttribute('content');
    document.title = 'Pulse Fitness Blog — Operations, reporting, and service-desk playbooks';
    let m = document.querySelector('meta[name="description"]');
    if (!m) { m = document.createElement('meta'); m.setAttribute('name', 'description'); document.head.appendChild(m); }
    m.setAttribute('content', 'Actionable playbooks for gym operators: cut equipment downtime, track the right KPIs, and write SLAs that stick.');
    return () => {
      document.title = prev;
      if (m && prevMeta) m.setAttribute('content', prevMeta);
    };
  }, []);

  return (
    <MarketingShell>
      <section className="gx-grid-bg">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-16 lg:pt-20 lg:pb-24">
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <BookOpen size={12} /> The Pulse Fitness Blog
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            Playbooks for operators who<br />
            <span className="gx-gradient-text">run the floor.</span>
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 max-w-3xl">
            Short, specific, numbers-first reads on service desk, reporting, contracts and the operational habits that separate scale from stall.
          </p>
        </div>
      </section>

      <section className="bg-white pb-24 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 grid md:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="blog-index">
          {posts.map((p) => (
            <Link
              key={p.slug}
              to={`/blog/${p.slug}`}
              data-testid={`blog-card-${p.slug}`}
              className="group rounded-2xl bg-white border border-slate-200 overflow-hidden hover:shadow-md hover:-translate-y-0.5 transition flex flex-col dark:bg-zinc-900 dark:border-zinc-800"
            >
              <div className="aspect-[16/9] bg-gradient-to-br from-slate-800 via-slate-700 to-slate-900 flex items-center justify-center p-6 overflow-hidden">
                {p.hero_image_url ? (
                  <img src={p.hero_image_url} alt="" className="w-full h-full object-cover"/>
                ) : (
                  <span className="text-white/80 text-xs font-bold uppercase tracking-[0.2em]">
                    {p.tags?.[0] || 'Article'}
                  </span>
                )}
              </div>
              <div className="p-6 flex-1 flex flex-col">
                <h2 className="text-xl font-black tracking-tight leading-snug">{p.title}</h2>
                <p className="mt-3 text-sm text-slate-600 leading-relaxed flex-1">{p.excerpt}</p>
                <div className="mt-5 flex items-center justify-between text-xs text-slate-500">
                  <span>{p.publishedAt ? new Date(p.publishedAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}</span>
                  <span className="inline-flex items-center gap-1"><Clock size={11} /> {p.readingMinutes}m</span>
                </div>
                <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-bold text-slate-800 group-hover:text-slate-600">
                  Read <ArrowRight size={14} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </MarketingShell>
  );
}
