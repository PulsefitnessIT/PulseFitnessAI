/**
 * GymAxis AI — Module "Learn More" detail pages.
 *
 * Matches the dark Swiss high-contrast aesthetic of the homepage. One
 * component, content selected by URL slug. Accessible via /learn/:slug.
 */
import React, { useEffect } from 'react';
import { Link, useParams, useNavigate, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
 ArrowLeft, ArrowRight, Workflow, Wrench, FileText, Brain, BarChart3,
 Link2, CheckCircle2, Zap, ShieldCheck, Sparkles,
 AlertTriangle, Activity, Users, Calendar, Star, DollarSign,
 TrendingUp, Clock, Send, Check, ShieldAlert, ClipboardList,
} from 'lucide-react';
import Footer from '../components/shared/Footer';

const FADE_UP = {
 hidden: { opacity: 0, y: 24 },
 show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};
const stagger = { show: { transition: { staggerChildren: 0.08 } } };

// ─── Content catalogue ─────────────────────────────────────────
const MODULE_CONTENT = {
 crm: {
 icon: Workflow,
 eyebrow: 'CRM',
 title: 'Accounts, pipeline and renewal — one unbroken flow.',
 lede: 'A CRM built around the estate, not a generic list of leads. Every contact, company, quote and contract stays wired to the sites and assets it actually affects.',
 metrics: [
 { value: '13', unit: 'modules', label: 'Complete CRM v2 surface area' },
 { value: '11', unit: 'tabs', label: 'Company record detail' },
 { value: '100%', unit: 'audit', label: 'Every change tracked' },
 ],
 features: [
 { title: 'Role-based dashboard', body: 'Ops, commercial, exec — each role lands on its own signal, not a single cluttered home screen.' },
 { title: 'Companies with 11-tab depth', body: 'AI auto-recognition, contacts, sites, assets, pipeline, quotes, contracts, documents, activity, billing, notes — in one screen.' },
 { title: 'Pipeline Kanban + list view', body: 'Switch between drag-drop board and sortable list. Deal cards surface renewal risk and SLA state.' },
 { title: 'Quotes & CPQ with versioning', body: 'Signatures, approval workflow, version history. Quote-to-contract handover is one click — no CSVs.' },
 { title: 'Contracts with 8-tab detail', body: 'Overview, Sites, Assets, SLA, Service Integration, Billing, Approvals, Timeline — the whole lifecycle.' },
 { title: 'Tender Engine built-in', body: 'AI-drafted bid responses with compliance and win-intelligence baked into the knowledge base.' },
 ],
 },
 service: {
 icon: Wrench,
 eyebrow: 'Service',
 title: 'Fault lifecycle, SLA and engineer dispatch — without the spreadsheets.',
 lede: 'From the moment a belt slips to the moment the engineer signs off, every second is tracked. AI triage, supplier collaboration, two-way messaging, read receipts — all in one operating layer.',
 metrics: [
 { value: '< 5min', unit: 'avg', label: 'Fault-to-triage latency' },
 { value: '41', unit: 'codes', label: 'Standardised fault taxonomy' },
 { value: '2-way', unit: 'chat', label: 'With read receipts' },
 ],
 features: [
 { title: 'AI fault diagnosis', body: 'Reads the full manual library + historic fixes. Suggests intervention before the engineer is even dispatched.' },
 { title: 'Supplier collaboration portal', body: 'Public token-based URL — no login required. Two-way messaging with photo/video, engineer visit scheduling, status progression, CSAT rating.' },
 { title: 'Read receipts on every message', body: 'Gym-side shows "Seen ✓✓" the moment the supplier opens the case. No more chasing follow-ups.' },
 { title: 'PPM engine + compliance', body: 'Weekly to annual schedules. Auto-generated tasks. Compliance % tracking. SLA/warranty-driven frequency.' },
 { title: 'KPI dashboard', body: 'Machine availability, downtime, reactive response, safety-critical response — surfaced, not buried.' },
 { title: 'ERP-ready exports & webhooks', body: 'Fault cases, work orders and resolution notes are export-ready in CSV and pushable via webhook. One data model, end to end — wire it into whatever your finance team already runs.' },
 ],
 },
 contracts: {
 icon: FileText,
 eyebrow: 'Contracts',
 title: 'Lifecycle automation across every site, every renewal.',
 lede: 'Contracts aren\'t PDFs in a shared drive. They\'re live objects wired to the sites they cover, the assets they protect, and the SLAs they promise.',
 metrics: [
 { value: '8', unit: 'tabs', label: 'Per-contract detail surface' },
 { value: '0', unit: 'silos', label: 'Sites, assets, SLA — one record' },
 { value: '5', unit: 'tiers', label: 'Including Gold & Platinum' },
 ],
 features: [
 { title: 'Live site and asset coverage', body: 'Every contract knows which sites and pieces of equipment it covers. Coverage gaps and overlaps surface automatically.' },
 { title: 'SLA-aware everything', body: 'Gold / Platinum tiers drive PPM frequency, response-time KPIs and renewal-risk scoring — with zero manual reconciliation.' },
 { title: 'Renewal timeline', body: 'Approvals, signatures, price changes, add-ons — tracked as a single timeline, not scattered across inboxes.' },
 { title: 'Open contract sync API', body: 'Header + every line item exposed via REST and webhooks. Customer numbers and order references kept in lock-step with whatever ERP you already run.' },
 { title: 'Tender-to-contract handover', body: 'Win the bid in the Tender Engine → one click converts the quote into a live contract with SLA and site list pre-populated.' },
 { title: 'Billing cadence built-in', body: 'Monthly, quarterly, annual. Billing schedule stored on the contract, not in an accountant\'s spreadsheet.' },
 ],
 },
 'ai-tender-engine': {
 icon: Brain,
 eyebrow: 'AI Tender Engine',
 title: 'Draft procurement-grade responses in hours, not weeks.',
 lede: 'Trained on your delivery history, your SLAs and your language. The Tender Engine drafts compliance-aware, value-focused responses that sound like your best bid writer on their best day.',
 metrics: [
 { value: '10x', unit: 'faster', label: 'Drafting speed vs manual' },
 { value: 'GPT-5.2', unit: 'core', label: 'Latest-generation model' },
 { value: '100%', unit: 'compliant', label: 'Knowledge-base grounded' },
 ],
 features: [
 { title: 'Compliance-aware drafting', body: 'Pulls from your compliance library, past wins and rejection notes. Flags sections that need human sign-off before submission.' },
 { title: 'Value-focused responses', body: 'Not generic AI boilerplate — the engine knows your margins, your KPIs and the commercial story you want told.' },
 { title: 'Win intelligence', body: 'Every tender outcome — win or loss — feeds back into the model. The next response is better than the last.' },
 { title: 'Knowledge-base grounded', body: 'Retrieval-augmented generation over your real procurement history. No hallucinations. No invented credentials.' },
 { title: 'One-click to CRM', body: 'Winning draft converts straight to a live Quote, then Contract, without leaving the platform.' },
 { title: 'CSAT feedback loop', body: 'Thumbs up/down on every AI response. The model learns what your team considers a strong draft.' },
 ],
 },
 'kpi-engine': {
 icon: BarChart3,
 eyebrow: 'KPI Engine',
 title: 'Downtime, compliance, commercial lift — measured, not estimated.',
 lede: 'Seven auto-calculated KPIs, colour-coded ratings, drill-down to the site or asset responsible. Tender-ready exports in CSV or PDF.',
 metrics: [
 { value: '7', unit: 'KPIs', label: 'Auto-calculated, period-filtered' },
 { value: '4', unit: 'grades', label: 'Emerald · Blue · Amber · Red' },
 { value: '∞', unit: 'drilldown', label: 'From fleet to one bolt' },
 ],
 features: [
 { title: 'PPM Compliance', body: 'Planned-preventive coverage across the estate. Rolling periods. Worst-performing sites surfaced instantly.' },
 { title: 'Equipment Downtime', body: 'Hours out-of-service per machine, per site. Direct feed from the fault lifecycle — no manual data entry.' },
 { title: 'Reactive Response Time', body: 'Time from fault logged to engineer on-site. Benchmarked against your SLA tier.' },
 { title: 'Safety-critical response', body: 'A separate bucket for anything flagged safety-critical. Different thresholds. Different escalation.' },
 { title: 'Machine OOS Ratio', body: 'Running vs out-of-service across the fleet. The single number a COO will actually read.' },
 { title: 'Tender-pack CSV export', body: 'One click exports all KPIs for the past period, ready to drop into a bid response or board pack.' },
 ],
 },
 integrations: {
 icon: Link2,
 eyebrow: 'Integrations',
 title: 'Open APIs, webhooks and a pluggable event bus.',
 lede: 'The platform doesn\'t force a rip-and-replace. It exposes every operation over a documented REST API, fires webhooks on every meaningful event, and keeps an audit trail across every integration you wire up.',
 metrics: [
 { value: '10', unit: 'event types', label: 'Integration Hub event bus' },
 { value: 'REST', unit: 'API', label: 'Documented endpoints, per-org keys' },
 { value: 'Live', unit: 'webhooks', label: 'Retry queue with exponential backoff' },
 ],
 features: [
 { title: 'Documented REST API', body: 'Every resource — companies, contracts, faults, assets, members — has typed endpoints. Per-org API keys. Rate-limited, audit-logged, fail-closed.' },
 { title: 'Webhook fan-out', body: 'Subscribe to ten canonical event types. Every webhook is signed, retried with exponential backoff, and observable from the Integration Hub.' },
 { title: 'Integration Hub event bus', body: 'Ten canonical event types. Every integration reads from one bus — add a new system without re-plumbing the rest.' },
 { title: 'Resend (transactional email)', body: 'Fault cards, supplier welcomes, engineer callouts, branded per-customer (Pulse Fitness vs GymAxis AI). Verified sending domain.' },
 { title: 'Stripe', body: 'Trial-to-paid conversion with metadata. Checkout session metadata flips the org to paid on webhook.' },
 { title: 'ERP-ready exports', body: 'Contract headers, line items, PO references and engineer notes export to CSV in a finance-friendly schema. Drop straight into your accounting suite.' },
 ],
 },
 memberships: {
 icon: Users,
 eyebrow: 'Memberships',
 title: 'Plans, classes and revenue — one operator console.',
 lede: 'Run direct-debit memberships, group-class timetables and member self-service from one screen. Stripe Checkout for new members, attendance + no-show tracking, and a dedicated instructor portal for the people on the floor.',
 metrics: [
 { value: '7', unit: 'sub-tabs', label: 'Members · Timetable · Plans · Ads · Analytics' },
 { value: '1-tap', unit: 'check-in', label: 'Member self-service portal' },
 { value: 'Live', unit: 'KPIs', label: 'MRR, churn, occupancy — in real time' },
 ],
 features: [
 { title: 'Stripe-native plans', body: 'Monthly / annual billing, trial periods, Stripe Checkout. Webhooks flip member status without manual reconciliation.' },
 { title: 'Class timetable + waitlists', body: 'Drag-and-drop weekly schedule. Booking caps, waitlists, instructor assignments, capacity heatmap.' },
 { title: 'Instructor portal', body: 'Standalone tablet-friendly view at /instructor — class roster, check-ins, no-show flags, daily summary email.' },
 { title: 'Referral campaigns', body: 'Member-driven growth with shareable codes, revenue attribution and a banner on the member portal.' },
 { title: 'Analytics that operators actually use', body: 'MRR, churn-30d, occupancy, attendance heatmaps, no-show ratio. AI-summarised weekly digest.' },
 { title: 'Win-back automation', body: 'Auto-detect lapsed members. Generate Stripe Checkout links + branded emails — recover revenue without manual chase.' },
 ],
 },
 'gym-floor': {
 icon: ClipboardList,
 eyebrow: 'Gym Floor',
 title: 'AI-moderated handover diary for shift teams.',
 lede: 'A site-generic shared login for floor staff plus a structured handover diary that travels across shifts. AI moderation flags hostile language; managers see what happened, who saw it, and what got fixed.',
 metrics: [
 { value: '1', unit: 'shared login', label: 'No personal accounts to manage' },
 { value: 'AI', unit: 'moderation', label: 'GPT-4o-mini auto-flags issues' },
 { value: '7', unit: 'topics', label: 'Handover · Cleaning · Equipment · Customer · Stock · Safety · General' },
 ],
 features: [
 { title: 'Shared site credential', body: 'Manager sets one username + password per site. Staff log in from any tablet at the desk — no per-person onboarding.' },
 { title: 'Topic taxonomy', body: 'Seven categories cover the real shift issues: handover notes, cleaning, equipment, customer interaction, stock, safety, general.' },
 { title: 'AI moderation', body: 'Posts pass through GPT-4o-mini moderation. Hostile or offensive content is flagged with severity high — manager sees it instantly.' },
 { title: 'Manager view in Pulse Pro', body: 'Owners and managers see the diary inside the Operations dashboard. Topic filter, severity badges, delete on demand.' },
 { title: 'Available wherever you operate', body: 'Pulse Pro sites get it in their dashboard. MOD PRO branches get it across every site they manage.' },
 ],
 },
};

