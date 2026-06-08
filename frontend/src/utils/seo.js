/**
 * useSeo (iter 215c2)
 * React hook for per-page SEO meta + Open Graph + Twitter card + JSON-LD.
 * Lightweight — no react-helmet dependency, just imperative DOM updates.
 *
 * Usage:
 *   useSeo({
 *     title: 'Pricing | GymAxis AI',
 *     description: '£150/mo for one site. Add modules à la carte. 3-day trial.',
 *     canonical: 'https://www.gymaxisai.com/pricing',
 *     image: 'https://www.gymaxisai.com/og/pricing.jpg',
 *     type: 'website',
 *     structuredData: { '@context': 'https://schema.org', '@type': 'Product', ... }
 *   });
 */
import { useEffect } from 'react';

const setMeta = (selector, attr, value) => {
  if (!value) return;
  let el = document.head.querySelector(selector);
  if (!el) {
    el = document.createElement('meta');
    const [, key, name] = selector.match(/\[([^=]+)="([^"]+)"\]/) || [];
    if (key && name) el.setAttribute(key, name);
    document.head.appendChild(el);
  }
  el.setAttribute(attr, value);
};

const setLink = (rel, href) => {
  if (!href) return;
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement('link');
    el.setAttribute('rel', rel);
    document.head.appendChild(el);
  }
  el.setAttribute('href', href);
};

const setJsonLd = (id, data) => {
  let el = document.getElementById(id);
  if (!data) {
    if (el) el.remove();
    return;
  }
  if (!el) {
    el = document.createElement('script');
    el.id = id;
    el.type = 'application/ld+json';
    document.head.appendChild(el);
  }
  el.textContent = JSON.stringify(data);
};

export const useSeo = ({ title, description, canonical, image, type = 'website', structuredData } = {}) => {
  useEffect(() => {
    // Iter 216o-6 — capture the previous title so navigating away from
    // a page that called `useSeo` restores the document title (otherwise
    // visiting /pricing then /dashboard leaves the tab labelled
    // "Pricing — GymAxis AI" forever).
    const previousTitle = document.title;
    if (title) document.title = title;
    if (description) setMeta('meta[name="description"]', 'content', description);

    // Open Graph
    setMeta('meta[property="og:title"]', 'content', title);
    setMeta('meta[property="og:description"]', 'content', description);
    setMeta('meta[property="og:type"]', 'content', type);
    setMeta('meta[property="og:url"]', 'content', canonical || window.location.href);
    setMeta('meta[property="og:image"]', 'content', image);
    setMeta('meta[property="og:site_name"]', 'content', 'GymAxis AI');

    // Twitter card
    setMeta('meta[name="twitter:card"]', 'content', image ? 'summary_large_image' : 'summary');
    setMeta('meta[name="twitter:title"]', 'content', title);
    setMeta('meta[name="twitter:description"]', 'content', description);
    setMeta('meta[name="twitter:image"]', 'content', image);

    if (canonical) setLink('canonical', canonical);

    setJsonLd('seo-jsonld', structuredData);

    return () => {
      // Restore on unmount so internal pages without their own useSeo()
      // call don't inherit the previous page's title.
      if (title) document.title = previousTitle;
    };
  }, [title, description, canonical, image, type, structuredData]);
};

// Pre-baked structured data builders for common pages.
export const orgJsonLd = () => ({
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'GymAxis AI',
  url: 'https://www.gymaxisai.com',
  logo: 'https://www.gymaxisai.com/brand/gymaxis-logo.svg',
  description: 'All-in-one platform for fitness operators: CRM, memberships, marketing, and gym operations.',
  sameAs: ['https://www.instagram.com/gymaxisai'],
  contactPoint: {
    '@type': 'ContactPoint',
    contactType: 'customer support',
    email: 'support@gymaxisai.com',
    areaServed: 'GB',
    availableLanguage: ['English'],
  },
});

export const softwareJsonLd = () => ({
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'GymAxis AI',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  description: 'Multi-tenant fitness operations platform for gyms, leisure centres, and studios.',
  image: ['https://www.gymaxisai.com/brand/og-cover.jpg'],
  offers: {
    '@type': 'AggregateOffer',
    lowPrice: '29.00',
    highPrice: '150.00',
    priceCurrency: 'GBP',
    offerCount: 5,
  },
});

export default useSeo;
