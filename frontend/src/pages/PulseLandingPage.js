/**
 * Pulse Fitness Service Portal — customer-facing landing page.
 *
 * Nine-section marketing homepage (light mode, tactile cards, Pulse brand).
 * Auth flow preserved: the existing inline login moves into a modal so the
 * marketing sections have room to breathe. `onLogin(data)` callback unchanged.
 */
import React, { useState, useRef, useEffect } from 'react';
import { motion, useInView } from 'framer-motion';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import axios from 'axios';

import { useInlineBanner } from '@/components/notifications';
import { TrustedBy, HeritageTimeline, StatsBento, Sustainability } from '@/pages/PulseHeritageSections';
import { useAuth } from '@/App';
import { useSignedOutNotice } from '@/hooks/useSignedOutNotice';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import {
  Wrench, ClipboardCheck, FileText, Phone, Brain, Sparkles, BookOpen,
  QrCode, Smartphone, Zap, Timer, TrendingDown, TrendingUp, Eye, CheckCircle2,
  ArrowRight, LogIn, Loader2, EyeOff, Sun, Moon, Globe, Check,
  ListChecks, MessageSquareHeart, Trophy, ChevronRight, Star, ClipboardList,
  AlertTriangle, Mail, User,
  Sliders, Layers, UserCog, Workflow, Link2,
  Menu, X, Linkedin, Instagram, Youtube,
} from 'lucide-react';

const API_URL = `${process.env.REACT_APP_BACKEND_URL}/api`;
// Hero / section backgrounds served as WebP (q=82, ~80% smaller than the
// source JPEGs). Supported by every browser we target (Safari 14+, Chrome,
// Firefox, Edge, mobile) — caniuse.com reports 97%+ global coverage. The
// source .jpg files are still on disk as a fallback for legacy crawlers.
const HERO_BG = '/pulse-photos/gym-treadmill-row.webp';
const GYM_EQUIPMENT = '/pulse-photos/gym-orange-lights.webp';
const GYM_ACTION = '/pulse-photos/strength-floor.webp';
const _MOBILE_BG = 'https://images.pexels.com/photos/4162581/pexels-photo-4162581.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940&fm=webp';

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
];

// ── Motion primitives ──────────────────────────────────────────
const FADE_UP = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};
const stagger = { show: { transition: { staggerChildren: 0.08 } } };

function Reveal({ children, className = '', testId }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.2 });
  return (
    <motion.div
      ref={ref}
      initial="hidden"
      animate={inView ? 'show' : 'hidden'}
      variants={stagger}
      className={className}
      data-testid={testId}
    >
      {children}
    </motion.div>
  );
}

function SectionHeading({ eyebrow, title, description, align = 'left', testId }) {
  const alignClass = align === 'center' ? 'text-center mx-auto' : '';
  return (
    <Reveal className={`max-w-2xl mb-10 ${alignClass}`} testId={testId}>
      <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
        <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" />
        {eyebrow}
      </motion.div>
      <motion.h2 variants={FADE_UP} className="text-2xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--color-surface-dark-panel-alt)] leading-[1.15]">
        {title}
      </motion.h2>
      {description && (
        <motion.p variants={FADE_UP} className="mt-3 sm:mt-4 text-sm sm:text-lg text-[var(--color-text-slate)] max-w-xl">
          {description}
        </motion.p>
      )}
    </Reveal>
  );
}

