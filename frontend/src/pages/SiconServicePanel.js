/* SiconServicePanel.js — compact, collapsible surface for all mapped Sicon fields. */
import { useState, useMemo } from 'react';
import {
 ClipboardList, ChevronDown, ChevronUp, User, Calendar, MapPin, Hash, CheckCircle2,
 Wrench, FileText, Shield, Users, Briefcase, Flag,
} from 'lucide-react';
import { Badge } from '../components/ui/badge';

const fmtDate = (d) => {
 if (!d) return '—';
 try {
 return new Date(d).toLocaleString('en-GB', {
 day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
 });
 } catch {
 return String(d);
 }
};
const fmtDateOnly = (d) => {
 if (!d) return '—';
 try {
 return new Date(d).toLocaleDateString('en-GB',
 { day: '2-digit', month: 'short', year: 'numeric' });
 } catch {
 return String(d);
 }
};

const PRIORITY_TONE = {
 'Safety Critical': 'bg-red-500/20 text-red-500 border-red-500/30',
 'Critical': 'bg-red-500/15 text-red-500 border-red-500/25',
 'High': 'bg-orange-500/15 text-orange-500 border-orange-500/25',
 'Medium': 'bg-amber-500/15 text-amber-500 border-amber-500/25',
 'Low': 'bg-emerald-500/15 text-emerald-500 border-emerald-500/25',
};

function Row({ icon: Icon, label, value, mono = false, testid }) {
 if (value === undefined || value === null || value === '') return null;
 return (
 <div className="flex items-start gap-2 text-xs" data-testid={testid}>
 {Icon && <Icon size={12} className="text-[var(--color-text-muted)] mt-0.5 shrink-0" />}
 <span className="text-[var(--color-text-muted)] min-w-[110px] shrink-0">{label}</span>
 <span className={`text-white font-medium break-words ${mono ? 'font-mono' : ''}`}>{value}</span>
 </div>
 );
}

function Section({ title, count, children, defaultOpen = false, testid }) {
 const [open, setOpen] = useState(defaultOpen);
 const Icon = open ? ChevronUp : ChevronDown;
 return (
 <div className="border-t border-white/10" data-testid={testid}>
 <button
 type="button"
 onClick={() => setOpen(v => !v)}
 className="w-full flex items-center justify-between py-2 text-left hover:bg-white/5 transition-colors px-1 rounded"
 data-testid={`${testid}-toggle`}
 >
 <span className="text-xs font-semibold tracking-wide text-[var(--color-text-muted)] uppercase">
 {title}{typeof count === 'number' && count > 0 && <span className="ml-2 text-white/80 normal-case lowercase">({count})</span>}
 </span>
 <Icon size={14} className="text-[var(--color-text-muted)]" />
 </button>
 {open && <div className="pb-3 pt-1 space-y-2">{children}</div>}
 </div>
 );
}

function EquipmentLineageSection({ issue, equipment }) {
 const warrantyText = useMemo(() => {
 const expiry = equipment?.warranty_expiry || equipment?.warranty_end_date;
 if (!expiry) return null;
 const days = Math.round((new Date(expiry) - new Date()) / 86400000);
 const remaining = days > 0
 ? ` (${days} days left)`
 : days < 0 ? ' (expired)' : ' (expires today)';
 return `${fmtDateOnly(expiry)}${remaining}`;
 }, [equipment]);

 return (
 <>
 <Row icon={Wrench} label="Equipment"
 value={[issue.machine_type, equipment?.make, equipment?.model_code].filter(Boolean).join(' · ')} />
 <Row label="Serial" mono value={issue.serial_number} />
 <Row icon={Calendar} label="Installed" value={fmtDateOnly(equipment?.install_date)} />
 <Row icon={Shield} label="Warranty" value={warrantyText} />
 <Row icon={Hash} label="Fault code" mono value={issue.fault_code} />
 <Row label="PPM schedule" value={issue.ppm_schedule_id} />
 <Row label="Source" value={(issue.source || '').replace('_', ' ')} />
 </>
 );
}

