/**
 * Blog post registry. Each post exports { meta, body }.
 *
 * Why in-code and not DB?  (iter 215ee)
 *   • SEO pages MUST be pre-rendered / crawlable — a React component
 *     renders server-side-equivalent markup on first paint.
 *   • No DB query = no loading spinner = faster LCP = better SEO.
 *   • Editors stay in the repo so diffs review like code.
 *
 * When we outgrow 10+ posts, swap this for a DB + admin editor.
 */
import * as downtimePost from './downtime-reduction';
import * as metricsPost from './gym-manager-metrics';
import * as slaPost from './service-desk-sla-explained';

export const posts = [downtimePost, metricsPost, slaPost]
  .map((m) => ({ ...m.meta, body: m.body }))
  .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));

export function getPost(slug) {
  return posts.find((p) => p.slug === slug) || null;
}