// Deep-link aliases so old marketing copy still works
const ALIASES = {
 ai: 'ai-tender-engine',
 tender: 'ai-tender-engine',
 kpi: 'kpi-engine',
 // New (consolidated) module slugs from the homepage bento — map to existing
 // long-form pages where appropriate so the lander stays simple but the
 // detail pages keep their depth.
 'service-desk': 'service',
 'crm-&-contracts': 'crm',
 'crm-contracts': 'crm',
 'ai-intelligence': 'ai-tender-engine',
};


function Hero({ icon: Icon, eyebrow, title, lede }) {
 return (
 <section className="relative overflow-hidden border-b border-white/10">
 {/* Background glows — subtle, don't wash out text */}
 <div className="pointer-events-none absolute inset-0">
 <div className="absolute -top-40 -left-40 w-[44rem] h-[44rem] rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.1)] blur-[140px]" />
 <div className="absolute -bottom-40 right-0 w-[32rem] h-[32rem] rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.05)] blur-[120px]" />
 <div
 className="absolute inset-0 opacity-[0.035]"
 style={{
 backgroundImage: 'linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)',
 backgroundSize: '80px 80px',
 }}
 />
 </div>

 <div className="relative max-w-6xl mx-auto px-6 pt-20 sm:pt-28 pb-20">
 <Link
 to="/"
 className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/60 hover:text-white transition-colors mb-10"
 data-testid="learn-more-back-home"
 >
 <ArrowLeft size={14} /> Back to home
 </Link>

 <motion.div initial="hidden" animate="show" variants={stagger} className="max-w-4xl">
 <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-white/60 mb-6">
 <span className="h-px w-6 bg-white/30" />
 {eyebrow}
 </motion.div>

 <motion.div variants={FADE_UP} className="w-14 h-14 rounded-2xl bg-[rgb(var(--rgb-brand-cyan)/0.1)] border border-[rgb(var(--rgb-brand-cyan)/0.3)] flex items-center justify-center mb-8 shadow-[0_0_40px_rgba(25,205,255,0.15)]">
 <Icon size={26} className="text-[var(--color-brand-cyan)]" />
 </motion.div>

 <motion.h1
 variants={FADE_UP}
 className="text-white font-extrabold leading-[1.04]"
 style={{ fontSize: 'clamp(2rem, 5vw, 4.25rem)', letterSpacing: '-0.025em', fontFamily: "'Proxima Nova', sans-serif" }}
 >
 {title}
 </motion.h1>

 <motion.p variants={FADE_UP} className="mt-6 text-lg sm:text-xl text-white/80 leading-relaxed max-w-3xl">
 {lede}
 </motion.p>
 </motion.div>
 </div>
 </section>
 );
}