function VisitsSection({ appointments, engineerMap }) {
 if (!appointments?.length) {
 return <p className="text-xs text-[var(--color-text-muted)] italic px-1">No visits booked yet.</p>;
 }
 return (
 <div className="space-y-3">
 {appointments.map((a, i) => {
 const engineers = (a.employee_ids || [])
 .map(eid => engineerMap[eid]?.full_name || `#${eid}`).join(', ');
 const hasGps = a.arrival_latitude != null && a.arrival_longitude != null;
 const gpsLink = hasGps ? `https://maps.google.com/?q=${a.arrival_latitude},${a.arrival_longitude}` : null;
 return (
 <div key={i} className="p-2.5 bg-[var(--color-ink-alt)] border border-white/5 rounded-md text-xs space-y-1.5"
 data-testid={`sicon-visit-${i}`}>
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-2 flex-wrap">
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)] border-[rgb(var(--rgb-brand-blue)/0.3)] text-[10px]">
 {a.appointment_type || 'Work'}
 </Badge>
 <span className="text-white font-medium">{fmtDate(a.scheduled_start)}</span>
 {a.appointment_complete && (
 <span className="inline-flex items-center gap-1 text-emerald-400 text-[10px]">
 <CheckCircle2 size={11} /> Complete
 </span>
 )}
 </div>
 {engineers && <span className="text-[var(--color-text-muted)]">{engineers}</span>}
 </div>
 {a.work_done_description && (
 <p className="text-white/90"><span className="text-[var(--color-text-muted)]">Work done:</span> {a.work_done_description}</p>
 )}
 {a.further_action && (
 <p className="text-amber-400"><span className="text-[var(--color-text-muted)]">Follow-up:</span> {a.further_action}</p>
 )}
 <div className="flex items-center gap-3 flex-wrap text-[10px] text-[var(--color-text-muted)]">
 {a.arrival_signee && <span>Arrival signed: <span className="text-white">{a.arrival_signee}</span></span>}
 {a.departure_signee && <span>Departure signed: <span className="text-white">{a.departure_signee}</span></span>}
 {gpsLink && (
 <a href={gpsLink} target="_blank" rel="noopener noreferrer"
 className="inline-flex items-center gap-1 text-[var(--color-brand-blue)] hover:underline">
 <MapPin size={10} /> GPS proof
 </a>
 )}
 </div>
 </div>
 );
 })}
 </div>
 );
}

function TrackingNotesSection({ timeline }) {
 const notes = (timeline || []).filter(t => t.type === 'sicon_note');
 if (!notes.length) {
 return <p className="text-xs text-[var(--color-text-muted)] italic px-1">No engineer notes yet.</p>;
 }
 const stripProvider = (s) => (s || '').replace(/^sicon\s*[·\-–|]\s*/i, '').replace(/^sicon\s+/i, '') || 'Service team';
 return (
 <div className="space-y-2">
 {notes.slice(-8).reverse().map((n, i) => (
 <div key={i} className="p-2 bg-[var(--color-ink-alt)] border border-white/5 rounded-md text-xs"
 data-testid={`sicon-note-${i}`}>
 <div className="flex items-center justify-between mb-1">
 <span className="text-[var(--color-text-muted)]">{stripProvider(n.by)}</span>
 <span className="text-[var(--color-text-muted)] text-[10px]">{fmtDate(n.timestamp)}</span>
 </div>
 <p className="text-white/90 whitespace-pre-wrap">{n.message}</p>
 </div>
 ))}
 </div>
 );
}

function CaseFactsSection({ issue }) {
 return (
 <>
 <Row icon={Hash} label="Case ref" mono value={issue.sicon_case_number || `#${issue.sicon_case_id}`} />
 <Row icon={Flag} label="Status" value={issue.sicon_status} />
 <Row label="Sub-status" value={issue.sicon_sub_status_id ? `#${issue.sicon_sub_status_id}` : null} />
 <Row icon={Briefcase} label="Case type" value={issue.sicon_case_type_name} />
 <Row icon={Users} label="Internal team" value={issue.sicon_internal_team} />
 <Row icon={Users} label="External team" value={issue.sicon_external_team} />
 <Row icon={FileText} label="Contract"
 value={issue.sicon_contract_number
 ? `${issue.sicon_contract_number}${issue.sicon_contract_line_number ? ` · Line ${issue.sicon_contract_line_number}` : ''}`
 : null} />
 <Row label="Job ref" value={issue.sicon_job_id ? `#${issue.sicon_job_id}` : null} />
 <Row icon={MapPin} label="Sub-location"
 value={issue.sicon_sub_location_description
 ? `${issue.sicon_sub_location_description}${issue.sicon_sub_location_comment ? ` · ${issue.sicon_sub_location_comment}` : ''}`
 : null} />
 <Row label="Customer ref" mono value={issue.sicon_customer_reference} />
 <Row label="Call logged" value={fmtDate(issue.sicon_call_date)} />
 </>
 );
}