// ── Header ─────────────────────────────────────────────────────
export function PulseHeader({ onSignIn, theme, toggleTheme, i18n }) {
  const [langOpen, setLangOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [mobileOpen]);

  const { t } = useTranslation();
  const NAV_LINKS = [
    { href: '/#capabilities', label: t('pulse.nav_what', 'What you can do'), testid: 'nav-capabilities' },
    { href: '/#ai',           label: t('pulse.nav_ai', 'AI'),                testid: 'nav-ai' },
    { href: '/#how',          label: t('pulse.nav_how', 'How it works'),     testid: 'nav-how' },
    { to:   '/pulse-pricing', label: t('pulse.nav_plans', 'Plans'),          testid: 'nav-plans' },
    { href: '/#support',      label: t('pulse.nav_support', 'Support'),      testid: 'nav-support' },
  ];

  const navigate = useNavigate();
  const goToSection = (e, href, closeMenu) => {
    if (!href || !href.includes('#')) return;
    e.preventDefault();
    if (closeMenu) closeMenu();
    const id = href.split('#').pop();
    if (window.location.pathname === '/') {
      // Already on the landing page → smooth-scroll, no reload/reset.
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth' });
        window.history.replaceState(null, '', '/#' + id);
      }
    } else {
      // On another route (e.g. /pulse-pricing) → go to landing, then scroll.
      navigate('/#' + id);
      let tries = 0;
      const tick = () => {
        const el = document.getElementById(id);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
        else if (tries++ < 25) setTimeout(tick, 100);
      };
      setTimeout(tick, 120);
    }
  };

  return (
    <header className="sticky top-0 z-50 bg-black border-b border-white/10" data-testid="pulse-header">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
        <RouterLink to="/" className="flex items-center gap-2" aria-label="Pulse Fitness home" data-testid="pulse-logo-home">
          <img
            src="/brand/pulse-logo-reverse.svg"
            alt="Pulse Fitness"
            className="h-8 w-auto object-contain select-none"
            draggable={false}
          />
        </RouterLink>
        <nav className="hidden md:flex items-center gap-7 text-[13px] font-semibold uppercase text-white/85" style={{ fontFamily: "'Proxima Nova', 'Inter', system-ui, sans-serif", letterSpacing: '0.08em' }}>
          {NAV_LINKS.map((l) => (
            l.to ? (
              <RouterLink key={l.to} to={l.to} className="hover:text-white transition-colors" data-testid={l.testid}>{l.label}</RouterLink>
            ) : (
              <a key={l.href} href={l.href} onClick={(e) => goToSection(e, l.href)} className="hover:text-white transition-colors" data-testid={l.testid}>{l.label}</a>
            )
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            // Iter 215dk — mobile readability: 36→40px tap target (was below
            // the 44px Apple/Google minimum on phones).
            className="w-10 h-10 rounded-xl flex items-center justify-center border border-white/40 hover:bg-white/10 transition-colors"
            data-testid="pulse-theme-toggle"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? <Sun size={16} style={{ color: '#fbbf24' }} /> : <Moon size={16} style={{ color: '#ffffff' }} />}
          </button>
          <div className="relative">
            <button
              onClick={() => setLangOpen(o => !o)}
              className="h-10 px-3 rounded-xl flex items-center gap-1.5 border border-white/40 hover:bg-white/10 transition-colors"
              data-testid="pulse-lang-toggle"
            >
              <Globe size={15} style={{ color: '#ffffff' }} />
              <span className="text-xs font-semibold uppercase" style={{ color: '#ffffff' }}>{i18n.language?.substring(0, 2)}</span>
            </button>
            {langOpen && (
              <div className="absolute right-0 top-full mt-2 w-40 rounded-xl shadow-xl overflow-hidden bg-white border border-slate-200" data-testid="pulse-lang-dropdown">
                {LANGUAGES.map(l => (
                  <button
                    key={l.code}
                    onClick={() => { i18n.changeLanguage(l.code); setLangOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-slate-50 ${i18n.language?.startsWith(l.code) ? 'text-[var(--pulse-primary)] font-semibold' : 'text-slate-700'}`}
                  >
                    {l.label}
                    {i18n.language?.startsWith(l.code) && <Check size={12} className="ml-auto" />}
                  </button>
                ))}
              </div>
            )}
          </div>
          <Button
            onClick={onSignIn}
            // Iter 215dj — was solid black using `surface-dark-panel-alt`
            // which dominated the Pulse Fitness header on mobile and felt
            // off-brand. Switched to the Pulse cyan primary so the CTA
            // matches the rest of the Pulse Fitness palette.
            // Iter 215dk — bumped 36→40px tap target for mobile.
            className="h-10 px-4 rounded-xl font-semibold text-sm uppercase tracking-wide hover:opacity-90 transition-opacity"
            style={{ backgroundColor: 'var(--pulse-primary)', color: 'var(--color-ink, #0f172a)' }}
            data-testid="pulse-header-login-btn"
          >
            <LogIn size={14} className="mr-1.5" /> {t('pulse.sign_in', 'Sign In')}
          </Button>
          {/* Iter 215aj — mobile menu */}
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            className="md:hidden w-10 h-10 rounded-xl flex items-center justify-center border border-white/20 hover:bg-white/10 transition-colors"
            data-testid="pulse-mobile-menu-btn"
          >
            <Menu size={16} className="text-white/80" />
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-[60] h-screen"
          data-testid="pulse-mobile-drawer"
          role="dialog"
          aria-modal="true"
          onClick={() => setMobileOpen(false)}
        >
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
          <div
            className="absolute right-0 top-0 h-full w-[78%] max-w-xs bg-white shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 h-14 border-b border-slate-200">
              <span className="text-slate-900 font-bold text-sm">Menu</span>
              <button
                onClick={() => setMobileOpen(false)}
                aria-label="Close menu"
                className="p-1.5 text-slate-600 hover:text-slate-900"
                data-testid="pulse-mobile-close"
              >
                <X size={18} />
              </button>
            </div>
            <nav className="flex-1 flex flex-col gap-1 py-4 px-3">
              {NAV_LINKS.map((l) => (
                l.to ? (
                  <RouterLink
                    key={l.to}
                    to={l.to}
                    onClick={() => setMobileOpen(false)}
                    className="px-4 py-3 rounded-lg text-slate-700 hover:text-slate-900 hover:bg-slate-50 text-[15px] font-semibold transition-colors"
                    data-testid={`pulse-mobile-${l.testid}`}
                  >
                    {l.label}
                  </RouterLink>
                ) : (
                  <a
                    key={l.href}
                    href={l.href}
                    onClick={(e) => goToSection(e, l.href, () => setMobileOpen(false))}
                    className="px-4 py-3 rounded-lg text-slate-700 hover:text-slate-900 hover:bg-slate-50 text-[15px] font-semibold transition-colors"
                    data-testid={`pulse-mobile-${l.testid}`}
                  >
                    {l.label}
                  </a>
                )
              ))}
            </nav>
          </div>
        </div>
      )}
    </header>
  );
}

// ── Hero ───────────────────────────────────────────────────────
function KineticWord() {
  const { t } = useTranslation();
  const words = [t('pulse.hero_word_1', 'Manage'), t('pulse.hero_word_2', 'Maintain'), t('pulse.hero_word_3', 'Maximise')];
  const [index, setIndex] = useState(0);
  React.useEffect(() => {
    const timer = setInterval(() => setIndex((i) => (i + 1) % 3), 2400);
    return () => clearInterval(timer);
  }, []);
  return (
    <span className="relative inline-block align-baseline" style={{ minWidth: '4.5ch' }}>
      <motion.span
        key={words[index]}
        initial={{ y: 28, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: -28, opacity: 0 }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        className="inline-block text-[var(--pulse-primary)]"
        style={{ fontFamily: "'Proxima Nova', sans-serif", fontWeight: 800 }}
      >
        {words[index]}
      </motion.span>
    </span>
  );
}

function Hero({ onSignIn }) {
  const { t } = useTranslation();
  return (
    <section className="relative overflow-hidden bg-[var(--pulse-black,#212721)]" data-theme="dark" data-testid="pulse-hero">
      {/* Full-bleed "Heart of Fitness" treadmill row, cinematic dark overlay */}
      <motion.div
        initial={{ opacity: 0, scale: 1.06 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.6, ease: [0.16, 1, 0.3, 1] }}
        className="absolute inset-0"
      >
        <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url(${HERO_BG})` }} />
        <div className="absolute inset-0" style={{ background: 'linear-gradient(100deg, rgba(33,39,33,0.94) 0%, rgba(33,39,33,0.78) 42%, rgba(33,39,33,0.35) 100%)' }} />
        <div className="absolute inset-0" style={{ background: 'linear-gradient(to top, rgba(33,39,33,0.9) 0%, transparent 35%, rgba(33,39,33,0.4) 100%)' }} />
      </motion.div>

      {/* Floating cyan accent orb */}
      <div className="pointer-events-none absolute top-1/3 right-1/4 w-96 h-96 rounded-full bg-[rgb(var(--rgb-pulse-primary)/0.15)] blur-3xl" />

      <div className="relative max-w-7xl mx-auto px-6 pt-14 sm:pt-20 pb-20 sm:pb-28 lg:pt-28 lg:pb-36 grid lg:grid-cols-[1.15fr_0.85fr] gap-10 items-center min-h-[90vh]">
        <motion.div initial="hidden" animate="show" variants={stagger} className="relative z-10">
          <motion.div
            variants={FADE_UP}
            className="eyebrow inline-flex items-center gap-2 bg-[rgb(var(--rgb-pulse-primary)/0.12)] border border-[rgb(var(--rgb-pulse-primary)/0.35)] rounded-full px-4 py-1.5 text-[11px] font-bold text-white uppercase mb-8 backdrop-blur-sm"
          >
            {t('pulse.hero_badge', 'Pulse Fitness Self-Service Portal')}
          </motion.div>

          <motion.h1
            variants={FADE_UP}
            className="font-extrabold text-white leading-[0.92]"
            style={{
              fontSize: 'clamp(2.75rem, 9vw, 7.5rem)',
              letterSpacing: '-0.02em',
              fontFamily: "'Proxima Nova', sans-serif",
              textShadow: '0 2px 30px rgba(0,0,0,0.5)',
            }}
            data-testid="pulse-hero-headline"
          >
            <KineticWord />
            <br />
            {t('pulse.hero_your_gym', 'your gym.')}<br />
            <span style={{ fontWeight: 800, color: 'rgba(255,255,255,0.7)' }}>{t('pulse.hero_one_place', 'In one place.')}</span>
          </motion.h1>

          <motion.p
            variants={FADE_UP}
            className="mt-6 sm:mt-8 max-w-md text-base sm:text-lg leading-relaxed"
            style={{ color: 'rgba(255,255,255,0.95)', textShadow: '0 1px 18px rgba(0,0,0,0.7)' }}
          >
            {t('pulse.hero_sub', 'Log faults in seconds. Track every piece of kit. Get AI-assisted diagnostics before the engineer arrives — ')}
            <span className="font-bold" style={{ color: '#fff' }}>{t('pulse.hero_sub_bold', 'purpose-built for gym teams.')}</span>
          </motion.p>

          <motion.div variants={FADE_UP} className="mt-9 sm:mt-12 flex flex-wrap gap-3">
            <Button
              onClick={onSignIn}
              className="h-14 px-8 rounded-2xl text-sm !bg-[var(--pulse-primary)] !text-[var(--color-surface-dark-panel-alt)] hover:!bg-[var(--pulse-primary-deep)] shadow-xl shadow-[rgb(var(--rgb-pulse-primary)/0.3)] hover:shadow-2xl hover:shadow-[rgb(var(--rgb-pulse-primary)/0.4)] transition-all"
              style={{ backgroundColor: 'var(--pulse-primary)', color: 'var(--color-surface-dark-panel-alt)', fontWeight: 700, letterSpacing: '0.05em' }}
              data-testid="pulse-hero-login-btn"
            >
              <span className="inline-flex items-center" style={{ color: '#212721' }}><LogIn size={16} className="mr-2" /> {t('pulse.hero_login', 'LOG IN')}</span>
            </Button>
            <Button
              variant="outline"
              onClick={onSignIn}
              className="h-14 px-8 rounded-2xl text-sm border-2 !border-white/70 !text-white hover:!bg-white hover:!text-[var(--color-surface-dark-panel-alt)] !bg-transparent transition-all"
              style={{ fontWeight: 700, letterSpacing: '0.05em', color: '#fff' }}
              data-testid="pulse-hero-getstarted-btn"
            >
              {t('pulse.hero_get_started', 'GET STARTED')} <ArrowRight size={16} className="ml-2" />
            </Button>
          </motion.div>

          <motion.div variants={FADE_UP} className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-2 text-xs" style={{ color: 'rgba(255,255,255,0.75)' }}>
            <div className="flex items-center gap-1.5"><CheckCircle2 size={14} className="text-[var(--pulse-primary)]" /> {t('pulse.hero_check_1', 'No app install required')}</div>
            <div className="flex items-center gap-1.5"><CheckCircle2 size={14} className="text-[var(--pulse-primary)]" /> {t('pulse.hero_check_2', 'Works on any browser')}</div>
            <div className="flex items-center gap-1.5"><CheckCircle2 size={14} className="text-[var(--pulse-primary)]" /> {t('pulse.hero_check_3', '3-day free trial')}</div>
          </motion.div>
        </motion.div>

        {/* Floating mini-preview card, offset over gym image */}
        <motion.div
          initial={{ opacity: 0, y: 60, rotate: 2 }}
          animate={{ opacity: 1, y: 0, rotate: 0 }}
          transition={{ delay: 0.45, duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          className="relative hidden lg:block"
        >
          <div className="relative bg-white rounded-3xl border border-[var(--color-border-light)] shadow-[0_40px_90px_-20px_rgba(27,29,29,0.35)] overflow-hidden p-6 ml-auto max-w-sm" data-testid="pulse-hero-preview">
            <div className="flex items-center justify-between mb-5">
              <div>
                <div className="text-[11px] sm:text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-slate)]">{t('pulse.hero_card_eyebrow', 'Your gym · this month')}</div>
                <div className="text-sm font-bold text-[var(--color-surface-dark-panel-alt)] mt-1">{t('pulse.hero_card_title', 'Platform activity')}</div>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] sm:text-[10px] font-bold px-2 py-1 rounded-full bg-[rgb(var(--rgb-pulse-primary)/0.15)] text-[var(--pulse-primary)] uppercase tracking-wider">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--pulse-primary)] opacity-75 animate-ping" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--pulse-primary)]" />
                </span>
                {t('pulse.hero_live', 'Live')}
              </div>
            </div>

            <div className="space-y-3">
              {[
                { icon: Wrench, label: t('pulse.hero_stat_1', 'Jobs logged'), value: '1,284', trend: '+18%', highlight: false },
                { icon: ClipboardCheck, label: t('pulse.hero_stat_2', 'Check sheets completed'), value: '842', trend: '+24%', highlight: false },
                { icon: TrendingUp, label: t('pulse.hero_stat_3', 'Saved via self-fix'), value: '£12,450', trend: '+£3.1k', highlight: true },
              ].map(({ icon: Icon, label, value, trend, highlight }, i) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.9 + i * 0.15 }}
                  className={`flex items-center justify-between p-3 rounded-2xl border ${highlight ? 'border-[rgb(var(--rgb-pulse-primary)/0.4)] bg-gradient-to-br from-[rgb(var(--rgb-pulse-primary)/0.1)] to-transparent' : 'border-[var(--color-border-light)] bg-[var(--color-neutral-25)]'}`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${highlight ? 'bg-[rgb(var(--rgb-pulse-primary)/0.2)]' : 'bg-white'}`}>
                      <Icon size={15} className={highlight ? 'text-[var(--pulse-primary)]' : 'text-[var(--color-text-slate)]'} />
                    </div>
                    <div>
                      <div className="text-[11px] sm:text-[10px] uppercase tracking-wider text-[var(--color-text-slate)] font-semibold">{label}</div>
                      <div className="text-lg font-extrabold text-[var(--color-surface-dark-panel-alt)] mt-0.5" style={{ letterSpacing: '-0.02em' }}>{value}</div>
                    </div>
                  </div>
                  <div className={`text-xs font-bold ${highlight ? 'text-[var(--pulse-primary)]' : 'text-emerald-600'}`}>{trend}</div>
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

// ── What You Can Do ───────────────────────────────────────────
const CAPABILITIES = (t) => [
  { icon: Wrench,         title: 'Log faults in 30 seconds',       desc: '' },
  { icon: ClipboardCheck, title: t('pulse.cap2_t', 'Track every piece of kit'),       desc: t('pulse.cap2_d', 'Live register, install dates, serial numbers, warranty clocks, QR labels.') },
  { icon: FileText,       title: t('pulse.cap3_t', 'See warranties at a glance'),     desc: t('pulse.cap3_d', 'Never miss a claim window. Amber alerts fire 90 / 60 / 30 days before expiry.') },
  { icon: ClipboardList,  title: t('pulse.cap4_t', 'Hand over without missing a thing'), desc: t('pulse.cap4_d', 'AI-moderated shift diary on the gym floor. Every team. Every site. One source of truth.') },
  { icon: UserCog,        title: t('pulse.cap5_t', 'Smart Rota built in'),            desc: t('pulse.cap5_d', 'Drag-drop shifts, marketplace swaps, payroll CSV, AI optimises cover for you.') },
  { icon: Sparkles,       title: t('pulse.cap6_t', 'Marketing Suite & AI Studio'),    desc: t('pulse.cap6_d', 'Email + SMS journeys, AI Copilot writes copy in your brand voice, attribution built in.') },
];

function WhatYouCanDo() {
  const { t } = useTranslation();
  const caps = CAPABILITIES(t);
  return (
    <section id="capabilities" className="py-16 sm:py-20 bg-[var(--color-neutral-25)] border-y border-[var(--color-border-light)]" data-testid="pulse-capabilities">
      <div className="max-w-7xl mx-auto px-6">
        <SectionHeading
          eyebrow={t('pulse.nav_what', 'What you can do')}
          title={t('pulse.cap_title', "Everything you need. Nothing you don't.")}
          description={t('pulse.cap_desc', 'Built around the jobs your gym team actually does — log, track, claim, hand over.')}
          testId="capabilities-heading"
        />
        {/* Editorial stagger: first card is image-led, rest are text cards */}
        <Reveal className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-4 sm:gap-5">
          {/* Image hero card */}
          <motion.div
            variants={FADE_UP}
            whileHover={{ y: -6 }}
            transition={{ type: 'spring', stiffness: 300, damping: 20 }}
            className="lg:col-span-5 lg:row-span-2 relative rounded-3xl overflow-hidden min-h-[340px] lg:min-h-full group"
          >
            <div className="absolute inset-0 bg-cover bg-center transition-transform duration-700 group-hover:scale-110" style={{ backgroundImage: `url(${GYM_ACTION})` }} />
            <div className="absolute inset-0 bg-[var(--color-surface-dark-panel-alt)]/60" />
            <div className="absolute inset-0 bg-gradient-to-t from-[var(--color-surface-dark-panel-alt)] via-[var(--color-surface-dark-panel-alt)]/30 to-transparent" />
            <div className="relative h-full p-7 flex flex-col justify-end on-dark">
              <div className="inline-flex items-center gap-1.5 bg-[var(--pulse-primary)] text-[var(--color-surface-dark-panel-alt)] text-[10px] font-extrabold uppercase tracking-[0.15em] px-3 py-1 rounded-full mb-4 w-fit">
                <Wrench size={11} /> {t('pulse.cap_img_badge', 'Log faults')}
              </div>
              <h3 className="text-3xl sm:text-4xl font-extrabold leading-[1.05] mb-3" style={{ letterSpacing: '-0.01em', color: 'var(--color-white)', textShadow: '0 2px 24px rgba(0,0,0,0.9), 0 0 40px rgba(0,0,0,0.6)' }}>
                {t('pulse.cap_img_title_1', '30 seconds.')}<br />
                {t('pulse.cap_img_title_2', 'Photo. Fault. Done.')}
              </h3>
              <p className="text-sm max-w-xs leading-relaxed" style={{ color: 'rgba(255,255,255,0.92)', textShadow: '0 1px 16px rgba(0,0,0,0.85)' }}>
                {t('pulse.cap_img_desc', 'Snap a photo, tick the machine, describe the fault. AI drafts the supplier email in the background — you just hit send.')}
              </p>
            </div>
          </motion.div>

          {/* Two text capability cards beside the image */}
          {caps.slice(1, 3).map(({ icon: Icon, title, desc }) => (
            <motion.div
              key={title}
              variants={FADE_UP}
              whileHover={{ y: -4 }}
              transition={{ type: 'spring', stiffness: 300, damping: 20 }}
              className="lg:col-span-7 bg-white rounded-3xl p-7 sm:p-9 border border-[var(--color-border-light)] hover:border-[rgb(var(--rgb-pulse-primary)/0.4)] hover:shadow-xl transition-all duration-300"
              data-testid={`capability-${title.toLowerCase().split(' ')[0]}`}
            >
              <div className="flex items-start gap-5">
                <div className="w-12 h-12 rounded-2xl bg-[rgb(var(--rgb-pulse-primary)/0.1)] flex items-center justify-center flex-shrink-0">
                  <Icon size={22} className="text-[var(--pulse-primary)]" />
                </div>
                <div>
                  <h3 className="font-extrabold text-[var(--color-surface-dark-panel-alt)] text-xl sm:text-2xl tracking-tight mb-2" style={{ letterSpacing: '-0.01em' }}>{title}</h3>
                  <p className="text-sm text-[var(--color-text-slate)] leading-relaxed">{desc}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </Reveal>

        {/* Remaining three cards — even row below */}
        <Reveal className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-5 mt-4 sm:mt-5">
          {caps.slice(3).map(({ icon: Icon, title, desc }) => (
            <motion.div
              key={title}
              variants={FADE_UP}
              whileHover={{ y: -4 }}
              transition={{ type: 'spring', stiffness: 300, damping: 20 }}
              className="bg-white rounded-3xl p-7 border border-[var(--color-border-light)] hover:border-[rgb(var(--rgb-pulse-primary)/0.4)] hover:shadow-xl transition-all duration-300"
              data-testid={`capability-${title.toLowerCase().split(' ')[0]}`}
            >
              <div className="w-12 h-12 rounded-2xl bg-[rgb(var(--rgb-pulse-primary)/0.1)] flex items-center justify-center mb-5">
                <Icon size={22} className="text-[var(--pulse-primary)]" />
              </div>
              <h3 className="font-extrabold text-[var(--color-surface-dark-panel-alt)] text-xl tracking-tight mb-2" style={{ letterSpacing: '-0.01em' }}>{title}</h3>
              <p className="text-sm text-[var(--color-text-slate)] leading-relaxed">{desc}</p>
            </motion.div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

// ── AI Features (Ask orb) ─────────────────────────────────────
function AIFeatures() {
  const { t } = useTranslation();
  return (
    <section id="ai" className="py-20 bg-[var(--color-neutral-25)]" data-testid="pulse-ai">
      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-16 items-center">
        <div>
          <SectionHeading
            eyebrow={t('pulse.ai_eyebrow', 'AI assistance')}
            title={t('pulse.ai_title', 'Ask anything. Get an answer.')}
            description={t('pulse.ai_desc', 'The Ask orb is trained on your equipment, your warranties, and your supplier contracts. No hunting through PDFs.')}
            testId="ai-heading"
          />
          <div className="space-y-5">
            {[
              { icon: Brain, title: t('pulse.ai_f1_t', 'AI fault triage'), desc: t('pulse.ai_f1_d', 'Describe the problem in plain English — get likely cause, repair steps, and part numbers.') },
              { icon: Sparkles, title: t('pulse.ai_f2_t', 'Equipment diagnosis'), desc: t('pulse.ai_f2_d', 'Photo-based fault recognition for treadmills, cable machines, plate-loaded, and cardio.') },
              { icon: BookOpen, title: t('pulse.ai_f3_t', 'Document Q&A'), desc: t('pulse.ai_f3_d', 'Upload manuals once — ask questions forever.') },
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} className="flex gap-4">
                <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 flex items-center justify-center flex-shrink-0">
                  <Icon size={16} className="text-[var(--pulse-primary)]" />
                </div>
                <div>
                  <div className="font-semibold text-[var(--color-surface-dark-panel-alt)]">{title}</div>
                  <div className="text-sm text-[var(--color-text-slate)] mt-0.5 leading-relaxed">{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Ask orb mock */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          className="relative"
        >
          <div className="relative bg-white rounded-3xl border border-slate-200 shadow-[0_20px_60px_-15px_rgba(37,99,235,0.25)] p-6" data-testid="pulse-ask-orb-mock">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[var(--pulse-primary)] to-[var(--color-violet-600)] flex items-center justify-center shadow-md shadow-[rgb(var(--rgb-pulse-primary)/0.3)]">
                <Sparkles size={18} className="text-white" />
              </div>
              <div>
                <div className="font-bold text-[var(--color-surface-dark-panel-alt)]">Ask Pulse</div>
                <div className="text-xs text-emerald-600 flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> {t('pulse.ai_online', 'Online')}
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <motion.div
                initial={{ opacity: 0, x: 20 }} whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }} transition={{ delay: 0.3 }}
                className="ml-8 rounded-2xl rounded-tr-sm bg-[var(--color-surface-dark-panel-alt)] p-3 text-sm"
                style={{ color: '#ffffff' }}
              >
                {t('pulse.ai_q', 'Why is treadmill #7 belt slipping when incline > 8%?')}
              </motion.div>
              <motion.div
                initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }} transition={{ delay: 0.7 }}
                className="mr-8 rounded-2xl rounded-tl-sm bg-slate-50 border border-slate-200 p-3 text-sm text-[var(--color-surface-dark-panel-alt)]"
              >
                <div className="font-semibold mb-1.5">{t('pulse.ai_a_title', 'Likely cause: belt tension drift')}</div>
                <div className="text-xs text-[var(--color-text-slate)] leading-relaxed">
                  {t('pulse.ai_a_body', 'Under high incline loads, the drive belt typically loses 8–12% tension after 6+ months. Check: (1) belt deck alignment, (2) tension bolt torque (22 N·m), (3) deck lubrication. Estimated fix time: 25 min. ')}
                  <span className="text-[var(--pulse-primary)] font-semibold">{t('pulse.ai_a_cta', 'Log this fault →')}</span>
                </div>
              </motion.div>
              <motion.div
                initial={{ opacity: 0 }} whileInView={{ opacity: 1 }}
                viewport={{ once: true }} transition={{ delay: 1.4 }}
                className="flex gap-2 flex-wrap"
              >
                {[t('pulse.ai_chip_1', 'Show manual'), t('pulse.ai_chip_2', 'Log fault'), t('pulse.ai_chip_3', 'Book engineer')].map((c) => (
                  <div key={c} className="text-xs px-3 py-1.5 rounded-full bg-[rgb(var(--rgb-pulse-primary)/0.1)] text-[var(--pulse-primary)] font-semibold cursor-pointer hover:bg-[rgb(var(--rgb-pulse-primary)/0.2)]">{c}</div>
                ))}
              </motion.div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

// ── How It Works ──────────────────────────────────────────────
const STEPS = (t) => [
  {
    icon: ClipboardCheck,
    title: t('pulse.step1_t', 'Your kit is already there'),
    desc: t('pulse.step1_d', 'Pulse pre-loads every machine, serial and warranty into your portal — no imports, no setup.'),
    img: '/pulse-photos/gym-cardio-angle.webp',
  },
  {
    icon: ListChecks,
    title: t('pulse.step2_t', 'Log faults'),
    desc: t('pulse.step2_d', 'Photo + description in 30 seconds. AI drafts the email for you.'),
    img: 'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=800&q=80',
  },
  {
    icon: MessageSquareHeart,
    title: t('pulse.step3_t', 'Get support'),
    desc: t('pulse.step3_d', 'AI triage, supplier thread, or help centre — whichever is fastest.'),
    img: 'https://images.unsplash.com/photo-1553877522-43269d4ea984?auto=format&fit=crop&w=800&q=80',
  },
  {
    icon: Trophy,
    title: t('pulse.step4_t', 'Stay operational'),
    desc: t('pulse.step4_d', 'Zero downtime drama. Clean audits. Happy members.'),
    img: 'https://images.pexels.com/photos/6922153/pexels-photo-6922153.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940&fm=webp',
  },
];

function HowItWorks() {
  const { t } = useTranslation();
  return (
    <section id="how" className="py-20 bg-white border-y border-[var(--color-border-light)]" data-testid="pulse-how">
      <div className="max-w-7xl mx-auto px-6">
        <SectionHeading
          eyebrow={t('pulse.how_eyebrow', 'How it works')}
          title={t('pulse.how_title', "Four steps. That's it.")}
          description={t('pulse.how_desc', 'No onboarding, no imports — sign in and your equipment is waiting for you.')}
          align="center"
          testId="how-heading"
        />
        <Reveal className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {STEPS(t).map(({ icon: Icon, title, desc, img }, i) => (
            <motion.div
              key={title}
              variants={FADE_UP}
              whileHover={{ y: -6 }}
              transition={{ type: 'spring', stiffness: 300, damping: 20 }}
              className="group relative rounded-3xl overflow-hidden bg-white border border-[var(--color-border-light)] hover:border-[rgb(var(--rgb-pulse-primary)/0.4)] hover:shadow-xl transition-all duration-300"
              data-testid={`step-${i + 1}`}
            >
              {/* Image header */}
              <div className="relative h-44 overflow-hidden">
                <div
                  className="absolute inset-0 bg-cover bg-center transition-transform duration-700 group-hover:scale-110"
                  style={{ backgroundImage: `url(${img})` }}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-[var(--color-surface-dark-panel-alt)]/80 via-[var(--color-surface-dark-panel-alt)]/30 to-transparent" />
                {/* Step number badge */}
                <div className="absolute top-3 left-3 w-9 h-9 rounded-full bg-[var(--pulse-primary)] text-[var(--color-surface-dark-panel-alt)] text-sm font-extrabold flex items-center justify-center shadow-lg" style={{ letterSpacing: 0 }}>
                  {i + 1}
                </div>
                {/* Icon chip in the corner */}
                <div className="absolute bottom-3 right-3 w-10 h-10 rounded-xl bg-white/95 backdrop-blur flex items-center justify-center shadow-md">
                  <Icon size={18} className="text-[var(--pulse-primary)]" />
                </div>
              </div>
              {/* Text */}
              <div className="p-5">
                <h3 className="font-extrabold text-[var(--color-surface-dark-panel-alt)] text-lg tracking-tight mb-1.5" style={{ letterSpacing: '-0.01em' }}>{title}</h3>
                <p className="text-sm text-[var(--color-text-slate)] leading-relaxed">{desc}</p>
              </div>
            </motion.div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

// ── Mobile Experience ─────────────────────────────────────────
function MobileExperience() {
  const { t } = useTranslation();
  return (
    <section className="py-20 bg-[var(--color-surface-dark-panel-alt)] relative overflow-hidden" data-theme="dark" data-testid="pulse-mobile">
      <div
        className="absolute inset-0 opacity-40"
        style={{ backgroundImage: `url(${GYM_EQUIPMENT})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
      />
      <div className="absolute inset-0 bg-gradient-to-br from-[var(--color-surface-dark-panel-alt)] via-[var(--color-surface-dark-panel-alt)]/90 to-transparent" />
      <div className="absolute top-1/2 -translate-y-1/2 right-0 w-96 h-96 rounded-full bg-[rgb(var(--rgb-pulse-primary)/0.2)] blur-3xl pointer-events-none" />
      <div className="relative max-w-7xl mx-auto px-6 grid lg:grid-cols-[1fr_1.2fr] gap-16 items-center">
        {/* Phone mock */}
        <motion.div
          initial={{ opacity: 0, rotate: -6, y: 30 }}
          whileInView={{ opacity: 1, rotate: -4, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          className="mx-auto max-w-[280px]"
        >
          <div className="bg-[var(--color-neutral-700)] rounded-[2.5rem] p-2.5 shadow-[0_30px_80px_-20px_rgba(37,99,235,0.4)] border border-white/10">
            <div className="bg-white rounded-[2rem] overflow-hidden">
              <div className="h-6 bg-white flex items-center justify-center">
                <div className="w-20 h-5 rounded-b-xl bg-[var(--color-neutral-700)]" />
              </div>
              <div className="p-4 min-h-[480px] bg-gradient-to-b from-white to-slate-50">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">{t('pulse.mob_scan_result', 'Scan result')}</div>
                <div className="text-base font-bold text-[var(--color-surface-dark-panel-alt)] mt-1">Pulse Fusion Treadmill #7</div>
                <div className="text-[11px] text-slate-500">Serial: PF-TR-44821</div>
                <div className="mt-4 p-3 rounded-xl bg-emerald-50 border border-emerald-100">
                  <div className="text-[10px] uppercase text-emerald-600 font-semibold">{t('pulse.mob_warranty', 'Warranty')}</div>
                  <div className="text-sm text-[var(--color-surface-dark-panel-alt)] font-semibold">{t('pulse.mob_warranty_val', 'Active · 14 months remaining')}</div>
                </div>
                <div className="mt-3 p-3 rounded-xl border border-slate-200">
                  <div className="text-[10px] uppercase text-slate-500 font-semibold">{t('pulse.mob_recent', 'Recent fault')}</div>
                  <div className="text-sm text-[var(--color-surface-dark-panel-alt)] mt-0.5">{t('pulse.mob_fault', 'Belt slipping at incline > 8%')}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">{t('pulse.mob_supplier', 'Supplier contacted · 2 hrs ago')}</div>
                </div>
                <button className="mt-4 w-full h-10 rounded-xl bg-[var(--pulse-primary)] text-white text-sm font-semibold">
                  {t('pulse.mob_log_new', 'Log new fault')}
                </button>
                <button className="mt-2 w-full h-10 rounded-xl border border-slate-200 text-[var(--color-surface-dark-panel-alt)] text-sm font-semibold">
                  {t('pulse.mob_history', 'View history')}
                </button>
              </div>
            </div>
          </div>
        </motion.div>

        <div>
          <Reveal className="max-w-xl">
            <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
              <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" /> {t('pulse.mob_eyebrow', 'Built for the gym floor')}
            </motion.div>
            <motion.h2 variants={FADE_UP} className="text-2xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-white leading-[1.15]">
              {t('pulse.mob_title', 'Scan. Log. Done.')}
            </motion.h2>
            <motion.p variants={FADE_UP} className="mt-4 text-base sm:text-lg text-white/70 max-w-lg">
              {t('pulse.mob_desc', 'Every piece of kit carries a branded QR label. Staff scan with any phone — no app install — and land straight on the right fault-log screen. Real-time updates push back to the dashboard.')}
            </motion.p>
            <motion.div variants={FADE_UP} className="mt-8 grid sm:grid-cols-2 gap-4">
              {[
                { icon: QrCode, label: t('pulse.mob_qr_t', 'Branded QR labels'), sub: t('pulse.mob_qr_d', 'Generated per asset') },
                { icon: Smartphone, label: t('pulse.mob_noapp_t', 'No app required'), sub: t('pulse.mob_noapp_d', 'Works in any browser') },
                { icon: Zap, label: t('pulse.mob_sync_t', 'Real-time sync'), sub: t('pulse.mob_sync_d', 'Dashboard updates instantly') },
                { icon: Eye, label: t('pulse.mob_audit_t', 'Full audit trail'), sub: t('pulse.mob_audit_d', 'Every action logged') },
              ].map(({ icon: Icon, label, sub }) => (
                <div key={label} className="flex gap-3 items-start">
                  <div className="w-9 h-9 rounded-xl bg-white/10 border border-white/10 flex items-center justify-center flex-shrink-0">
                    <Icon size={15} className="text-[var(--pulse-primary)]" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">{label}</div>
                    <div className="text-xs text-white/50">{sub}</div>
                  </div>
                </div>
              ))}
            </motion.div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

// ── Gym Floor Showcase ────────────────────────────────────────
// Auto-advancing 30-second mock demo: 4 steps showing how a shift worker
// logs an attributable fault from the shared site-generic login. Each step
// auto-progresses every 7.5s on a loop. CSS/Framer-Motion only — no video
// asset required, so it works everywhere immediately.

const GYM_FLOOR_STEPS = (t) => [
  {
    id: 'login',
    title: t('pulse.gf_s1_t', 'Sign in once per site'),
    body: t('pulse.gf_s1_b', 'A single shared credential the manager hands out — no per-staff accounts to maintain.'),
    chip: `${t('pulse.gf_step', 'Step')} 1`,
  },
  {
    id: 'pick',
    title: t('pulse.gf_s2_t', 'Pick your name'),
    body: t('pulse.gf_s2_b', 'Mandatory roster dropdown at the top of the card. Suppliers will see who actually logged it.'),
    chip: `${t('pulse.gf_step', 'Step')} 2`,
  },
  {
    id: 'log',
    title: t('pulse.gf_s3_t', 'Describe the fault'),
    body: t('pulse.gf_s3_b', "Pick the machine, write what's wrong, set severity. Done in under 30 seconds on a phone."),
    chip: `${t('pulse.gf_step', 'Step')} 3`,
  },
  {
    id: 'email',
    title: t('pulse.gf_s4_t', 'Supplier email auto-attributed'),
    body: t('pulse.gf_s4_b', 'Engineer gets a clean ticket with a "Reported by" block — name, email, mobile, all click-to-call.'),
    chip: `${t('pulse.gf_step', 'Step')} 4`,
  },
];

function GymFloorPhoneFrame({ step }) {
  // Each step renders a different mock screen inside the phone frame. We
  // use Framer's AnimatePresence-style approach with `key` swaps + Tailwind
  // transitions so the screens cross-fade as the user auto-advances.
  return (
    <div
      className="relative mx-auto w-[280px] sm:w-[300px] aspect-[9/19] rounded-[36px] bg-[var(--color-ink)] border-[10px] border-[var(--color-surface-dark-panel-alt)] shadow-[0_30px_80px_-20px_rgba(25,205,255,0.35)] overflow-hidden"
      data-testid="gym-floor-phone-frame"
    >
      {/* Notch */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-24 h-5 bg-[var(--color-surface-dark-panel-alt)] rounded-b-2xl z-10" />

      {/* Screen content */}
      <div className="absolute inset-0 pt-6">
        {step === 'login' && (
          <motion.div
            key="login"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            className="px-5 py-8 h-full flex flex-col"
            data-testid="phone-screen-login"
          >
            <div className="text-center mb-6">
              <div className="w-12 h-12 rounded-2xl bg-[rgb(var(--rgb-pulse-primary)/0.2)] text-[var(--pulse-primary)] grid place-items-center mx-auto mb-3">
                <ClipboardList size={20} />
              </div>
              <p className="text-white text-base font-bold">Gym Floor</p>
              <p className="text-[10px] text-white/50">Shared staff login · Handover Diary</p>
            </div>
            <div className="space-y-3">
              <div>
                <p className="text-[9px] text-white/40 uppercase tracking-wider mb-1">Username</p>
                <div className="h-8 rounded-md bg-white/5 border border-white/10 px-2 flex items-center text-[11px] text-white/80 font-mono">
                  studio-floor
                </div>
              </div>
              <div>
                <p className="text-[9px] text-white/40 uppercase tracking-wider mb-1">Password</p>
                <div className="h-8 rounded-md bg-white/5 border border-white/10 px-2 flex items-center text-[11px] text-white/80 tracking-widest">
                  ••••••••
                </div>
              </div>
              <motion.div
                animate={{ scale: [1, 1.04, 1] }}
                transition={{ duration: 1.4, repeat: Infinity }}
                className="h-9 rounded-full bg-[var(--pulse-primary)] text-[var(--color-ink)] grid place-items-center text-xs font-bold"
              >
                Sign in
              </motion.div>
            </div>
          </motion.div>
        )}

        {step === 'pick' && (
          <motion.div
            key="pick"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="px-3 py-4 h-full flex flex-col"
            data-testid="phone-screen-pick"
          >
            <div className="flex gap-1 p-1 rounded-md bg-white/5 mb-3">
              <div className="flex-1 h-6 rounded text-[9px] text-white/50 grid place-items-center">Diary</div>
              <div className="flex-1 h-6 rounded bg-[var(--pulse-primary)] text-[var(--color-ink)] text-[9px] font-bold grid place-items-center">Log a Fault</div>
            </div>
            <div className="rounded-lg p-3 border-2 border-[var(--pulse-primary)] bg-[rgb(var(--rgb-pulse-primary)/0.05)] mb-3">
              <p className="text-[9px] font-bold text-[var(--pulse-primary)] uppercase mb-1.5 flex items-center gap-1">
                <User size={9} /> Who's logging this fault? *
              </p>
              <motion.div
                initial={{ background: 'rgba(255,255,255,0.05)' }}
                animate={{ background: ['rgba(255,255,255,0.05)', 'rgba(25,205,255,0.18)', 'rgba(255,255,255,0.05)'] }}
                transition={{ duration: 2, repeat: Infinity }}
                className="h-8 rounded-md border border-white/10 px-2 flex items-center justify-between text-[11px] text-white"
              >
                <span className="font-semibold">Floor Member</span>
                <ChevronRight size={10} className="rotate-90 text-white/40" />
              </motion.div>
              <p className="text-[8px] text-white/50 mt-1.5 leading-tight">
                We'll attach the member's contact details to the supplier ticket.
              </p>
            </div>
            <div className="space-y-2 opacity-50">
              <div className="h-8 rounded-md bg-white/5 border border-white/10" />
              <div className="h-14 rounded-md bg-white/5 border border-white/10" />
            </div>
          </motion.div>
        )}

        {step === 'log' && (
          <motion.div
            key="log"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="px-3 py-4 h-full flex flex-col"
            data-testid="phone-screen-log"
          >
            <div className="rounded-md bg-[rgb(var(--rgb-pulse-primary)/0.1)] border border-[rgb(var(--rgb-pulse-primary)/0.3)] px-2 py-1.5 mb-2 flex items-center gap-1.5">
              <CheckCircle2 size={10} className="text-[var(--pulse-primary)]" />
              <span className="text-[9px] text-[var(--pulse-primary)] font-semibold">Floor Member</span>
            </div>
            <div className="space-y-2">
              <div className="h-7 rounded-md bg-white/5 border border-white/10 px-2 flex items-center text-[10px] text-white">
                Treadmill (3)
              </div>
              <div className="h-14 rounded-md bg-white/5 border border-white/10 p-2 text-[9px] text-white/80 leading-tight">
                Belt slipping under load when running &gt;12kph. Needs adjustment.
                <motion.span
                  animate={{ opacity: [1, 0, 1] }}
                  transition={{ duration: 0.8, repeat: Infinity }}
                  className="inline-block w-px h-2 bg-[var(--pulse-primary)] ml-0.5"
                />
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <div className="h-7 rounded-md bg-white/5 border border-white/10 grid place-items-center text-[8px] text-white/50">Minor</div>
                <motion.div
                  animate={{ borderColor: ['rgba(25,205,255,0.4)', 'rgba(25,205,255,1)', 'rgba(25,205,255,0.4)'] }}
                  transition={{ duration: 1.2, repeat: Infinity }}
                  className="h-7 rounded-md bg-[rgb(var(--rgb-pulse-primary)/0.1)] border-2 border-[var(--pulse-primary)] grid place-items-center text-[8px] text-[var(--pulse-primary)] font-bold"
                >
                  Fault present
                </motion.div>
                <div className="h-7 rounded-md bg-white/5 border border-white/10 grid place-items-center text-[8px] text-white/50">Non-op</div>
                <div className="h-7 rounded-md bg-white/5 border border-white/10 grid place-items-center text-[8px] text-white/50">Safety</div>
              </div>
              <motion.div
                animate={{ scale: [1, 1.03, 1] }}
                transition={{ duration: 1.2, repeat: Infinity }}
                className="h-9 rounded-full bg-[var(--pulse-primary)] text-[var(--color-ink)] grid place-items-center text-[11px] font-bold flex items-center justify-center gap-1.5"
              >
                <AlertTriangle size={11} /> Log fault report
              </motion.div>
            </div>
          </motion.div>
        )}

        {step === 'email' && (
          <motion.div
            key="email"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="absolute inset-0 bg-white p-3 overflow-hidden"
            data-testid="phone-screen-email"
          >
            <div className="text-[8px] text-slate-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
              <Mail size={9} /> Inbox · supplier@pulsefitness.com
            </div>
            <div className="rounded-lg border border-slate-200 overflow-hidden shadow-sm">
              <div className="bg-[var(--color-ink-alt)] px-3 py-2">
                <p className="text-white text-[10px] font-bold m-0">Example Gym — Fault Communication</p>
                <p className="text-white/50 text-[7px] m-0">via Pulse Fitness</p>
              </div>
              <div className="p-2.5 space-y-2">
                <div className="rounded-md bg-amber-50 border border-amber-200 px-2 py-1.5">
                  <p className="text-[7px] font-bold text-amber-800 uppercase tracking-wider">Job FLT-867FCD16 · Treadmill · 0004958</p>
                  <p className="text-[8px] text-slate-800 mt-0.5"><strong>Fault:</strong> Belt slipping under load…</p>
                </div>
                <motion.div
                  initial={{ scale: 0.9, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ delay: 0.4, duration: 0.5 }}
                  className="rounded-md bg-sky-50 border-2 border-sky-300 px-2 py-1.5"
                >
                  <p className="text-[7px] font-bold text-sky-700 uppercase tracking-wider mb-0.5">Reported by</p>
                  <p className="text-[10px] font-bold text-slate-900 m-0">
                    Floor Member
                    <span className="ml-1 inline-block bg-sky-100 text-sky-700 text-[6px] font-bold px-1 py-0.5 rounded uppercase">Gym Floor</span>
                  </p>
                  <p className="text-[8px] text-slate-700 mt-0.5">
                    <span className="text-sky-600 underline">member@example.com</span>
                    <span className="mx-1">·</span>
                    <span className="text-sky-600 underline">+44 7700 900000</span>
                  </p>
                </motion.div>
                <div className="rounded-md bg-slate-50 border-l-2 border-blue-400 px-2 py-1.5">
                  <p className="text-[7px] font-bold text-slate-600 m-0">Gym Manager</p>
                  <p className="text-[8px] text-slate-800 mt-0.5">Hi, please look into this when possible.</p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function GymFloorShowcase() {
  const { t } = useTranslation();
  const steps = GYM_FLOOR_STEPS(t);
  const [stepIdx, setStepIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const STEP_DURATION = 7500; // 7.5s per step → 30s full loop

  useEffect(() => {
    if (paused) return undefined;
    const timer = setTimeout(() => setStepIdx((i) => (i + 1) % steps.length), STEP_DURATION);
    return () => clearTimeout(timer);
  }, [stepIdx, paused, steps.length]);

  const active = steps[stepIdx];

  return (
    <section
      className="relative py-20 overflow-hidden"
      style={{
        background: 'linear-gradient(180deg, var(--color-ink) 0%, #14181F 100%)',
      }}
      data-theme="dark"
      data-testid="pulse-gym-floor-showcase"
    >
      {/* Real Pulse strength-floor photography, dimmed to keep copy legible */}
      <div
        className="absolute inset-0 opacity-[0.18] pointer-events-none bg-cover bg-center"
        style={{ backgroundImage: 'url(/pulse-photos/strength-floor.webp)' }}
      />
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'linear-gradient(180deg, rgba(20,24,31,0.7) 0%, transparent 40%, rgba(20,24,31,0.7) 100%)' }} />
      {/* Decorative grid texture — reads as "operations / shift floor" */}
      <div
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle, var(--pulse-primary) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}
      />

      <div className="relative max-w-7xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
        {/* Left — Phone mock */}
        <Reveal className="lg:col-span-5 flex justify-center" testId="gym-floor-phone-col">
          <motion.div variants={FADE_UP} className="relative">
            <GymFloorPhoneFrame step={active.id} />

            {/* Step pips below the phone */}
            <div className="flex items-center justify-center gap-1.5 mt-6" data-testid="gym-floor-step-pips">
              {steps.map((s, i) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => { setStepIdx(i); setPaused(false); }}
                  onMouseEnter={() => setPaused(true)}
                  onMouseLeave={() => setPaused(false)}
                  className="h-1.5 rounded-full transition-all"
                  style={{
                    width: i === stepIdx ? 28 : 10,
                    background: i === stepIdx ? 'var(--pulse-primary)' : 'rgba(255,255,255,0.18)',
                  }}
                  aria-label={`Go to ${s.chip}`}
                  data-testid={`gym-floor-step-pip-${i}`}
                />
              ))}
            </div>
          </motion.div>
        </Reveal>

        {/* Right — Copy + step list */}
        <Reveal className="lg:col-span-7" testId="gym-floor-copy-col">
          <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
            <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" />
            {t('pulse.gf_eyebrow', 'New for Managed')}
          </motion.div>
          <motion.h2 variants={FADE_UP} className="text-2xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-white leading-[1.15] mb-5">
            {t('pulse.gf_title', 'Gym Floor — every fault, attributed to a real person.')}
          </motion.h2>
          <motion.p variants={FADE_UP} className="text-base text-white/70 mb-8 max-w-xl leading-relaxed">
            {t('pulse.gf_desc', 'One shared site login your shift staff actually use. They pick their name from a roster before logging anything, so suppliers always know who to call back. No per-staff accounts. No more "logged by site" mystery tickets.')}
          </motion.p>

          <Reveal className="space-y-3" testId="gym-floor-step-list">
            {steps.map((s, i) => {
              const isActive = i === stepIdx;
              return (
                <motion.button
                  key={s.id}
                  variants={FADE_UP}
                  type="button"
                  onClick={() => { setStepIdx(i); setPaused(false); }}
                  onMouseEnter={() => setPaused(true)}
                  onMouseLeave={() => setPaused(false)}
                  className="w-full text-left flex items-start gap-3 p-4 rounded-xl border transition-all"
                  style={{
                    borderColor: isActive ? 'rgba(25,205,255,0.5)' : 'rgba(255,255,255,0.08)',
                    background: isActive ? 'rgba(25,205,255,0.06)' : 'rgba(255,255,255,0.02)',
                  }}
                  data-testid={`gym-floor-step-${s.id}`}
                >
                  <div
                    className="shrink-0 w-7 h-7 rounded-lg grid place-items-center text-[10px] font-bold transition-colors"
                    style={{
                      background: isActive ? 'var(--pulse-primary)' : 'rgba(255,255,255,0.06)',
                      color: isActive ? 'var(--color-ink)' : 'rgba(255,255,255,0.5)',
                    }}
                  >
                    {i + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-white m-0">{s.title}</p>
                    <p className="text-[12px] text-white/55 mt-0.5 leading-relaxed">{s.body}</p>
                  </div>
                  {isActive && (
                    <motion.div
                      layoutId="gym-floor-active-arrow"
                      className="shrink-0 mt-1 text-[var(--pulse-primary)]"
                    >
                      <ChevronRight size={16} />
                    </motion.div>
                  )}
                </motion.button>
              );
            })}
          </Reveal>

          <motion.div variants={FADE_UP} className="mt-8 flex flex-wrap gap-3 items-center">
            <a
              href="#how"
              className="inline-flex items-center gap-2 px-5 py-3 rounded-full bg-[var(--pulse-primary)] hover:bg-[rgb(var(--rgb-pulse-primary)/0.9)] text-[var(--color-ink)] text-sm font-bold transition-colors"
              data-testid="gym-floor-cta-how"
            >
              {t('pulse.gf_cta', 'See how it fits the workflow')} <ArrowRight size={14} />
            </a>
            <span className="text-[11px] text-white/40">
              {t('pulse.gf_note', 'Included on Managed · No extra cost')}
            </span>
          </motion.div>
        </Reveal>
      </div>
    </section>
  );
}

// ── Customer Benefits ─────────────────────────────────────────
const BENEFITS = (t) => [
  { icon: TrendingDown, stat: t('pulse.ben1_s', 'Less'), label: t('pulse.ben1_l', 'Equipment downtime'), sub: t('pulse.ben1_d', 'Catch faults early, fix them faster') },
  { icon: Timer, stat: t('pulse.ben2_s', 'Faster'), label: t('pulse.ben2_l', 'Fault reporting'), sub: t('pulse.ben2_d', 'No more chasing by email or phone') },
  { icon: Eye, stat: t('pulse.ben3_s', 'Audit-ready'), label: t('pulse.ben3_l', 'End-to-end visibility'), sub: t('pulse.ben3_d', 'Timestamped from log to close') },
];

function CustomerBenefits() {
  const { t } = useTranslation();
  return (
    <section className="py-20 bg-white border-y border-slate-200" data-testid="pulse-benefits">
      <div className="max-w-7xl mx-auto px-6">
        <SectionHeading
          eyebrow={t('pulse.ben_eyebrow', 'Customer benefits')}
          title={t('pulse.ben_title', 'Designed for the ops director.')}
          description={t('pulse.ben_desc', 'Built with input from the teams who actually run gym estates.')}
          align="center"
          testId="benefits-heading"
        />
        <Reveal className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {BENEFITS(t).map(({ icon: Icon, stat, label, sub }) => (
            <motion.div
              key={label}
              variants={FADE_UP}
              whileHover={{ y: -4 }}
              className="p-8 rounded-2xl border border-slate-200 bg-white shadow-sm hover:shadow-lg transition-all duration-300"
              data-testid={`benefit-${label.toLowerCase().split(' ')[0]}`}
            >
              <Icon size={22} className="text-[var(--pulse-primary)] mb-5" />
              <div className="text-4xl font-extrabold text-[var(--color-surface-dark-panel-alt)] tracking-tight" style={{ letterSpacing: '-0.02em' }}>{stat}</div>
              <div className="mt-3 font-semibold text-[var(--color-surface-dark-panel-alt)]">{label}</div>
              <div className="mt-1 text-sm text-[var(--color-text-slate)]">{sub}</div>
            </motion.div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

// ── Support ───────────────────────────────────────────────────
function Support() {
  const { t } = useTranslation();
  return (
    <section id="support" className="py-20 bg-[var(--color-neutral-25)]" data-testid="pulse-support">
      <div className="max-w-7xl mx-auto px-6">
        <SectionHeading
          eyebrow={t('pulse.sup_eyebrow', 'Always here')}
          title={t('pulse.sup_title', 'Support that actually supports.')}
          description={t('pulse.sup_desc', 'AI first, humans second, supplier direct if needed — three routes to an answer.')}
          align="center"
          testId="support-heading"
        />
        <Reveal className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {[
            { icon: Sparkles, title: t('pulse.sup1_t', 'AI Support'), desc: t('pulse.sup1_d', 'In-app Ask orb. Available 24/7. Escalates to a human when you need one.') },
            { icon: Phone, title: t('pulse.sup2_t', 'Direct to suppliers'), desc: t('pulse.sup2_d', 'Threaded conversations with every supplier, full fault context attached.') },
            { icon: BookOpen, title: t('pulse.sup3_t', 'Help centre'), desc: t('pulse.sup3_d', 'Searchable guides, video walkthroughs, and templates for common workflows.') },
          ].map(({ icon: Icon, title, desc }) => (
            <motion.div
              key={title}
              variants={FADE_UP}
              whileHover={{ y: -4 }}
              className="p-7 rounded-2xl bg-white border border-slate-200 shadow-sm hover:shadow-lg transition-all duration-300"
              data-testid={`support-${title.toLowerCase().split(' ')[0]}`}
            >
              <div className="w-11 h-11 rounded-xl bg-[rgb(var(--rgb-pulse-primary)/0.1)] flex items-center justify-center mb-5">
                <Icon size={20} className="text-[var(--pulse-primary)]" />
              </div>
              <h3 className="font-bold text-[var(--color-surface-dark-panel-alt)] text-lg mb-2">{title}</h3>
              <p className="text-sm text-[var(--color-text-slate)] leading-relaxed">{desc}</p>
            </motion.div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

// ── Lite vs Pro Plans ─────────────────────────────────────────
// Reinstates the Lite/Pro tier differentiation that the homepage
// redesign removed. Lite is free for Pulse Fitness customers; Pro
// pricing is handled through the account manager (TBD).
export function PlansLitePro({ onSignIn, onUpgrade }) {
  const { t } = useTranslation();
  const LITE_FEATURES = [
    t('pulse.lite_f1', 'Equipment management'),
    t('pulse.lite_f2', 'Fault logging + QR scanning'),
    t('pulse.lite_f3', 'Document storage'),
    t('pulse.lite_f4', 'Dashboard overview'),
    t('pulse.lite_f5', 'Warranty tracking'),
    t('pulse.lite_f6', 'Supplier directory'),
    t('pulse.lite_f7', 'Mobile PWA access'),
  ];
  const PRO_FEATURES = [
    t('pulse.pro_f1', 'Everything in Lite'),
    t('pulse.pro_f2', 'AI Fault Diagnosis (chat)'),
    t('pulse.pro_f3', 'AI Audit Report Generation'),
    t('pulse.pro_f4', 'Check Sheets (daily / weekly / monthly)'),
    t('pulse.pro_f5', 'Operational Reports + KPI Engine'),
    t('pulse.pro_f6', 'Risk Assessments with auto-scoring'),
    t('pulse.pro_f7', 'Gym Layout Designer'),
    t('pulse.pro_f8', 'Supplier Management + PO workflow'),
    t('pulse.pro_f9', 'Weekly Digest Emails'),
    t('pulse.pro_f10', 'Staff Performance Tracking'),
    t('pulse.pro_f11', 'Cost Savings Analytics'),
  ];

  return (
    <section
      id="pulse-plans"
      className="relative py-20 bg-gradient-to-b from-white to-slate-50 overflow-hidden"
      data-testid="pulse-plans-section"
    >
      {/* Subtle brand glow */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[48rem] h-[24rem] rounded-full bg-[rgb(var(--rgb-pulse-primary)/0.08)] blur-[120px]" />
      </div>

      <div className="relative max-w-6xl mx-auto px-6">
        <SectionHeading
          eyebrow="For Pulse Fitness equipment customers"
          title={t('pulse.plans_title', 'Your equipment portal — included.')}
          description={t('pulse.plans_desc', 'Every Pulse Fitness equipment customer gets the Lite portal free. Upgrade to Managed any time for AI diagnostics, automated check sheets, and operational reporting handled by your account manager.')}
          align="center"
          testId="pulse-plans-heading"
        />

        <div className="mt-14 grid grid-cols-1 md:grid-cols-2 gap-6 max-w-5xl mx-auto">
          {/* ── Lite card ── */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            whileHover={{ y: -4 }}
            className="relative rounded-2xl bg-white border border-slate-200 shadow-sm p-8 sm:p-10 overflow-hidden transition-all hover:shadow-lg"
            data-testid="pulse-plan-lite"
          >
            <div className="flex items-start justify-between gap-4 mb-2">
              <div>
                <div className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-text-slate)] mb-3">
                  <CheckCircle2 size={11} className="text-emerald-500" />
                  {t('pulse.plan_lite_badge', 'Pulse Fitness Customers')}
                </div>
                <h3 className="text-[var(--color-surface-dark-panel-alt)] font-extrabold text-2xl tracking-tight" style={{ letterSpacing: '-0.01em' }}>
                  Lite
                </h3>
              </div>
              <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider">
                {t('pulse.plan_free', 'Free')}
              </span>
            </div>
            <p className="text-[var(--color-text-slate)] text-sm leading-relaxed min-h-[3rem]">
              {t('pulse.plan_lite_desc', 'Everything a Pulse Fitness site needs to track equipment, log faults, and keep a clean audit trail. Included in your Pulse Fitness agreement — no card, no contract.')}
            </p>

            <div className="mt-6 flex items-baseline gap-2">
              <span className="text-[var(--color-surface-dark-panel-alt)] font-extrabold tracking-tight" style={{ fontSize: '3rem', letterSpacing: '-0.03em', lineHeight: 1 }}>
                £0
              </span>
              <span className="text-sm text-[var(--color-text-slate)]">{t('pulse.plan_forever', 'forever')}</span>
            </div>

            <Button
              onClick={onSignIn}
              className="w-full h-12 mt-6 rounded-xl font-bold text-sm bg-white hover:bg-slate-50 text-[var(--color-surface-dark-panel-alt)] border-2 border-slate-200 hover:border-[var(--pulse-primary)] uppercase tracking-wider"
              style={{ letterSpacing: '0.05em' }}
              data-testid="pulse-plan-lite-cta"
            >
              <LogIn size={14} className="mr-2" /> {t('pulse.plan_lite_cta', 'Sign in to your portal')}
            </Button>

            <div className="mt-8 pt-6 border-t border-slate-100">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-text-slate)] mb-4">{t('pulse.plan_included', 'Included')}</div>
              <ul className="space-y-2.5">
                {LITE_FEATURES.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm text-[var(--color-surface-dark-panel-alt)] leading-relaxed">
                    <Check size={15} className="text-emerald-500 mt-0.5 shrink-0" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          </motion.div>

          {/* ── Pro card (highlighted) ── */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.12 }}
            whileHover={{ y: -6 }}
            className="relative rounded-2xl bg-gradient-to-b from-[rgb(var(--rgb-pulse-primary)/0.08)] via-white to-white border-2 border-[rgb(var(--rgb-pulse-primary)/0.4)] p-8 sm:p-10 transition-all hover:shadow-[0_0_50px_rgba(25,205,255,0.25)]"
            style={{ boxShadow: '0 20px 60px rgba(25,205,255,0.15)' }}
            data-testid="pulse-plan-pro"
          >
            {/* Glow accent — clipped inside its own layer so the "Most
                Popular" badge (absolutely positioned above the card edge)
                isn't cut off by overflow-hidden on the card itself. */}
            <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl">
              <div className="absolute -top-20 -right-20 w-64 h-64 bg-[rgb(var(--rgb-pulse-primary)/0.15)] blur-[100px] rounded-full" />
            </div>

            <div className="absolute -top-3 left-8">
              <span className="bg-[var(--pulse-primary)] text-[var(--color-surface-darker)] text-[10px] font-extrabold px-3 py-1 rounded-full flex items-center gap-1 uppercase tracking-wider shadow-[0_0_20px_rgba(25,205,255,0.5)]">
                <Star size={10} /> {t('pulse.plan_popular', 'Most Popular')}
              </span>
            </div>

            <div className="relative">
              <div className="flex items-start justify-between gap-4 mb-2 mt-2">
                <div>
                  <div className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--pulse-primary)] mb-3">
                    <Sparkles size={11} /> {t('pulse.plan_ai_powered', 'AI-Powered')}
                  </div>
                  <h3 className="text-[var(--color-surface-dark-panel-alt)] font-extrabold text-2xl tracking-tight" style={{ letterSpacing: '-0.01em' }}>
                    Managed
                  </h3>
                </div>
                <span className="bg-white border border-slate-200 text-[var(--color-surface-dark-panel-alt)] text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider">
                  {t('pulse.plan_upgrade', 'Upgrade')}
                </span>
              </div>
              <p className="text-[var(--color-text-slate)] text-sm leading-relaxed min-h-[3rem]">
                {t('pulse.plan_pro_desc', 'The full Pulse Fitness operating suite — AI triage, automated check sheets, operational reports, risk assessments and KPI tracking.')}
              </p>

              <div className="mt-6 flex items-baseline gap-2">
                <span className="text-[var(--color-surface-dark-panel-alt)] font-extrabold tracking-tight" style={{ fontSize: '2rem', letterSpacing: '-0.02em', lineHeight: 1 }}>
                  {t('pulse.plan_talk', 'Talk to us')}
                </span>
                <span className="text-sm text-[var(--color-text-slate)]">{t('pulse.plan_tailored', '· pricing tailored to your estate')}</span>
              </div>

              <Button
                onClick={onUpgrade}
                className="w-full h-12 mt-6 rounded-xl font-bold text-sm uppercase tracking-wider transition-colors"
                style={{
                  background: 'linear-gradient(135deg, var(--pulse-primary) 0%, var(--pulse-primary-deep) 100%)',
                  color: 'var(--color-surface-darker)',
                  letterSpacing: '0.05em',
                  boxShadow: '0 0 30px rgba(25,205,255,0.35)',
                }}
                data-testid="pulse-plan-pro-cta"
              >
                <Zap size={14} className="mr-2" /> {t('pulse.plan_request', 'Request Upgrade')} <ArrowRight size={14} className="ml-1.5" />
              </Button>

              <div className="mt-8 pt-6 border-t border-slate-100">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--pulse-primary)] mb-4">{t('pulse.plan_pro_includes', 'Managed includes')}</div>
                <ul className="space-y-2.5">
                  {PRO_FEATURES.map((f, i) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm text-[var(--color-surface-dark-panel-alt)] leading-relaxed">
                      <Check size={15} className={`${i === 0 ? 'text-emerald-500' : 'text-[var(--pulse-primary)]'} mt-0.5 shrink-0`} />
                      <span className={i === 0 ? 'font-semibold' : ''}>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Footnote */}
        <div className="mt-10 text-center">
          <p className="text-xs text-[var(--color-text-slate)] max-w-xl mx-auto">
            {t('pulse.plan_footnote', 'Lite is free for active Pulse Fitness equipment customers. Managed upgrades are handled by your Pulse Fitness account manager. Already upgraded?')}{' '}
            <button
              type="button"
              onClick={onSignIn}
              className="text-[var(--pulse-primary)] font-semibold hover:underline"
              data-testid="pulse-plans-signin-link"
            >
              {t('pulse.plan_signin_here', 'Sign in here')}
            </button>.
          </p>
        </div>
      </div>
    </section>
  );
}


// ── Tailored to your gym ────────────────────────────────────
//
// Mirrors the Pulse Fitness "Tailored" section but in Pulse's light theme.
// Operators picking Pulse Pro want the same reassurance: their gym
// chain doesn't slot into a one-size-fits-all SaaS, and that's fine —
// every important behaviour can be configured at the org level.
const TAILORING_PILLARS = (t) => [
  { icon: Sliders,    title: t('pulse.tai1_t', 'Modules on or off'),       desc: t('pulse.tai1_d', 'Memberships, Marketing, Smart Rota, AI Studio — turn on only what your team will use today. Add the rest in a click.') },
  { icon: Layers,     title: t('pulse.tai2_t', 'Your brand, your domain'), desc: t('pulse.tai2_d', 'Logo, colours, custom domain, branded emails — your members never see a third-party platform.') },
  { icon: UserCog,    title: t('pulse.tai3_t', 'Roles built around you'),  desc: t('pulse.tai3_d', 'Beyond owner / manager / staff. Build a "Maintenance Engineer" role that touches faults but never member data. Audited.') },
  { icon: Workflow,   title: t('pulse.tai4_t', 'Workflows you control'),   desc: t('pulse.tai4_d', 'Rota rules, fault thresholds, SLA windows, supplier dispatch — all driven by org-level settings, not hard-coded.') },
  { icon: Smartphone, title: t('pulse.tai5_t', 'Build your member app'),   desc: t('pulse.tai5_d', 'Drag-and-drop the cards your members see — class booking, PT enquiries, rewards — without touching code.') },
  { icon: Link2,      title: t('pulse.tai6_t', 'Open integrations'),       desc: t('pulse.tai6_d', 'Bring your stack — webhooks and an open API mean you can plug in the tools you already use.') },
];

function TailoredPulse() {
  const { t } = useTranslation();
  return (
    <section className="py-16 sm:py-20 bg-white border-y border-[var(--color-border-light)]" data-testid="pulse-tailored">
      <div className="max-w-7xl mx-auto px-6">
        <SectionHeading
          eyebrow={t('pulse.tai_eyebrow', 'Tailored to you')}
          title={t('pulse.tai_title', "Your gym isn't generic. Neither is the platform.")}
          description={t('pulse.tai_desc', "Off-the-shelf SaaS forces you to bend your processes around someone else's idea of how a gym should run. This bends to yours.")}
          testId="pulse-tailored-heading"
        />
        {/* Wide treadmill-row banner — real Pulse install photography */}
        <Reveal className="mb-10">
          <motion.div variants={FADE_UP} className="relative h-44 sm:h-64 rounded-3xl overflow-hidden" data-testid="pulse-tailored-banner">
            <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: 'url(/pulse-photos/carshalton-igym.webp)' }} />
            <div className="absolute inset-0 bg-gradient-to-r from-[rgba(33,39,33,0.85)] via-[rgba(33,39,33,0.35)] to-transparent" />
            <div className="relative h-full flex flex-col justify-end p-7 sm:p-9 on-dark">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--pulse-primary)]">{t('pulse.tai_banner_eyebrow', 'Real installs, real estates')}</div>
              <p className="mt-1.5 text-lg sm:text-2xl font-extrabold max-w-md leading-tight" style={{ color: '#fff', textShadow: '0 2px 20px rgba(0,0,0,0.8)' }}>
                {t('pulse.tai_banner', 'From single studios to national leisure estates.')}
              </p>
            </div>
          </motion.div>
        </Reveal>
        <Reveal className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          {TAILORING_PILLARS(t).map(({ icon: Icon, title, desc }) => (
            <motion.div
              key={title}
              variants={FADE_UP}
              whileHover={{ y: -4 }}
              transition={{ type: 'spring', stiffness: 300, damping: 20 }}
              className="bg-[var(--color-neutral-25)] rounded-3xl p-7 border border-[var(--color-border-light)] hover:border-[rgb(var(--rgb-pulse-primary)/0.4)] hover:shadow-xl transition-all duration-300"
              data-testid={`pulse-tailored-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
            >
              <div className="w-12 h-12 rounded-2xl bg-[rgb(var(--rgb-pulse-primary)/0.1)] flex items-center justify-center mb-5">
                <Icon size={22} className="text-[var(--pulse-primary)]" />
              </div>
              <h3 className="font-extrabold text-[var(--color-surface-dark-panel-alt)] text-xl tracking-tight mb-2" style={{ letterSpacing: '-0.01em' }}>{title}</h3>
              <p className="text-sm text-[var(--color-text-slate)] leading-relaxed">{desc}</p>
            </motion.div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

// ── Final CTA ─────────────────────────────────────────────────
function FinalCTA({ onSignIn }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <section className="relative py-24 overflow-hidden" data-theme="dark" data-testid="pulse-final-cta">
      <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: 'url(/pulse-photos/gym-cardio-angle.webp)' }} />
      <div className="absolute inset-0" style={{ background: 'rgba(33,39,33,0.88)' }} />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[60rem] h-[60rem] bg-[rgb(var(--rgb-pulse-primary)/0.15)] blur-[120px] rounded-full" />
      <div className="relative max-w-4xl mx-auto px-6 text-center">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-3xl sm:text-5xl lg:text-6xl font-bold tracking-[-0.02em] text-white leading-[1.08]"
        >
          {t('pulse.cta_title_1', 'Ready to elevate your')}<br />
          {t('pulse.cta_title_2', 'equipment management?')}
        </motion.h2>
        <p className="mt-6 max-w-xl mx-auto text-white/70">
          {t('pulse.cta_sub', 'Sign in to your portal, or upgrade to Pro to unlock AI triage, audit reports, and document Q&A.')}
        </p>
        <div className="mt-10 flex flex-wrap gap-3 justify-center">
          <Button
            onClick={onSignIn}
            className="h-12 px-7 rounded-xl font-semibold text-sm !bg-white hover:!bg-slate-100 shadow-lg"
            style={{ backgroundColor: '#ffffff' }}
            data-testid="pulse-final-login-btn"
          >
            <span className="inline-flex items-center" style={{ color: '#212721' }}>{t('pulse.cta_login', 'Access Your Portal')} <ArrowRight size={16} className="ml-2" /></span>
          </Button>
          <Button
            variant="outline"
            onClick={() => navigate('/pulse-pricing')}
            className="h-12 px-7 rounded-xl font-semibold text-sm border-white/20 text-white hover:bg-white/10"
            style={{ color: 'var(--color-white)' }}
            data-testid="pulse-final-upgrade-btn"
          >
            <Star size={16} className="mr-2" /> {t('pulse.cta_plans', 'See plans & upgrade')}
          </Button>
        </div>
      </div>
    </section>
  );
}

// ── Footer ────────────────────────────────────────────────────
export function PulseFooter() {
  const PRODUCTS = [
    ['Cardiovascular', 'https://pulsefitness.com/product-category/cardio-vascular/'],
    ['Connectivity', 'https://pulsefitness.com/product-category/connectivity/'],
    ['Strength', 'https://pulsefitness.com/product-category/commercial-strength-equipment-uk/'],
    ['Free Weights', 'https://pulsefitness.com/product-category/free-weights/'],
    ['Functional', 'https://pulsefitness.com/product-category/functional/'],
    ['Studio/Circuit', 'https://pulsefitness.com/product-category/studio-circuit/'],
    ['Home Gym', 'https://pulsefitness.com/product-category/home-gym/'],
    ['Flooring', 'https://pulsefitness.com/product-category/flooring/'],
    ['After Sales', 'https://pulsefitness.com/product-category/after-sales/'],
    ['Retired Products', 'https://pulsefitness.com/retired-products/'],
  ];
  const COMPANY = [
    ['Blog', '/blog'],
    ['Careers', 'https://pulsefitness.com/careers/'],
    ['Case Studies', 'https://pulsefitness.com/case-studies/'],
    ['Contact', 'https://pulsefitness.com/contact/'],
    ['Feed', 'https://pulsefitness.com/pulse-feed/'],
    ['In The Media', 'https://pulsefitness.com/press-release/'],
    ['Pulse Resale', 'https://pulseresale.com/'],
  ];
  const LEGAL = [
    ['Data Protection', 'https://pulsefitness.com/wp-content/uploads/2026/03/Registration-Certificate-Z7612515-Pulse-Fitness.pdf'],
    ['Privacy Policy', 'https://pulsefitness.com/privacy-policy/'],
    ['Environmental', 'https://pulsefitness.com/environmental/'],
    ['ISO Certification', 'https://pulsefitness.com/iso-certification/'],
    ['REACH Regulation', 'https://pulsefitness.com/reach-regulation/'],
    ['WEEE Statement', 'https://pulsefitness.com/weee-statement/'],
    ['Shipping & Returns', 'https://pulsefitness.com/website-shipping-returns/'],
    ['Terms & Conditions', 'https://pulsefitness.com/terms-and-conditions/'],
    ["Klarna T&C's", 'https://pulsefitness.com/klarna-tcs/'],
    ["Clearpay T&C's", 'https://pulsefitness.com/clearpay-tcs/'],
    ['Pre-order/Back-order', 'https://pulsefitness.com/pre-order-and-back-order-terms-and-conditions/'],
    ['Corporate Social Responsibilities', 'https://pulsefitness.com/corporate-social-responsibilities/'],
    ['Modern Slavery and Human Trafficking Policy', 'https://pulsefitness.com/pulse-modern-slavery-and-human-trafficking-policy/'],
  ];
  const linkCls = 'block text-sm text-[#6E7476] hover:text-[#19CDFF] transition-colors leading-relaxed';
  const headCls = 'text-sm font-bold tracking-wide text-[#1B1C1D] mb-3 after:block after:w-7 after:h-0.5 after:bg-[#1B1C1D] after:mt-2';
  const Col = ({ title, items }) => (
    <div>
      <h4 className={headCls}>{title}</h4>
      <ul className="space-y-1.5 mt-4">
        {items.map(([label, href]) => {
          const external = /^https?:\/\//i.test(href);
          return (
            <li key={label}>
              <a
                href={href}
                {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                className={linkCls}
                data-testid={label === 'Blog' ? 'pulse-footer-blog-link' : undefined}
              >
                {label}
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
  return (
    <footer className="bg-[#f7f6f6] border-t border-[#E0E0E0] py-16" data-theme="light" data-testid="pulse-footer">
      <div className="max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-x-8 gap-y-10">
          {/* Brand + address */}
          <div className="col-span-2 md:col-span-1">
            <img src="/brand/pulse-logo-dark.svg" alt="Pulse Fitness" className="h-9 w-auto object-contain mb-6" draggable={false} />
            <address className="not-italic text-sm text-[#6E7476] leading-relaxed">
              Pulse Fitness<br />
              Radnor Park<br />
              Greenfield Road<br />
              Congleton<br />
              Cheshire<br />
              CW12 4TW
            </address>
          </div>
          <Col title="PRODUCTS" items={PRODUCTS} />
          <Col title="COMPANY" items={COMPANY} />
          <Col title="LEGAL" items={LEGAL} />
          {/* Social */}
          <div className="col-span-2 md:col-span-1">
            <div className="flex items-center gap-3">
              <a href="https://www.linkedin.com/company/pulse-fitness/" target="_blank" rel="noopener noreferrer" aria-label="LinkedIn" className="w-10 h-10 rounded-full border border-[#6E7476] flex items-center justify-center text-[#1B1C1D] hover:bg-[#1B1C1D] hover:text-white transition-colors"><Linkedin size={16} /></a>
              <a href="https://www.instagram.com/pulsefitness_official" target="_blank" rel="noopener noreferrer" aria-label="Instagram" className="w-10 h-10 rounded-full border border-[#6E7476] flex items-center justify-center text-[#1B1C1D] hover:bg-[#1B1C1D] hover:text-white transition-colors"><Instagram size={16} /></a>
              <a href="https://www.youtube.com/user/pulsefitnessuk" target="_blank" rel="noopener noreferrer" aria-label="YouTube" className="w-10 h-10 rounded-full border border-[#6E7476] flex items-center justify-center text-[#1B1C1D] hover:bg-[#1B1C1D] hover:text-white transition-colors"><Youtube size={16} /></a>
            </div>
            <p className="mt-8 text-sm text-[#6E7476]">© Pulse Fitness {new Date().getFullYear()}</p>
          </div>
        </div>
      </div>
    </footer>
  );
}

// ── Login Modal ───────────────────────────────────────────────
export function LoginModal({ open, onOpenChange, onLogin, prefillEmail = '', redirectTo = '' }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState(prefillEmail);
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const { banner, show, clear } = useInlineBanner();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    clear();
    setLoading(true);
    try {
      const res = await axios.post(`${API_URL}/auth/login`, { email, password });
      // MFA enforcement: the backend withholds the real token and returns an
      // MFA challenge. This modal has no MFA UI, so hand off to the dedicated
      // /login page (which renders the enrol/verify steps) via in-memory
      // router state — the short-lived temp_token is never persisted.
      if (res.data?.requires_mfa_enrolment || res.data?.requires_mfa) {
        onOpenChange(false);
        navigate('/login', {
          state: {
            mfaChallenge: {
              kind: res.data.requires_mfa_enrolment ? 'enrol' : 'verify',
              temp_token: res.data.temp_token,
              email: res.data.user?.email || email,
            },
          },
        });
        setLoading(false);
        return;
      }
      if (res.data.token) {
        onLogin(res.data);
        // Newly-provisioned admins on a temporary password must rotate it
        // before continuing — this short-circuits any role-based routing.
        if (res.data.user?.must_change_password) {
          onOpenChange(false);
          navigate('/change-password', { replace: true });
          setLoading(false);
          return;
        }
        // A plan CTA can request a post-login destination (e.g. Stripe
        // checkout for the chosen module). Only honour safe INTERNAL paths
        // (single leading slash) to avoid an open-redirect.
        const safeNext = typeof redirectTo === 'string'
          && redirectTo.startsWith('/') && !redirectTo.startsWith('//')
          ? redirectTo : '';
        if (safeNext) {
          onOpenChange(false);
          navigate(safeNext, { replace: true });
          setLoading(false);
          return;
        }
        // Route MOD PRO users (mod_branch, mod_org) to /dashboard where
        // the proper MODProDashboard routing logic lives.
        const accountType = res.data.user?.account_type;
        if (accountType === 'mod_branch' || accountType === 'mod_org') {
          navigate('/dashboard', { replace: true });
        }
        // Pulse Master Admins (provisioned by Pulse Fitness) go straight to the
        // Master Admin console — same UI, data scoped to Pulse.
        if (res.data.user?.is_pulse_admin || res.data.user?.is_master_admin) {
          onOpenChange(false);
          navigate('/master-admin', { replace: true });
          setLoading(false);
          return;
        }
        // MOD site users stay on /pulse (LiteDashboardPage handles them)
      }
    } catch (err) {
      // Fallback — Gym Floor shared-credential login.
      // Lets gym-floor staff use the main Pulse portal instead of a separate URL.
      if (err.response?.status === 401 && !email.includes('@')) {
        try {
          const gf = await axios.post(`${API_URL}/gym-floor/login`, { username: email, password });
          const session = { ...gf.data, logged_in_at: new Date().toISOString() };
          localStorage.setItem('gym_floor_session', JSON.stringify(session));
          onOpenChange(false);
          navigate('/gym-floor', { replace: true });
          setLoading(false);
          return;
        } catch (_gfErr) {
          // fall through to original error
        }
      }
      show({ tone: 'error', title: t('pulse.lm_failed', 'Sign-in failed'), detail: err.response?.data?.detail || t('pulse.lm_failed_detail', 'Please check your email/username and password, then try again.') });
    }
    setLoading(false);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) clear(); onOpenChange(o); }}>
      <DialogContent className="sm:max-w-md p-0 overflow-hidden bg-white border-slate-200 [&>button]:!mt-3 [&>button]:!mr-3" data-testid="pulse-login-dialog">
        <DialogHeader className="p-6 pb-0">
          <DialogTitle className="text-2xl font-bold text-[var(--color-surface-dark-panel-alt)]">{t('pulse.lm_title', 'Welcome back')}</DialogTitle>
          <DialogDescription className="text-[var(--color-text-slate)]">{t('pulse.lm_sub', 'Sign in to your Pulse Fitness portal')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="p-6 space-y-4" data-testid="pulse-login-form">
          {banner && <div>{banner}</div>}
          <div>
            <label className="text-xs font-semibold text-[var(--color-text-slate)] mb-1.5 block">{t('pulse.lm_email', 'Your email or site code')}</label>
            <Input
              type="text"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t('pulse.lm_email_ph', 'you@gym.com or kiosk username')}
              className="h-11 rounded-xl bg-slate-50 border-slate-200 text-[var(--color-surface-dark-panel-alt)] focus:border-[var(--pulse-primary)]"
              required
              data-testid="pulse-login-email"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-[var(--color-text-slate)] mb-1.5 block">{t('pulse.lm_password', 'Password')}</label>
            <div className="relative">
              <Input
                type={showPass ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t('pulse.lm_pass_ph', 'Enter password')}
                className="h-11 rounded-xl bg-slate-50 border-slate-200 text-[var(--color-surface-dark-panel-alt)] pr-10 focus:border-[var(--pulse-primary)]"
                required
                data-testid="pulse-login-password"
              />
              <button type="button" onClick={() => setShowPass(!showPass)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">
                {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <Button
            type="submit"
            disabled={loading}
            // Iter 215dj — Pulse-branded submit; was solid black.
            className="w-full h-11 rounded-xl font-semibold hover:opacity-90 transition-opacity"
            style={{ backgroundColor: 'var(--pulse-primary)', color: 'var(--color-ink, #0f172a)' }}
            data-testid="pulse-login-submit"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : t('pulse.sign_in', 'Sign In')}
          </Button>
          <button
            type="button"
            onClick={() => { onOpenChange(false); navigate('/reset-password'); }}
            className="w-full text-center text-xs font-semibold text-[var(--color-text-slate)] hover:opacity-80 transition-opacity"
            data-testid="pulse-login-forgot"
          >
            {t('pulse.lm_forgot', 'Forgot password?')}
          </button>
          <p className="text-[11px] text-[var(--color-slate-400)] text-center pt-1">
            {t('pulse.lm_note', 'Access level (Lite or Managed) is determined by your account')}
          </p>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// Shared global styles for any Pulse-branded marketing surface (homepage,
// pricing page, etc.). Exported so secondary Pulse pages can mount the
// same scoped CSS without duplication.
export const PULSE_LANDING_CSS = `
        .pulse-landing h1, .pulse-landing h2, .pulse-landing h3, .pulse-landing h4, .pulse-landing h5 {
          font-family: 'Proxima Nova', sans-serif !important;
          letter-spacing: 0.02em;
        }
        .pulse-landing h1 { font-weight: 800; letter-spacing: 0.01em; }
        .pulse-landing h2 { font-weight: 700; letter-spacing: 0.02em; }
        .pulse-landing h3 { font-weight: 600; letter-spacing: 0.03em; }
        .pulse-landing .eyebrow { letter-spacing: 0.18em; font-weight: 700; }
        .pulse-landing p, .pulse-landing span, .pulse-landing div, .pulse-landing a, .pulse-landing button, .pulse-landing input, .pulse-landing label {
          font-family: 'Proxima Nova', sans-serif;
        }
        /* Force white for elements on dark backgrounds (image overlays + dark sections) */
        .pulse-landing .on-dark, .pulse-landing .on-dark h1, .pulse-landing .on-dark h2, .pulse-landing .on-dark h3, .pulse-landing .on-dark p, .pulse-landing .on-dark span {
          color: var(--color-white) !important;
        }
        .pulse-landing [data-theme="dark"] h1, .pulse-landing [data-theme="dark"] h2, .pulse-landing [data-theme="dark"] h3 { color: var(--color-white) !important; }
        .pulse-landing [data-theme="dark"] .text-white { color: var(--color-white) !important; }
        .pulse-landing [data-theme="dark"] .text-white\\/50 { color: rgba(255,255,255,0.6) !important; }
        .pulse-landing [data-theme="dark"] .text-white\\/70 { color: rgba(255,255,255,0.8) !important; }
      `;

// ── Page ──────────────────────────────────────────────────────
export default function PulseLandingPage({ onLogin }) {
  const { theme, toggleTheme } = useAuth();
  const { i18n } = useTranslation();
  // Iter 274 — consistent sign-out: toast + auto-open the login modal with
  // the email pre-filled when arriving from a Pulse sign-out.
  const { prefillEmail, signedOut } = useSignedOutNotice();
  const [loginOpen, setLoginOpen] = useState(signedOut);

  const openLogin = () => setLoginOpen(true);

  // Marketing page theming is independent of the authenticated app theme.
  // Pulse landing is designed for its own light/dark sections via the
  // `data-theme` attribute on its wrapper. Force `<html data-theme="light">`
  // so the Pulse light top sections render correctly even when the user
  // previously toggled CRM/Admin to dark.
  React.useEffect(() => {
    const html = document.documentElement;
    const previous = html.getAttribute('data-theme');
    html.setAttribute('data-theme', 'light');
    return () => {
      if (previous) html.setAttribute('data-theme', previous);
    };
  }, []);

  return (
    <div
      className="min-h-screen bg-white antialiased"
      style={{ fontFamily: "'Proxima Nova', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", color: 'var(--color-surface-dark-panel-alt)' }}
      data-theme="light"
      data-testid="pulse-landing-page"
    >
      <style>{PULSE_LANDING_CSS}</style>
      <div className="pulse-landing">
        <PulseHeader onSignIn={openLogin} theme={theme} toggleTheme={toggleTheme} i18n={i18n} />
        <Hero onSignIn={openLogin} />
        <TrustedBy />
        {/* ── Portal-focused content first ── */}
        <WhatYouCanDo />
        <AIFeatures />
        <HowItWorks />
        <MobileExperience />
        <GymFloorShowcase />
        <CustomerBenefits />
        <TailoredPulse />
        {/* ── Company / heritage detail further down ── */}
        <StatsBento />
        <HeritageTimeline />
        <Sustainability />
        <Support />
        <FinalCTA onSignIn={openLogin} />
        <PulseFooter />
        <LoginModal open={loginOpen} onOpenChange={setLoginOpen} onLogin={onLogin} prefillEmail={prefillEmail} />
      </div>
    </div>
  );
}