function MetricsStrip({ metrics }) {
 return (
 <section className="relative border-b border-white/10 bg-black">
 <div className="max-w-6xl mx-auto px-6 py-14 grid grid-cols-1 sm:grid-cols-3 gap-8">
 {metrics.map((m) => (
 <div key={m.label} className="border-l-2 border-[rgb(var(--rgb-brand-cyan)/0.6)] pl-5" data-testid={`learn-metric-${m.label.toLowerCase().replace(/\s+/g, '-')}`}>
 <div className="flex items-baseline gap-2">
 <div className="text-white font-extrabold tracking-tight" style={{ fontSize: 'clamp(2rem, 4vw, 3.25rem)', letterSpacing: '-0.02em' }}>
 {m.value}
 </div>
 <div className="text-[var(--color-brand-cyan)] text-xs font-bold uppercase tracking-[0.2em]">{m.unit}</div>
 </div>
 <div className="mt-2 text-sm text-white/70">{m.label}</div>
 </div>
 ))}
 </div>
 </section>
 );
}


// ─── Per-module visual preview compositions ────────────────────
// Each returns a "UI-in-a-card" mockup built from the real product's
// visual language — not a screenshot. Renders crisp at any viewport.

function PreviewFrame({ children, chrome = 'Preview', testId }) {
 return (
 <div
 className="relative rounded-2xl border border-white/10 bg-gradient-to-br from-[var(--color-ink-coal)] to-[var(--color-surface-darker)] shadow-[0_30px_120px_rgba(0,0,0,0.5)] overflow-hidden"
 data-testid={testId}
 >
 {/* window chrome */}
 <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 bg-black/40">
 <div className="flex gap-1.5">
 <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
 <span className="w-2.5 h-2.5 rounded-full bg-[#FEBC2E]" />
 <span className="w-2.5 h-2.5 rounded-full bg-[#28C840]" />
 </div>
 <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/40 ml-2">
 {chrome}
 </div>
 </div>
 <div className="p-5 sm:p-7">{children}</div>
 </div>
 );
}

