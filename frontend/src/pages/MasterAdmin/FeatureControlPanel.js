import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
 Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { X, Copy, History, Sparkles, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

// High-contrast switch styling for the Master Admin pages — works on both
// the light Master Admin background and any dark surface. Without this,
// the default Switch component fades into the white card.
const ADMIN_SWITCH = 'data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-zinc-300 border border-zinc-300 shadow-inner';

const FEATURE_LIST = [
 // ── Operations Portal ──────────────────────────────────────
 { key: 'ai_audits', label: 'AI Audits', group: 'portal' },
 { key: 'qr_scanning', label: 'QR Scanning', group: 'portal' },
 { key: 'multi_site', label: 'Multi-Site', group: 'portal' },
 { key: 'ppm_engine', label: 'PPM Scheduling', group: 'portal' },
 { key: 'gym_floor', label: 'Gym Floor Layout', group: 'portal' },
 { key: 'check_sheets', label: 'Daily Check Sheets', group: 'portal' },

 // ── Memberships (NEW) ──────────────────────────────────────
 { key: 'mem_smart_waitlist', label: 'Smart Waitlist', group: 'memberships' },
 { key: 'mem_qr_kiosk', label: 'QR Kiosk Check-in', group: 'memberships' },
 { key: 'mem_ai_insights', label: 'AI Demand & Pricing', group: 'memberships' },
 { key: 'mem_crm_loop', label: 'CRM Auto-Trigger Loop', group: 'memberships' },
 { key: 'mem_member_portal', label: 'Member Portal', group: 'memberships' },
 { key: 'mem_classes', label: 'Group Fitness Timetable', group: 'memberships' },
 { key: 'mem_payments', label: 'Stripe Memberships', group: 'memberships' },

 // ── Marketing Suite (NEW) ──────────────────────────────────
 { key: 'mkt_ai_director', label: 'AI Creative Director', group: 'marketing' },
 { key: 'mkt_brand_kit', label: 'Brand Kit', group: 'marketing' },
 { key: 'mkt_quick_poster', label: 'Quick Poster Studio', group: 'marketing' },
 { key: 'mkt_campaigns', label: 'Email Campaigns', group: 'marketing' },
 { key: 'mkt_journeys', label: 'Journey Canvas', group: 'marketing' },
 { key: 'mkt_churn_rescue', label: 'Churn Rescue', group: 'marketing' },
 { key: 'mkt_social', label: 'Social Posting', group: 'marketing' },
 { key: 'mkt_sms', label: 'SMS (Twilio)', group: 'marketing' },

 // ── AI / Assistant ─────────────────────────────────────────
 { key: 'orb_assistant', label: 'Unified Orb Assistant', group: 'ai' },
 { key: 'ai_action_undo', label: 'AI Action Undo Log', group: 'ai' },
 { key: 'ai_bulk_import', label: 'Bulk CSV Import', group: 'ai' },

 // ── General ────────────────────────────────────────────────
 { key: 'api_access', label: 'API Access', group: 'general' },
 { key: 'white_label', label: 'White Label', group: 'general' },
 { key: 'mfa_required', label: 'Force MFA on Sign-in', group: 'general' },

 // ── CRM Modules ────────────────────────────────────────────
 { key: 'crm_pipeline', label: 'Pipeline', group: 'crm' },
 { key: 'crm_quotes', label: 'Quotes / CPQ', group: 'crm' },
 { key: 'crm_tenders', label: 'Tender Engine', group: 'crm' },
 { key: 'crm_ai_tools', label: 'AI Tools', group: 'crm' },
 { key: 'crm_workflows', label: 'Workflows', group: 'crm' },
 { key: 'crm_documents', label: 'Documents', group: 'crm' },
 { key: 'crm_calendar', label: 'Calendar', group: 'crm' },
 { key: 'crm_companies', label: 'Companies & Contracts', group: 'crm' },

 // ── Enterprise ─────────────────────────────────────────────
 { key: 'kpi_engine', label: 'KPI / Performance Engine', group: 'enterprise' },
 { key: 'sicon_integration', label: 'Sicon Integration', group: 'enterprise' },
 { key: 'sage_integration', label: 'Sage 200 Integration', group: 'enterprise' },
 { key: 'stripe_connect', label: 'Stripe Connect (live)', group: 'enterprise' },
];

const GROUP_META = {
 enterprise: { label: 'GymAxis Enterprise (Premium Add-ons)', order: 0 },
 portal: { label: 'Operations Portal', order: 1 },
 memberships: { label: 'Memberships', order: 2 },
 marketing: { label: 'Marketing Suite', order: 3 },
 ai: { label: 'AI & Assistant', order: 4 },
 general: { label: 'General', order: 5 },
 crm: { label: 'CRM Modules', order: 6 },
};

const ACCOUNT_TYPE_LABELS = { full: 'GymAxis', pulse_pro: 'Pulse Pro', lite: 'Pulse Lite' };

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const FeatureControlPanel = ({ org, allOrgs, onClose, onUpdateFeatures }) => {
 const isGymaxis = (org.account_type || 'full') === 'full';
 const [presets, setPresets] = useState([]);
 const [presetKey, setPresetKey] = useState(org.features_preset || '');
 const [copyFromId, setCopyFromId] = useState('');
 const [applying, setApplying] = useState(false);
 const [audit, setAudit] = useState([]);
 const [showAudit, setShowAudit] = useState(false);
 const [loadingAudit, setLoadingAudit] = useState(false);

 useEffect(() => {
 axios.get(`${API}/master-admin/feature-presets`, { headers: authHeaders() })
 .then(r => setPresets(r.data.presets || []))
 .catch(() => { /* silent */ });
 }, []);

 const loadAudit = async () => {
 setLoadingAudit(true);
 try {
 const r = await axios.get(
 `${API}/master-admin/organizations/${org.id}/features/audit`,
 { headers: authHeaders() }
 );
 setAudit(r.data.audit || []);
 setShowAudit(true);
 } catch {
 notify.error('Failed to load audit log', { duration: 6000 });
 } finally {
 setLoadingAudit(false);
 }
 };

 const applyPreset = async () => {
 if (!presetKey) return;
 setApplying(true);
 try {
 const r = await axios.post(
 `${API}/master-admin/organizations/${org.id}/features/apply-preset`,
 { preset: presetKey },
 { headers: authHeaders() }
 );
 notify.success(`Preset applied — ${r.data.changed} feature(s) updated`, { duration: 6000 });
 if (onUpdateFeatures) onUpdateFeatures(org.id, r.data.features, { silent: true });
 } catch (e) {
 notifyApiError(notify, e, 'Failed to apply preset');
 } finally {
 setApplying(false);
 }
 };

 const copyFrom = async () => {
 if (!copyFromId || copyFromId === org.id) return;
 setApplying(true);
 try {
 const r = await axios.post(
 `${API}/master-admin/organizations/${org.id}/features/copy-from/${copyFromId}`,
 {},
 { headers: authHeaders() }
 );
 notify.success(`Features copied from ${r.data.copied_from}`, { duration: 6000 });
 if (onUpdateFeatures) onUpdateFeatures(org.id, r.data.features, { silent: true });
 } catch (e) {
 notifyApiError(notify, e, 'Failed to copy features');
 } finally {
 setApplying(false);
 }
 };

 const groupedFeatures = [...FEATURE_LIST].sort((a, b) => GROUP_META[a.group].order - GROUP_META[b.group].order);
 const groups = [...new Set(groupedFeatures.map(f => f.group))];

 const otherOrgs = (allOrgs || []).filter(o => o.id !== org.id);

 // Latest audit entry preview
 const latestAudit = audit[0];

 return (
 <div className="border-t border-zinc-100 bg-zinc-50 p-4" data-testid={`org-features-panel-${org.id}`}>
 <div className="flex items-center justify-between mb-3">
 <div>
 <p className="text-sm font-semibold text-zinc-800">Feature Control — {org.name}</p>
 <p className="text-[11px] text-zinc-500 mt-0.5">
 Account: <span className="font-semibold text-zinc-700">{ACCOUNT_TYPE_LABELS[org.account_type || 'full']}</span>
 {' · '}Toggle features on/off, apply a preset, or copy from another org.
 </p>
 </div>
 <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600"><X size={16} /></button>
 </div>

 {/* Module Matrix — orgs choose Operations/Memberships/Marketing + tier */}
 <div className="mb-4 p-3 bg-white border border-zinc-200 rounded-lg" data-testid="module-matrix">
 <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-400 mb-2">
 Module access · {org.name}
 </p>
 <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
 {[
 { key: 'operations', label: 'Operations Portal', tip: 'Equipment, faults, PPM, suppliers' },
 { key: 'memberships', label: 'Memberships', tip: 'Members, plans, classes, bookings' },
 { key: 'marketing', label: 'Marketing Suite', tip: 'Campaigns, segments, automation' },
 { key: 'crm', label: 'CRM', tip: 'Pipeline, quotes, tenders, leads' },
 ].map((m) => {
 const cfg = ((org.modules || {})[m.key]) || { enabled: m.key === 'operations', tier: 'pro' };
 return (
 <div key={m.key} className="p-2.5 bg-zinc-50 rounded-md border border-zinc-100 space-y-1.5"
 data-testid={`module-${m.key}`}>
 <div className="flex items-center justify-between">
 <div>
 <p className="text-xs font-bold text-zinc-700">{m.label}</p>
 <p className="text-[10px] text-zinc-400">{m.tip}</p>
 </div>
 <Switch checked={!!cfg.enabled}
 onCheckedChange={(val) => onUpdateFeatures && onUpdateFeatures(org.id, {
 modules: { ...(org.modules || {}), [m.key]: { ...cfg, enabled: val } },
 })}
 className={ADMIN_SWITCH}
 data-testid={`module-${m.key}-toggle-${org.id}`} />
 </div>
 <Select
 value={cfg.tier || 'pro'}
 onValueChange={(tier) => onUpdateFeatures && onUpdateFeatures(org.id, {
 modules: { ...(org.modules || {}), [m.key]: { ...cfg, tier } },
 })}
 disabled={!cfg.enabled}>
 <SelectTrigger className="h-7 text-[11px] bg-white border-zinc-300" data-testid={`module-${m.key}-tier-${org.id}`}>
 <SelectValue />
 </SelectTrigger>
 <SelectContent className="bg-white">
 <SelectItem value="lite">Lite</SelectItem>
 <SelectItem value="pro">Pro</SelectItem>
 <SelectItem value="enterprise">Enterprise</SelectItem>
 </SelectContent>
 </Select>
 </div>
 );
 })}
 </div>
 <p className="text-[10px] text-zinc-400 mt-1.5">
 Disabled modules disappear from the org\'s sidebar and route guards return 404.
 </p>
 </div>

 {/* Presets + copy-from toolbar */}
 <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 p-3 bg-white border border-zinc-200 rounded-lg" data-testid="feature-toolbar">
 <div className="flex items-center gap-2">
 <Sparkles size={14} className="text-[var(--color-brand-blue)]" />
 <Select value={presetKey} onValueChange={setPresetKey}>
 <SelectTrigger className="h-8 text-xs bg-white border-zinc-300" data-testid="preset-select">
 <SelectValue placeholder="Apply preset…" />
 </SelectTrigger>
 <SelectContent className="bg-white">
 {presets.map(p => (
 <SelectItem key={p.key} value={p.key} data-testid={`preset-opt-${p.key}`}>
 <div>
 <div className="font-medium">{p.label}</div>
 <div className="text-[10px] text-zinc-500">{p.description}</div>
 </div>
 </SelectItem>
 ))}
 </SelectContent>
 </Select>
 <Button size="sm" onClick={applyPreset} disabled={!presetKey || applying}
 className="h-8 text-xs" data-testid="preset-apply">
 {applying ? <Loader2 size={12} className="animate-spin" /> : 'Apply'}
 </Button>
 </div>

 <div className="flex items-center gap-2">
 <Copy size={14} className="text-zinc-500" />
 <Select value={copyFromId} onValueChange={setCopyFromId}>
 <SelectTrigger className="h-8 text-xs bg-white border-zinc-300" data-testid="copy-from-select">
 <SelectValue placeholder="Copy features from…" />
 </SelectTrigger>
 <SelectContent className="bg-white max-h-64">
 {otherOrgs.map(o => (
 <SelectItem key={o.id} value={o.id} data-testid={`copy-from-opt-${o.id}`}>
 {o.name} <span className="text-zinc-400 text-[10px] ml-1">{ACCOUNT_TYPE_LABELS[o.account_type || 'full']}</span>
 </SelectItem>
 ))}
 </SelectContent>
 </Select>
 <Button size="sm" variant="outline" onClick={copyFrom} disabled={!copyFromId || applying}
 className="h-8 text-xs border-zinc-300" data-testid="copy-from-apply">
 {applying ? <Loader2 size={12} className="animate-spin" /> : 'Copy'}
 </Button>
 </div>

 <div className="flex items-center justify-end gap-2">
 <Button size="sm" variant="ghost" onClick={loadAudit} disabled={loadingAudit}
 className="h-8 text-xs text-zinc-600 hover:text-zinc-900" data-testid="audit-toggle">
 {loadingAudit ? <Loader2 size={12} className="animate-spin mr-1" /> : <History size={12} className="mr-1" />}
 {showAudit ? 'Hide' : 'Show'} audit log
 </Button>
 </div>
 </div>

 {/* Audit log */}
 {showAudit && (
 <div className="mb-4 bg-white border border-zinc-200 rounded-lg p-3" data-testid="audit-log">
 <p className="text-[11px] uppercase tracking-wider font-bold text-zinc-400 mb-2">Recent feature changes</p>
 {audit.length === 0 ? (
 <p className="text-xs text-zinc-400">No changes recorded yet.</p>
 ) : (
 <div className="space-y-2 max-h-48 overflow-y-auto">
 {audit.slice(0, 20).map((entry, idx) => (
 <div key={idx} className="flex items-start gap-2 text-xs text-zinc-700 border-l-2 border-[rgb(var(--rgb-brand-blue)/0.4)] pl-2">
 <div className="flex-1">
 <div className="flex items-center gap-2">
 <span className="font-medium">{entry.by}</span>
 {entry.preset && <Badge className="bg-blue-50 text-blue-700 text-[10px] h-4">{entry.preset}</Badge>}
 <span className="text-zinc-400 text-[10px]">
 {new Date(entry.at).toLocaleString()}
 </span>
 </div>
 <div className="text-[11px] text-zinc-500 mt-0.5">
 {Object.entries(entry.changes || {}).map(([k, v]) => {
 const fmt = (val) => {
 if (val == null) return '—';
 if (typeof val === 'object') {
 // Module entries are { enabled, tier } — render as"on/off · tier"
 if ('enabled' in val) {
 return `${val.enabled ? 'on' : 'off'}${val.tier ? ` · ${val.tier}` : ''}`;
 }
 return JSON.stringify(val);
 }
 return String(val);
 };
 const positive = (v && typeof v.to === 'object' && v.to !== null)
 ? !!v.to.enabled
 : !!v.to;
 return (
 <span key={k} className="mr-2">
 {k}: <span className={positive ? 'text-emerald-600' : 'text-red-500'}>
 {fmt(v.from)} → {fmt(v.to)}
 </span>
 </span>
 );
 })}
 </div>
 </div>
 </div>
 ))}
 </div>
 )}
 </div>
 )}

 {!showAudit && latestAudit && (
 <p className="text-[11px] text-zinc-400 mb-2">
 Last change: <span className="font-medium text-zinc-600">{latestAudit.by}</span>
 {' · '}{new Date(latestAudit.at).toLocaleDateString()}
 {latestAudit.preset && <> · preset <span className="font-medium">{latestAudit.preset}</span></>}
 </p>
 )}

 {/* Feature toggles */}
 {groups.map(group => {
 const groupFeats = groupedFeatures.filter(f => f.group === group);
 const isEnterprise = group === 'enterprise';
 return (
 <div key={group} className="mb-3">
 <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-400 mb-1.5">
 {GROUP_META[group].label}
 {isEnterprise && !isGymaxis && (
 <span className="ml-2 normal-case tracking-normal text-amber-600">
 · off by default for {ACCOUNT_TYPE_LABELS[org.account_type || 'full']} — toggle on to grant access
 </span>
 )}
 </p>
 <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
 {groupFeats.map(feat => {
 const stored = (org.features || {})[feat.key];
 const defaultOn = isEnterprise ? isGymaxis : true;
 const enabled = stored === undefined ? defaultOn : stored !== false;
 return (
 <div key={feat.key} className="flex items-center justify-between p-2 bg-white rounded-md border border-zinc-200">
 <span className="text-xs text-zinc-700">{feat.label}</span>
 <Switch checked={enabled} onCheckedChange={(val) => {
 if (onUpdateFeatures) onUpdateFeatures(org.id, { ...(org.features || {}), [feat.key]: val });
 }} className={ADMIN_SWITCH} data-testid={`feature-${feat.key}-${org.id}`} />
 </div>
 );
 })}
 </div>
 </div>
 );
 })}
 </div>
 );
};

export default FeatureControlPanel;