export default function SiconServicePanel({ issue, equipment, engineers = [] }) {
 const [open, setOpen] = useState(false);
 const engineerMap = useMemo(() => {
 const map = {};
 (engineers || []).forEach(e => {
 if (e.sicon_employee_id) map[e.sicon_employee_id] = e;
 });
 return map;
 }, [engineers]);

 if (!issue?.sicon_case_id) return null;

 const appointments = issue.sicon_appointments || [];
 const nextAppt = appointments.find(a => !a.appointment_complete) || appointments[appointments.length - 1];
 const engineerName = issue.sicon_assigned_to
 || (nextAppt?.employee_ids || []).map(eid => engineerMap[eid]?.full_name).filter(Boolean).join(', ')
 || '—';
 const scheduled = nextAppt?.scheduled_start ? fmtDate(nextAppt.scheduled_start) : '—';
 const priorityTone = PRIORITY_TONE[issue.sicon_priority] || 'bg-zinc-500/15 text-zinc-400 border-zinc-500/25';
 const notesCount = (issue.timeline || []).filter(t => t.type === 'sicon_note').length;

 return (
 <div className="p-4 bg-[var(--theme-surface)] border border-white/10 rounded-lg space-y-2"
 data-testid={`sicon-service-panel-${issue.id}`}>
 {/* Top line: label · case ref · priority */}
 <div className="flex items-center justify-between flex-wrap gap-2">
 <div className="flex items-center gap-2 min-w-0">
 <ClipboardList size={14} className="text-[var(--color-brand-blue)] shrink-0" />
 <h4 className="text-white font-medium text-sm">Job Card</h4>
 <span className="font-mono text-xs text-[var(--color-text-muted)]">
 {issue.sicon_case_number || `#${issue.sicon_case_id}`}
 </span>
 </div>
 <div className="flex items-center gap-2">
 {issue.sicon_priority && (
 <Badge variant="outline" className={`text-[10px] ${priorityTone}`}>
 {issue.sicon_priority}
 </Badge>
 )}
 {issue.sicon_status && (
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)] text-[10px] border border-[rgb(var(--rgb-brand-blue)/0.3)]">
 {issue.sicon_status}
 </Badge>
 )}
 </div>
 </div>

 {/* Key-info strip: Engineer assigned · Scheduled date */}
 <div className="grid grid-cols-2 gap-3 text-xs">
 <div className="flex items-start gap-2 min-w-0">
 <User size={12} className="text-[var(--color-text-muted)] mt-0.5 shrink-0" />
 <div className="min-w-0">
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wide">Engineer</p>
 <p className="text-white font-medium truncate" data-testid="sicon-engineer-name">{engineerName}</p>
 </div>
 </div>
 <div className="flex items-start gap-2 min-w-0">
 <Calendar size={12} className="text-[var(--color-text-muted)] mt-0.5 shrink-0" />
 <div className="min-w-0">
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wide">Scheduled</p>
 <p className="text-white font-medium truncate" data-testid="sicon-scheduled-date">{scheduled}</p>
 </div>
 </div>
 </div>

 {/* Single expand trigger */}
 <button
 type="button"
 onClick={() => setOpen(v => !v)}
 className="w-full flex items-center justify-center gap-1 pt-1 text-[11px] text-[var(--color-brand-blue)] hover:underline"
 data-testid="sicon-expand-toggle"
 >
 {open ? 'Hide' : 'Show'} full job details
 {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
 </button>

 {open && (
 <div className="pt-1 space-y-1">
 <Section title="Case facts" testid="sicon-section-case" defaultOpen>
 <CaseFactsSection issue={issue} />
 </Section>
 <Section title="Equipment lineage" testid="sicon-section-equipment">
 <EquipmentLineageSection issue={issue} equipment={equipment} />
 </Section>
 <Section title="Visits" count={appointments.length} testid="sicon-section-visits">
 <VisitsSection appointments={appointments} engineerMap={engineerMap} />
 </Section>
 <Section title="Engineer notes" count={notesCount} testid="sicon-section-notes">
 <TrackingNotesSection timeline={issue.timeline} />
 </Section>
 </div>
 )}

 {issue.sicon_synced_at && !open && (
 <p className="text-[10px] text-[var(--color-text-muted)] pt-1 border-t border-white/5">
 Auto-synced {fmtDate(issue.sicon_synced_at)}
 </p>
 )}
 </div>
 );
}