function CRMPreview() {
 const stages = [
 { name: 'Qualified', color: 'var(--color-brand-cyan)', deals: [
 { company: 'Pulse Fitness HQ', value: '£84k', risk: 'Warm', riskTone: 'amber' },
 { company: 'Leisure United', value: '£42k', risk: 'New', riskTone: 'blue' },
 ] },
 { name: 'Proposal', color: 'var(--color-violet-400)', deals: [
 { company: 'Nuffield Health', value: '£146k', risk: 'Hot', riskTone: 'emerald' },
 ] },
 { name: 'Renewal Risk', color: 'var(--color-warning)', deals: [
 { company: 'Anytime Fitness — North', value: '£28k', risk: '14d to renew', riskTone: 'red' },
 ] },
 ];
 const tone = (t) => ({
 emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
 amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
 blue: 'bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] border-[rgb(var(--rgb-brand-cyan)/0.3)]',
 red: 'bg-red-500/15 text-red-300 border-red-500/30',
 }[t]);
 return (
 <PreviewFrame chrome="CRM · Pipeline" testId="preview-crm">
 <div className="flex items-center justify-between mb-4">
 <div className="text-white font-bold text-sm">Q1 Pipeline · £300k</div>
 <div className="flex items-center gap-1 text-[10px] text-white/50 uppercase tracking-wider">
 <Activity size={11} className="text-[var(--color-brand-cyan)]" /> live
 </div>
 </div>
 <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
 {stages.map((s) => (
 <div key={s.name} className="rounded-xl bg-black/30 border border-white/5 p-3">
 <div className="flex items-center gap-2 mb-3">
 <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
 <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-white/70">{s.name}</span>
 <span className="ml-auto text-[10px] text-white/40">{s.deals.length}</span>
 </div>
 <div className="space-y-2">
 {s.deals.map((d) => (
 <div key={d.company} className="rounded-lg bg-white/[0.04] border border-white/10 p-2.5 hover:border-[rgb(var(--rgb-brand-cyan)/0.3)] transition-colors">
 <div className="text-white text-[12px] font-semibold truncate">{d.company}</div>
 <div className="flex items-center justify-between mt-1.5">
 <span className="text-[11px] text-white/50 flex items-center gap-1"><DollarSign size={10} />{d.value}</span>
 <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${tone(d.riskTone)}`}>{d.risk}</span>
 </div>
 </div>
 ))}
 </div>
 </div>
 ))}
 </div>
 </PreviewFrame>
 );
}

function ServicePreview() {
 return (
 <PreviewFrame chrome="Service · Fault Card" testId="preview-service">
 <div className="flex items-start gap-3">
 <div className="w-10 h-10 rounded-lg bg-red-500/15 border border-red-500/30 flex items-center justify-center shrink-0">
 <AlertTriangle size={18} className="text-red-400" />
 </div>
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2 flex-wrap">
 <span className="text-white font-bold text-sm">Belt slipping · Treadmill #TM-18</span>
 <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-500/15 text-red-300 border border-red-500/30 uppercase tracking-wider">High</span>
 <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] border border-[rgb(var(--rgb-brand-cyan)/0.3)]">BEL-01</span>
 </div>
 <div className="text-[11px] text-white/50 mt-1">Tottenham Green · Serial TG-TR-044 · Logged 06:12</div>
 </div>
 </div>

 {/* AI triage ribbon */}
 <div className="mt-4 rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.05)] border border-[rgb(var(--rgb-brand-cyan)/0.2)] p-3">
 <div className="flex items-center gap-2 mb-1">
 <Sparkles size={12} className="text-[var(--color-brand-cyan)]" />
 <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-brand-cyan)]">AI Triage · 4.2s</span>
 </div>
 <div className="text-[12px] text-white/80 leading-relaxed">
 Drive-belt tension low. Likely needs adjustment, not replacement. Engineer not required — gym staff can resolve with torque wrench.
 </div>
 </div>

 {/* Chat bubbles */}
 <div className="mt-4 space-y-2">
 <div className="flex justify-start">
 <div className="max-w-[80%] rounded-2xl rounded-bl-sm px-3 py-2 text-[12px]" style={{ background: 'var(--color-success-alt)', color: '#fff' }}>
 <div className="text-[9px] uppercase tracking-wider text-white/70 mb-0.5">Lee · Site</div>
 Hi — any ETA? Belt's getting worse through peak hour.
 <div className="flex justify-end mt-1"><span className="text-[9px] text-[var(--color-blue-100)]">Seen ✓✓</span></div>
 </div>
 </div>
 <div className="flex justify-end">
 <div className="max-w-[80%] rounded-2xl rounded-br-sm px-3 py-2 text-[12px]" style={{ background: 'var(--color-info-ios)', color: '#fff' }}>
 <div className="text-[9px] uppercase tracking-wider text-white/70 mb-0.5">Technogym</div>
 Engineer dispatched. ETA 09:15.
 </div>
 </div>
 </div>
 </PreviewFrame>
 );
}

function ContractsPreview() {
 return (
 <PreviewFrame chrome="Contracts · Coverage" testId="preview-contracts">
 <div className="flex items-center justify-between">
 <div>
 <div className="text-white font-bold text-sm">Pulse Fitness — Master SLA 2026</div>
 <div className="text-[11px] text-white/50">Ref #CT-2061 · Effective 01 Jan 2026</div>
 </div>
 <span className="text-[10px] font-bold uppercase px-2 py-1 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 tracking-wider">Platinum</span>
 </div>

 {/* Stats strip */}
 <div className="mt-4 grid grid-cols-3 gap-2">
 {[
 { label: 'Sites', value: '42' },
 { label: 'Assets', value: '1,284' },
 { label: 'Renewal', value: '89d' },
 ].map((s) => (
 <div key={s.label} className="rounded-lg bg-white/[0.03] border border-white/5 p-2.5 text-center">
 <div className="text-white font-extrabold text-lg tracking-tight">{s.value}</div>
 <div className="text-[9px] uppercase tracking-wider text-white/50 mt-0.5">{s.label}</div>
 </div>
 ))}
 </div>

 {/* Timeline */}
 <div className="mt-4">
 <div className="text-[10px] uppercase tracking-wider text-white/50 mb-2">Timeline</div>
 <div className="space-y-1.5">
 {[
 { icon: Check, color: 'emerald', text: 'Signed by CFO · 14 Dec', done: true },
 { icon: Check, color: 'emerald', text: 'Site coverage synced · 42 sites mapped', done: true },
 { icon: Calendar, color: 'blue', text: 'PPM schedules generated · 1,284 assets', done: true },
 { icon: ShieldAlert, color: 'amber', text: 'Renewal notice due · 01 Nov', done: false },
 ].map((t, i) => {
 const Icon = t.icon;
 const toneMap = {
 emerald: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
 blue: 'bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] border-[rgb(var(--rgb-brand-cyan)/0.3)]',
 amber: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
 };
 return (
 <div key={i} className="flex items-center gap-2 text-[11px]">
 <span className={`w-5 h-5 rounded-full flex items-center justify-center border ${toneMap[t.color]}`}>
 <Icon size={10} />
 </span>
 <span className={t.done ? 'text-white/80' : 'text-white/50'}>{t.text}</span>
 </div>
 );
 })}
 </div>
 </div>
 </PreviewFrame>
 );
}

function AITenderPreview() {
 const checks = [
 { text: 'Section 4 · Insurance — matches our active policy', ok: true },
 { text: 'Section 7 · KPI commitments — pulled from live KPI Engine', ok: true },
 { text: 'Section 9 · Price schedule — needs commercial sign-off', ok: false },
 ];
 return (
 <PreviewFrame chrome="AI Tender Engine · Drafting" testId="preview-ai-tender-engine">
 <div className="flex items-center gap-2 mb-3">
 <Sparkles size={14} className="text-[var(--color-brand-cyan)]" />
 <span className="text-white font-bold text-sm">Everyone Active — RFQ 2026/Q2</span>
 <span className="ml-auto text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] border border-[rgb(var(--rgb-brand-cyan)/0.3)]">Draft · v3</span>
 </div>

 {/* Document preview with skeleton lines */}
 <div className="rounded-lg bg-black/40 border border-white/10 p-4 space-y-1.5">
 <div className="h-2 w-1/2 rounded bg-white/20" />
 <div className="h-2 w-full rounded bg-white/10" />
 <div className="h-2 w-11/12 rounded bg-white/10" />
 <div className="h-2 w-3/4 rounded bg-white/10" />
 <div className="h-2 w-full rounded bg-white/10" />
 <div className="h-2 w-4/5 rounded bg-white/10" />
 </div>

 {/* Compliance checks */}
 <div className="mt-4 space-y-1.5">
 <div className="text-[10px] uppercase tracking-wider text-white/50 mb-1">Compliance checks</div>
 {checks.map((c) => (
 <div key={c.text} className="flex items-center gap-2 text-[11px]">
 <span className={`w-4 h-4 rounded-full flex items-center justify-center ${c.ok ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
 {c.ok ? <Check size={10} /> : <AlertTriangle size={10} />}
 </span>
 <span className={c.ok ? 'text-white/80' : 'text-amber-200/90'}>{c.text}</span>
 </div>
 ))}
 </div>

 <div className="mt-4 flex items-center gap-2">
 <button className="flex items-center gap-1.5 bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] text-[11px] font-bold px-3 py-1.5 rounded-full">
 <Send size={11} /> Submit draft
 </button>
 <span className="text-[10px] text-white/50">· Generated in 4.2s from 186 historic wins</span>
 </div>
 </PreviewFrame>
 );
}

function KPIPreview() {
 const kpis = [
 { label: 'Machine Availability', value: '97.4', unit: '%', tone: 'emerald', border: 'border-l-emerald-500' },
 { label: 'PPM Compliance', value: '92', unit: '%', tone: 'blue', border: 'border-l-[var(--color-brand-cyan)]' },
 { label: 'Reactive Response', value: '3.8', unit: 'h avg', tone: 'amber', border: 'border-l-amber-500' },
 { label: 'Safety-Critical', value: '< 1', unit: 'h', tone: 'emerald', border: 'border-l-emerald-500' },
 ];
 const toneText = {
 emerald: 'text-emerald-400', blue: 'text-[var(--color-brand-cyan)]', amber: 'text-amber-400',
 };
 return (
 <PreviewFrame chrome="KPI Engine · March 2026" testId="preview-kpi-engine">
 <div className="grid grid-cols-2 gap-3">
 {kpis.map((k) => (
 <div key={k.label} className={`rounded-xl bg-black/30 border border-white/10 ${k.border} border-l-[3px] p-4`}>
 <div className="flex items-baseline gap-1.5">
 <div className="text-white font-extrabold tracking-tight" style={{ fontSize: '1.75rem', letterSpacing: '-0.02em' }}>{k.value}</div>
 <div className={`text-[10px] font-bold uppercase tracking-wider ${toneText[k.tone]}`}>{k.unit}</div>
 </div>
 <div className="text-[11px] text-white/60 mt-1">{k.label}</div>
 </div>
 ))}
 </div>

 {/* Worst-performer mini-bars */}
 <div className="mt-4 rounded-xl bg-black/30 border border-white/10 p-4">
 <div className="flex items-center justify-between mb-3">
 <span className="text-[10px] uppercase tracking-wider text-white/50">Worst performing assets</span>
 <span className="text-[9px] text-white/40">by downtime</span>
 </div>
 {[
 { name: 'TM-18 · Treadmill', hours: 42, bar: 'w-[85%]' },
 { name: 'ST-04 · Cable Stack', hours: 28, bar: 'w-[55%]' },
 { name: 'RB-11 · Rowing', hours: 17, bar: 'w-[35%]' },
 ].map((r) => (
 <div key={r.name} className="mb-2 last:mb-0">
 <div className="flex items-center justify-between text-[11px] mb-1">
 <span className="text-white/80">{r.name}</span>
 <span className="text-white/50">{r.hours}h</span>
 </div>
 <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
 <div className={`h-full rounded-full bg-gradient-to-r from-red-500 to-red-400 ${r.bar}`} />
 </div>
 </div>
 ))}
 </div>
 </PreviewFrame>
 );
}

function IntegrationsPreview() {
 const sources = [
 { label: 'Pulse CRM', icon: Workflow },
 { label: 'Operations Portal', icon: Wrench },
 { label: 'Contracts', icon: FileText },
 ];
 const targets = [
 { label: 'ERP webhook', active: true },
 { label: 'Open REST API', active: true },
 { label: 'Resend Email', active: true },
 { label: 'Stripe', active: true },
 ];
 return (
 <PreviewFrame chrome="Integration Hub · Event Bus" testId="preview-integrations">
 <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-stretch">
 {/* Left: sources */}
 <div className="space-y-2">
 <div className="text-[10px] uppercase tracking-wider text-white/50 mb-2">Sources</div>
 {sources.map((s) => {
 const Icon = s.icon;
 return (
 <div key={s.label} className="flex items-center gap-2 rounded-lg bg-white/[0.04] border border-white/10 px-3 py-2">
 <Icon size={14} className="text-[var(--color-brand-cyan)]" />
 <span className="text-[12px] text-white/80 font-semibold">{s.label}</span>
 </div>
 );
 })}
 </div>

 {/* Middle: event bus */}
 <div className="flex items-center justify-center">
 <div className="relative w-full">
 <div className="rounded-xl bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.2)] to-[rgb(var(--rgb-brand-cyan)/0.05)] border border-[rgb(var(--rgb-brand-cyan)/0.4)] p-4 text-center shadow-[0_0_40px_rgba(25,205,255,0.15)]">
 <Link2 size={18} className="text-[var(--color-brand-cyan)] mx-auto mb-1" />
 <div className="text-white font-extrabold text-sm tracking-tight">Event Bus</div>
 <div className="text-[10px] text-[var(--color-brand-cyan)] font-bold uppercase tracking-wider mt-0.5">10 event types</div>
 <div className="mt-3 space-y-1 text-[10px] text-white/60 text-left">
 <div>· fault.created</div>
 <div>· contract.signed</div>
 <div>· supplier.responded</div>
 <div className="text-white/30">· +7 more</div>
 </div>
 </div>
 </div>
 </div>

 {/* Right: targets */}
 <div className="space-y-2">
 <div className="text-[10px] uppercase tracking-wider text-white/50 mb-2">Destinations</div>
 {targets.map((t) => (
 <div key={t.label} className="flex items-center justify-between rounded-lg bg-white/[0.04] border border-white/10 px-3 py-2">
 <span className="text-[12px] text-white/80 font-semibold">{t.label}</span>
 <span className={`w-1.5 h-1.5 rounded-full ${t.active ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]' : 'bg-white/20'}`} />
 </div>
 ))}
 </div>
 </div>
 </PreviewFrame>
 );
}

const PREVIEW_MAP = {
 crm: CRMPreview,
 service: ServicePreview,
 contracts: ContractsPreview,
 'ai-tender-engine': AITenderPreview,
 'kpi-engine': KPIPreview,
 integrations: IntegrationsPreview,
};

function ModulePreview({ slug }) {
 const Preview = PREVIEW_MAP[slug];
 if (!Preview) return null;
 return (
 <section className="relative border-b border-white/10 py-20 overflow-hidden">
 {/* Soft brand glow behind the preview */}
 <div className="pointer-events-none absolute inset-0">
 <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[48rem] h-[24rem] rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.1)] blur-[140px]" />
 </div>
 <div className="relative max-w-5xl mx-auto px-6">
 <div className="text-center mb-8">
 <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/60">
 <span className="h-px w-6 bg-white/30" />
 A look inside
 <span className="h-px w-6 bg-white/30" />
 </div>
 </div>
 <motion.div
 initial={{ opacity: 0, y: 30 }}
 whileInView={{ opacity: 1, y: 0 }}
 viewport={{ once: true, amount: 0.2 }}
 transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
 >
 <Preview />
 </motion.div>
 </div>
 </section>
 );
}


function FeatureGrid({ features }) {
 return (
 <section className="relative border-b border-white/10 py-24">
 <div className="max-w-6xl mx-auto px-6">
 <motion.div
 initial="hidden"
 whileInView="show"
 viewport={{ once: true, amount: 0.15 }}
 variants={stagger}
 className="grid grid-cols-1 md:grid-cols-2 gap-5"
 >
 {features.map((f) => (
 <motion.div
 key={f.title}
 variants={FADE_UP}
 className="group relative rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.04] to-transparent p-7 transition-all duration-300 hover:border-[rgb(var(--rgb-brand-cyan)/0.4)] hover:shadow-[0_0_40px_rgba(25,205,255,0.12)] overflow-hidden"
 data-testid={`learn-feature-${f.title.toLowerCase().replace(/\s+/g, '-')}`}
 >
 <div className="absolute top-0 right-0 w-32 h-32 bg-[rgb(var(--rgb-brand-cyan)/0.05)] blur-3xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
 <div className="relative">
 <div className="flex items-center gap-3 mb-3">
 <CheckCircle2 size={18} className="text-[var(--color-brand-cyan)] shrink-0" />
 <h3 className="text-white font-extrabold text-lg tracking-tight" style={{ letterSpacing: '-0.01em' }}>
 {f.title}
 </h3>
 </div>
 <p className="text-sm text-white/75 leading-relaxed">{f.body}</p>
 </div>
 </motion.div>
 ))}
 </motion.div>
 </div>
 </section>
 );
}


function CTASection({ current, all }) {
 return (
 <section className="relative py-24 overflow-hidden">
 <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[var(--color-brand-cyan)]/[0.04] to-transparent pointer-events-none" />
 <div className="relative max-w-6xl mx-auto px-6">
 <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-[var(--color-ink-midnight)] to-[var(--color-surface-darker)] p-10 sm:p-14 text-center">
 <Sparkles size={28} className="text-[var(--color-brand-cyan)] mx-auto mb-5" />
 <h2 className="text-white font-extrabold text-3xl sm:text-5xl leading-tight tracking-tight" style={{ letterSpacing: '-0.02em' }}>
 One platform. Every module. No bolt-ons.
 </h2>
 <p className="mt-4 text-white/70 max-w-2xl mx-auto text-base sm:text-lg">
 Every GymAxis module shares one data model, one audit trail, one security posture. Want to see the full picture?
 </p>
 <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
 <Link
 to="/"
 className="inline-flex items-center justify-center gap-2 bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] font-bold text-sm px-6 py-3 rounded-full hover:bg-white transition-colors"
 data-testid="learn-cta-back-home"
 >
 Back to home <ArrowRight size={14} />
 </Link>
 <Link
 to="/contact"
 className="inline-flex items-center justify-center gap-2 bg-white/5 text-white border border-white/20 font-bold text-sm px-6 py-3 rounded-full hover:bg-white/10 transition-colors"
 data-testid="learn-cta-contact"
 >
 Book a demo
 </Link>
 </div>
 </div>

 {/* Related modules */}
 <div className="mt-16">
 <div className="text-xs uppercase tracking-[0.2em] text-white/50 mb-5">Explore more modules</div>
 <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
 {Object.entries(all).filter(([slug]) => slug !== current).map(([slug, mod]) => {
 const Icon = mod.icon;
 return (
 <Link
 key={slug}
 to={`/learn/${slug}`}
 className="group flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 hover:border-[rgb(var(--rgb-brand-cyan)/0.4)] hover:bg-white/[0.06] transition-all"
 data-testid={`learn-related-${slug}`}
 >
 <div className="w-9 h-9 rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.1)] border border-[rgb(var(--rgb-brand-cyan)/0.2)] flex items-center justify-center shrink-0">
 <Icon size={16} className="text-[var(--color-brand-cyan)]" />
 </div>
 <div className="min-w-0 flex-1">
 <div className="text-white text-sm font-bold truncate">{mod.eyebrow}</div>
 </div>
 <ArrowRight size={14} className="text-white/40 group-hover:text-[var(--color-brand-cyan)] group-hover:translate-x-0.5 transition-all shrink-0" />
 </Link>
 );
 })}
 </div>
 </div>
 </div>
 </section>
 );
}


export default function LearnMorePage() {
 const { slug } = useParams();
 const navigate = useNavigate();

 // Theme-lock: every public marketing page must render on the dark
 // aesthetic regardless of the user's stored theme preference.
 useEffect(() => {
 const html = document.documentElement;
 const prev = html.getAttribute('data-theme');
 html.setAttribute('data-theme', 'dark');
 return () => {
 if (prev) html.setAttribute('data-theme', prev);
 };
 }, []);

 const resolvedSlug = ALIASES[slug] || slug;
 const mod = MODULE_CONTENT[resolvedSlug];

 // Scroll to top on slug change — must run before any early return to keep
 // hook call order stable across renders.
 useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [resolvedSlug]);

 if (!mod) {
 return <Navigate to="/" replace />;
 }

 return (
 <div className="min-h-screen bg-[var(--color-surface-darker)] text-white" data-testid={`learn-more-page-${resolvedSlug}`}>
 {/* Top bar — matches the landing page minimal header */}
 <nav className="sticky top-0 z-40 bg-[var(--color-surface-darker)]/80 backdrop-blur-lg border-b border-white/10">
 <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
 <Link to="/" className="text-white font-extrabold text-lg tracking-tight" data-testid="learn-logo-home">
 GymAxis<span className="text-[var(--color-brand-cyan)]">.AI</span>
 </Link>
 <div className="flex items-center gap-2">
 <button
 onClick={() => navigate(-1)}
 className="text-white/70 hover:text-white text-sm font-semibold hidden sm:inline-flex items-center gap-1.5"
 data-testid="learn-nav-back"
 >
 <ArrowLeft size={14} /> Back
 </button>
 <Link
 to="/login"
 className="bg-white text-[var(--color-surface-darker)] font-bold text-sm px-4 py-2 rounded-full hover:bg-[var(--color-brand-cyan)] transition-colors"
 data-testid="learn-nav-signin"
 >
 Sign In
 </Link>
 </div>
 </div>
 </nav>

 <Hero icon={mod.icon} eyebrow={mod.eyebrow} title={mod.title} lede={mod.lede} />
 <MetricsStrip metrics={mod.metrics} />
 <ModulePreview slug={resolvedSlug} />
 <FeatureGrid features={mod.features} />
 <CTASection current={resolvedSlug} all={MODULE_CONTENT} />
 <Footer />
 </div>
 );
}
