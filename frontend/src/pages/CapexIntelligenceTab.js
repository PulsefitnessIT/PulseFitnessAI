import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import {
 PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import {
 TrendingUp, AlertTriangle, Shield, Wrench, PoundSterling, Download,
 Brain, Loader2, ChevronDown, ChevronUp, Calendar, FileText,
 CheckCircle, Clock, XCircle, CircleAlert
} from 'lucide-react';

const STATUS_CONFIG = {
 healthy: { color: 'var(--color-success-alt-2)', bg: 'bg-green-500/15', text: 'text-green-400', label: 'Healthy', icon: CheckCircle },
 monitor: { color: 'var(--color-yellow)', bg: 'bg-yellow-500/15', text: 'text-yellow-400', label: 'Monitor', icon: Clock },
 at_risk: { color: 'var(--color-orange)', bg: 'bg-orange-500/15', text: 'text-orange-400', label: 'At Risk', icon: AlertTriangle },
 replace_soon: { color: 'var(--color-danger)', bg: 'bg-red-500/15', text: 'text-red-400', label: 'Replace Soon', icon: CircleAlert },
 replace_now: { color: 'var(--color-neutral-950-alt)', bg: 'bg-zinc-900', text: 'text-white', label: 'Replace Now', icon: XCircle, dotColor: 'var(--color-text-faint)' },
};

const PIE_COLORS = ['var(--color-success-alt-2)', 'var(--color-yellow)', 'var(--color-orange)', 'var(--color-danger)', 'var(--color-text-faint)'];

const fmt = (n) => n != null ? `£${Number(n).toLocaleString()}` : '—';

/* ─── CAPEX Summary Cards ─── */
const SummaryCards = ({ summary, forecast }) => {
 const flagged = (summary.at_risk || 0) + (summary.replace_soon || 0) + (summary.replace_now || 0);
 return (
 <div className="grid grid-cols-2 lg:grid-cols-5 gap-4" data-testid="capex-summary-cards">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5">
 <p className="text-[var(--color-text-muted)] text-xs mb-1">Total Audited</p>
 <p className="text-3xl font-bold text-white" data-testid="capex-total">{summary.total}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5">
 <p className="text-green-400 text-xs mb-1">Healthy</p>
 <p className="text-3xl font-bold text-green-400" data-testid="capex-healthy">{summary.healthy}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5">
 <p className="text-orange-400 text-xs mb-1">At Risk</p>
 <p className="text-3xl font-bold text-orange-400" data-testid="capex-at-risk">{summary.at_risk}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5">
 <p className="text-red-400 text-xs mb-1">Replacement Required</p>
 <p className="text-3xl font-bold text-red-400" data-testid="capex-replace">{(summary.replace_soon || 0) + (summary.replace_now || 0)}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-[rgb(var(--rgb-brand-blue)/0.3)] p-5 col-span-2 lg:col-span-1">
 <p className="text-[var(--color-text-muted)] text-xs mb-1">Est. Replacement (12m)</p>
 <p className="text-2xl font-bold text-white" data-testid="capex-total-cost">{fmt(forecast.next_12_months)}</p>
 </Card>
 </div>
 );
};

/* ─── Priority Replacements Table ─── */
const PriorityTable = ({ items }) => {
 if (!items.length) return null;
 return (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="capex-priority-table">
 <h3 className="text-lg font-semibold text-white mb-4">Priority Replacement Items</h3>
 <div className="overflow-x-auto">
 <table className="w-full text-sm">
 <thead>
 <tr className="border-b border-white/10 text-[var(--color-text-muted)]">
 <th className="text-left py-2 pr-4">Machine</th>
 <th className="text-left py-2 pr-4 hidden sm:table-cell">Type</th>
 <th className="text-left py-2 pr-4 hidden md:table-cell">Location</th>
 <th className="text-center py-2 pr-4">Status</th>
 <th className="text-right py-2 pr-4">Score</th>
 <th className="text-right py-2">Est. Cost</th>
 </tr>
 </thead>
 <tbody>
 {items.map((item, i) => {
 const cfg = STATUS_CONFIG[item.status.toLowerCase().replace(/ /g, '_')] || STATUS_CONFIG.at_risk;
 return (
 <tr key={i} className="border-b border-white/5">
 <td className="py-3 pr-4 text-white font-medium">{item.name}</td>
 <td className="py-3 pr-4 text-[var(--color-text-muted)] hidden sm:table-cell">{item.type}</td>
 <td className="py-3 pr-4 text-[var(--color-text-muted)] hidden md:table-cell">{item.location}</td>
 <td className="py-3 pr-4 text-center">
 <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}>
 <span className="w-2 h-2 rounded-full" style={{ background: cfg.dotColor || cfg.color }} />
 {item.status}
 </span>
 </td>
 <td className="py-3 pr-4 text-right text-white font-mono">{item.score}</td>
 <td className="py-3 text-right text-white font-semibold">{fmt(item.cost)}</td>
 </tr>
 );
 })}
 </tbody>
 </table>
 </div>
 </Card>
 );
};

/* ─── Charts ─── */
const CapexCharts = ({ summary, byType }) => {
 const pieData = [
 { name: 'Healthy', value: summary.healthy || 0 },
 { name: 'Monitor', value: summary.monitor || 0 },
 { name: 'At Risk', value: summary.at_risk || 0 },
 { name: 'Replace Soon', value: summary.replace_soon || 0 },
 { name: 'Replace Now', value: summary.replace_now || 0 },
 ].filter(d => d.value > 0);

 const barData = Object.entries(byType || {}).map(([k, v]) => ({ name: k.length > 14 ? k.slice(0, 12) + '..' : k, cost: v }));

 return (
 <div className="grid md:grid-cols-2 gap-6">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="capex-pie-chart">
 <h3 className="text-lg font-semibold text-white mb-4">Asset Health Distribution</h3>
 {pieData.length > 0 ? (
 <ResponsiveContainer width="100%" height={260}>
 <PieChart>
 <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={95} paddingAngle={3} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
 {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
 </Pie>
 <Tooltip contentStyle={{ background: 'var(--color-surface-dark-2)', border: '1px solid #333', borderRadius: 8, color: '#fff' }} />
 </PieChart>
 </ResponsiveContainer>
 ) : <p className="text-[var(--color-text-muted)] text-center py-12">No data</p>}
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="capex-bar-chart">
 <h3 className="text-lg font-semibold text-white mb-4">Replacement Cost by Category</h3>
 {barData.length > 0 ? (
 <ResponsiveContainer width="100%" height={260}>
 <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 10 }}>
 <XAxis type="number" tickFormatter={v => `£${(v / 1000).toFixed(0)}k`} stroke="#666" />
 <YAxis type="category" dataKey="name" width={100} stroke="#999" tick={{ fontSize: 12 }} />
 <Tooltip formatter={v => fmt(v)} contentStyle={{ background: 'var(--color-surface-dark-2)', border: '1px solid #333', borderRadius: 8, color: '#fff' }} />
 <Bar dataKey="cost" fill="var(--color-brand-blue)" radius={[0, 4, 4, 0]} />
 </BarChart>
 </ResponsiveContainer>
 ) : <p className="text-[var(--color-text-muted)] text-center py-12">No replacement costs to display</p>}
 </Card>
 </div>
 );
};

/* ─── Forecast ─── */
const ForecastSection = ({ forecast, byPriority }) => (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="capex-forecast">
 <h3 className="text-lg font-semibold text-white mb-4">CAPEX Forecast</h3>
 <div className="grid grid-cols-3 gap-4 mb-6">
 {[
 { label: 'Next 3 Months', value: forecast.next_3_months, color: 'text-red-400' },
 { label: 'Next 6 Months', value: forecast.next_6_months, color: 'text-orange-400' },
 { label: 'Next 12 Months', value: forecast.next_12_months, color: 'text-white' },
 ].map(f => (
 <div key={f.label} className="text-center p-4 rounded-lg bg-white/5">
 <p className="text-[var(--color-text-muted)] text-xs mb-1">{f.label}</p>
 <p className={`text-xl font-bold ${f.color}`} data-testid={`forecast-${f.label.replace(/ /g, '-').toLowerCase()}`}>{fmt(f.value)}</p>
 </div>
 ))}
 </div>
 <div className="grid grid-cols-3 gap-4">
 {[
 { label: 'Immediate (0-3m)', value: byPriority.immediate, color: 'border-red-500/30' },
 { label: 'Short Term (3-6m)', value: byPriority.short_term, color: 'border-orange-500/30' },
 { label: 'Medium Term (6-12m)', value: byPriority.medium_term, color: 'border-yellow-500/30' },
 ].map(p => (
 <div key={p.label} className={`text-center p-3 rounded-lg border ${p.color} bg-white/5`}>
 <p className="text-[var(--color-text-muted)] text-[11px] mb-1">{p.label}</p>
 <p className="text-base font-semibold text-white">{fmt(p.value)}</p>
 </div>
 ))}
 </div>
 </Card>
);

/* ─── Equipment Detail Row ─── */
const EquipmentRow = ({ item, justification, isExpanded, onToggle }) => {
 const cfg = STATUS_CONFIG[item.capex.status] || STATUS_CONFIG.monitor;
 const IconComp = cfg.icon;
 return (
 <div className="border border-white/10 rounded-lg overflow-hidden mb-2" data-testid={`capex-equip-${item.id}`}>
 <button onClick={onToggle} className="w-full flex items-center gap-3 p-4 hover:bg-white/5 transition-colors text-left">
 <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${cfg.bg}`}>
 <IconComp size={18} className={cfg.text} />
 </div>
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2 flex-wrap">
 <p className="text-white font-medium truncate">{item.name}</p>
 <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${cfg.bg} ${cfg.text}`}>
 <span className="w-1.5 h-1.5 rounded-full" style={{ background: cfg.dotColor || cfg.color }} />
 {cfg.label}
 </span>
 </div>
 <p className="text-[var(--color-text-muted)] text-xs truncate">{item.equipment_type} · {item.manufacturer || 'Unknown'} · {item.location}</p>
 </div>
 <div className="text-right flex-shrink-0 hidden sm:block">
 <p className="text-white font-mono text-sm">{item.capex.score}/100</p>
 <p className="text-[var(--color-text-muted)] text-xs">{fmt(item.capex.replacement_cost)}</p>
 </div>
 {isExpanded ? <ChevronUp size={16} className="text-[var(--color-text-muted)] flex-shrink-0" /> : <ChevronDown size={16} className="text-[var(--color-text-muted)] flex-shrink-0" />}
 </button>
 {isExpanded && (
 <div className="px-4 pb-4 space-y-4 border-t border-white/5">
 <p className="text-[var(--color-text-muted)] text-[11px] pt-3 leading-relaxed">
 Scores below are each <strong className="text-white">0–100 indicators of replacement urgency</strong> — higher means replace sooner.
 Actual age and warranty remaining are shown further down.
 </p>
 {/* Score Breakdown (0-100 replacement-urgency indicators) */}
 <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
 {[
 { label: 'Age Score', key: 'age' },
 { label: 'Fault Count Score', key: 'fault_count' },
 { label: 'Frequency Score', key: 'fault_frequency' },
 { label: 'Severity Score', key: 'severity' },
 { label: 'Warranty Score', key: 'warranty' },
 ].map(s => (
 <div key={s.key} className="bg-white/5 rounded-lg p-3 text-center">
 <p className="text-[var(--color-text-muted)] text-[10px] mb-1">{s.label}</p>
 <p className="text-white font-mono text-sm">
 {item.capex.score_breakdown?.[s.key] != null
 ? Math.round(item.capex.score_breakdown[s.key])
 : '—'}
 <span className="text-[var(--color-text-muted)] text-[10px]">/100</span>
 </p>
 </div>
 ))}
 </div>
 {/* Real Asset Facts */}
 <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
 <div className="bg-white/5 rounded-lg p-3">
 <p className="text-[var(--color-text-muted)] text-[10px]">Total Faults</p>
 <p className="text-white font-semibold">{item.total_faults}</p>
 </div>
 <div className="bg-white/5 rounded-lg p-3">
 <p className="text-[var(--color-text-muted)] text-[10px]">Open Faults</p>
 <p className="text-white font-semibold">{item.open_faults}</p>
 </div>
 <div className="bg-white/5 rounded-lg p-3">
 <p className="text-[var(--color-text-muted)] text-[10px]">Age in Service</p>
 <p className="text-white font-semibold">
 {item.capex.age_years != null
 ? `${item.capex.age_years} years`
 : <span className="text-[var(--color-text-muted)] font-normal text-xs">No install date</span>}
 </p>
 </div>
 <div className="bg-white/5 rounded-lg p-3">
 <p className="text-[var(--color-text-muted)] text-[10px]">Warranty Remaining</p>
 <p className="text-white font-semibold">
 {item.capex.warranty_months_remaining == null
 ? <span className="text-[var(--color-text-muted)] font-normal text-xs">No warranty date</span>
 : item.capex.warranty_months_remaining <= 0
 ? <span className="text-red-400 font-semibold">Expired</span>
 : `${item.capex.warranty_months_remaining} months`}
 </p>
 </div>
 <div className="bg-white/5 rounded-lg p-3">
 <p className="text-[var(--color-text-muted)] text-[10px]">Repair Spend (est.)</p>
 <p className="text-white font-semibold">{fmt(item.capex.estimated_repair_spend)}</p>
 </div>
 </div>
 {/* Suggested Action */}
 <div className={`rounded-lg p-4 ${cfg.bg}`}>
 <p className={`font-semibold text-sm ${cfg.text}`}>{item.capex.suggested_action}</p>
 {item.capex.replace_within_months && (
 <p className="text-[var(--color-text-muted)] text-xs mt-1">Replacement cost: {fmt(item.capex.replacement_cost)} · Timeline: within {item.capex.replace_within_months} months</p>
 )}
 </div>
 {/* AI Justification */}
 {justification && (
 <div className="rounded-lg p-4 bg-[rgb(var(--rgb-brand-blue)/0.1)] border border-[rgb(var(--rgb-brand-blue)/0.2)]">
 <div className="flex items-center gap-2 mb-2">
 <Brain size={14} className="text-[var(--color-brand-blue)]" />
 <p className="text-[var(--color-brand-blue)] text-xs font-semibold">AI-Generated Justification</p>
 </div>
 <p className="text-[#ccc] text-sm leading-relaxed italic">&ldquo;{justification}&rdquo;</p>
 </div>
 )}
 </div>
 )}
 </div>
 );
};


/* ─── PDF Export ─── */
const generatePDF = (data, justifications) => {
 const win = window.open('', '_blank');
 if (!win) { notify.error('Please allow popups for PDF export'); return; }

 const summary = data.summary;
 const forecast = data.forecast;
 const flagged = data.equipment.filter(e => e.capex.status !== 'healthy' && e.capex.status !== 'monitor');
 const now = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

 const statusBadge = (status) => {
 const colors = { healthy: 'var(--color-success-alt-2)', monitor: 'var(--color-yellow)', at_risk: 'var(--color-orange)', replace_soon: 'var(--color-danger)', replace_now: 'var(--color-neutral-950-alt)' };
 return `<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;color:white;background:${colors[status] || '#666'}">${status.replace(/_/g, ' ').replace(/\b\w/g,c=>c.toUpperCase())}</span>`;
 };

 const equipRows = data.equipment.map(e => `
 <tr>
 <td style="padding:8px;border-bottom:1px solid #eee">${e.name}</td>
 <td style="padding:8px;border-bottom:1px solid #eee">${e.equipment_type}</td>
 <td style="padding:8px;border-bottom:1px solid #eee">${e.location}</td>
 <td style="padding:8px;border-bottom:1px solid #eee;text-align:center">${statusBadge(e.capex.status)}</td>
 <td style="padding:8px;border-bottom:1px solid #eee;text-align:center;font-family:monospace">${e.capex.score}</td>
 <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;font-weight:600">${e.capex.replace_within_months ? fmt(e.capex.replacement_cost) : '—'}</td>
 </tr>
 `).join('');

 const justificationRows = flagged.map(e => {
 const j = justifications[e.name];
 return `
 <div style="page-break-inside:avoid;margin-bottom:16px;padding:16px;border:1px solid var(--color-border-alt);border-radius:8px;border-left:4px solid ${STATUS_CONFIG[e.capex.status]?.color || '#999'}">
 <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
 <strong style="font-size:14px">${e.name}</strong>
 ${statusBadge(e.capex.status)}
 </div>
 <p style="color:#666;font-size:12px;margin:4px 0">${e.equipment_type} · ${e.manufacturer || ''} · ${e.location} · Score: ${e.capex.score}/100</p>
 <p style="color:#666;font-size:12px;margin:4px 0">Faults: ${e.total_faults} · Est. repair spend: ${fmt(e.capex.estimated_repair_spend)} · Replacement: ${fmt(e.capex.replacement_cost)}</p>
 ${j ? `<p style="margin-top:8px;font-style:italic;color:#333;line-height:1.6;font-size:13px;background:var(--color-blue-50);padding:10px;border-radius:6px">"${j}"</p>` : ''}
 <p style="margin-top:6px;font-weight:600;color:var(--color-brand-blue);font-size:13px">${e.capex.suggested_action}</p>
 </div>
 `;
 }).join('');

 win.document.write(`<!DOCTYPE html><html><head><title>CAPEX Intelligence Report - GymAxis AI</title>
 <style>
 body{font-family:'Segoe UI',Arial,sans-serif;padding:40px;color:var(--color-surface-dark-2);max-width:900px;margin:0 auto;line-height:1.5}
 h1{color:var(--color-brand-blue);border-bottom:3px solid var(--color-brand-blue);padding-bottom:12px;font-size:24px}
 h2{color:#333;border-bottom:1px solid #ddd;padding-bottom:8px;margin-top:32px;font-size:18px}
 .header-meta{display:flex;justify-content:space-between;color:#666;font-size:12px;margin-bottom:24px}
 .summary-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:16px 0}
 .summary-card{padding:16px;border-radius:8px;text-align:center;border:1px solid var(--color-border-alt)}
 .summary-card .label{font-size:11px;color:#666;margin-bottom:4px}
 .summary-card .value{font-size:24px;font-weight:700}
 .forecast-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}
 .forecast-card{padding:16px;text-align:center;border-radius:8px;border:1px solid var(--color-border-alt);background:var(--color-neutral-25-alt)}
 table{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}
 th{text-align:left;padding:10px 8px;border-bottom:2px solid var(--color-brand-blue);color:var(--color-brand-blue);font-size:12px}
 @media print{body{padding:20px}h1{font-size:20px}.summary-grid{grid-template-columns:repeat(5,1fr)}}
 .page-break{page-break-before:always}
 .footer{margin-top:40px;padding-top:16px;border-top:1px solid #ddd;text-align:center;color:#999;font-size:11px}
 </style></head><body>
 <h1>CAPEX Intelligence Report</h1>
 <div class="header-meta">
 <span>Generated: ${now}</span>
 <span>GymAxis AI · Equipment Maintenance Platform</span>
 </div>

 <h2>Executive Summary</h2>
 <div class="summary-grid">
 <div class="summary-card"><div class="label">Total Equipment</div><div class="value">${summary.total}</div></div>
 <div class="summary-card" style="border-color:var(--color-success-alt-2)"><div class="label" style="color:var(--color-success-alt-2)">Healthy</div><div class="value" style="color:var(--color-success-alt-2)">${summary.healthy}</div></div>
 <div class="summary-card" style="border-color:var(--color-orange)"><div class="label" style="color:var(--color-orange)">At Risk</div><div class="value" style="color:var(--color-orange)">${summary.at_risk}</div></div>
 <div class="summary-card" style="border-color:var(--color-danger)"><div class="label" style="color:var(--color-danger)">Replace Required</div><div class="value" style="color:var(--color-danger)">${(summary.replace_soon || 0) + (summary.replace_now || 0)}</div></div>
 <div class="summary-card" style="border-color:var(--color-brand-blue)"><div class="label" style="color:var(--color-brand-blue)">Est. Total (12m)</div><div class="value" style="color:var(--color-brand-blue)">${fmt(forecast.next_12_months)}</div></div>
 </div>

 <h2>CAPEX Forecast</h2>
 <div class="forecast-grid">
 <div class="forecast-card"><div class="label" style="font-size:11px;color:#666">Next 3 Months</div><div style="font-size:20px;font-weight:700;color:var(--color-danger)">${fmt(forecast.next_3_months)}</div></div>
 <div class="forecast-card"><div class="label" style="font-size:11px;color:#666">Next 6 Months</div><div style="font-size:20px;font-weight:700;color:var(--color-orange)">${fmt(forecast.next_6_months)}</div></div>
 <div class="forecast-card"><div class="label" style="font-size:11px;color:#666">Next 12 Months</div><div style="font-size:20px;font-weight:700;color:var(--color-surface-dark-2)">${fmt(forecast.next_12_months)}</div></div>
 </div>

 <h2>Equipment Breakdown</h2>
 <table>
 <thead><tr>
 <th>Machine</th><th>Type</th><th>Location</th><th style="text-align:center">Status</th><th style="text-align:center">Score</th><th style="text-align:right">Replacement</th>
 </tr></thead>
 <tbody>${equipRows}</tbody>
 </table>

 <div class="page-break"></div>
 <h2>CAPEX Recommendations & AI Justifications</h2>
 ${flagged.length > 0 ? justificationRows : '<p style="color:#999">No equipment currently flagged for replacement.</p>'}

 <div class="footer">
 <p>This report was generated by GymAxis AI CAPEX Intelligence. Data is based on equipment records, fault history, and AI analysis.</p>
 <p>Suitable for board meetings, council submissions, and budget approvals.</p>
 </div>
 </body></html>`);
 win.document.close();
 setTimeout(() => win.print(), 500);
};


/* ─── Main Component ─── */
const CapexIntelligenceTab = () => {
 const { API, user } = useAuth();
 const [data, setData] = useState(null);
 const [loading, setLoading] = useState(true);
 const [justifications, setJustifications] = useState({});
 const [generatingAI, setGeneratingAI] = useState(false);
 const [expanded, setExpanded] = useState({});
 const [filter, setFilter] = useState('all');
 const [justificationsLoaded, setJustificationsLoaded] = useState(false);
 const token = localStorage.getItem('token');
 const headers = { Authorization: `Bearer ${token}` };

 const isRestricted = !['owner', 'manager', 'master_admin'].includes(user?.role);

 const loadData = useCallback(async () => {
 setLoading(true);
 try {
 const [analysisRes, justRes] = await Promise.all([
 axios.get(`${API}/capex/analysis`, { headers }),
 axios.get(`${API}/capex/justifications`, { headers }).catch(() => ({ data: { justifications: {} } })),
 ]);
 setData(analysisRes.data);
 if (justRes.data?.justifications) {
 setJustifications(justRes.data.justifications);
 setJustificationsLoaded(true);
 }
 } catch (err) {
 if (err.response?.status === 403) {
 notify.error('CAPEX data is restricted to Owner and Manager roles');
 } else {
 notify.error('Failed to load CAPEX data');
 }
 } finally {
 setLoading(false);
 }
 }, [API]);

 useEffect(() => { loadData(); }, [loadData]);

 const generateJustifications = async () => {
 setGeneratingAI(true);
 try {
 const res = await axios.post(`${API}/capex/generate-justifications`, {}, { headers });
 setJustifications(res.data.justifications || {});
 setJustificationsLoaded(true);
 notify.success(`Generated ${res.data.count} AI justifications`);
 } catch {
 notify.error('Failed to generate AI justifications');
 } finally {
 setGeneratingAI(false);
 }
 };

 if (isRestricted) {
 return (
 <div className="text-center py-16" data-testid="capex-restricted">
 <Shield size={40} className="text-[var(--color-text-muted)] mx-auto mb-4" />
 <h3 className="text-lg font-semibold text-white mb-2">Restricted Access</h3>
 <p className="text-[var(--color-text-muted)]">CAPEX Intelligence is available to Owner and Manager roles only.</p>
 </div>
 );
 }

 if (loading) return <div className="text-[var(--color-text-muted)] text-center py-16"><Loader2 className="animate-spin mx-auto mb-2" size={24} />Loading CAPEX analysis...</div>;
 if (!data) return <div className="text-[var(--color-text-muted)] text-center py-16">Unable to load CAPEX data</div>;

 const filteredEquipment = filter === 'all' ? data.equipment : data.equipment.filter(e => e.capex.status === filter);

 return (
 <div className="space-y-6" data-testid="capex-intelligence-tab">
 {/* Header */}
 <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
 <div>
 <h2 className="text-2xl font-semibold text-white">CAPEX Intelligence</h2>
 <p className="text-[var(--color-text-muted)] text-sm">Strategic equipment replacement analysis and budget forecasting</p>
 </div>
 <div className="flex items-center gap-2">
 <Button
 size="sm"
 onClick={generateJustifications}
 disabled={generatingAI}
 className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-alt)]"
 data-testid="capex-generate-ai-btn"
 >
 {generatingAI ? <Loader2 className="animate-spin mr-2" size={14} /> : <Brain size={14} className="mr-2" />}
 {generatingAI ? 'Generating...' : 'Generate AI Justifications'}
 </Button>
 <Button
 size="sm"
 variant="outline"
 onClick={() => generatePDF(data, justifications)}
 className="border-white/10 text-[var(--color-text-muted)] hover:text-white"
 data-testid="capex-export-pdf-btn"
 >
 <Download size={14} className="mr-2" /> Export PDF
 </Button>
 </div>
 </div>

 {/* Summary */}
 <SummaryCards summary={data.summary} forecast={data.forecast} />

 {/* Priority Table */}
 <PriorityTable items={data.priority_replacements || []} />

 {/* Charts */}
 <CapexCharts summary={data.summary} byType={data.by_type} />

 {/* Forecast */}
 <ForecastSection forecast={data.forecast} byPriority={data.by_priority || {}} />

 {/* Equipment List */}
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="capex-equipment-list">
 <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
 <h3 className="text-lg font-semibold text-white">All Equipment — CAPEX Status</h3>
 <div className="flex gap-1.5 flex-wrap">
 {[
 { key: 'all', label: 'All' },
 { key: 'replace_now', label: 'Replace Now', color: 'text-zinc-300' },
 { key: 'replace_soon', label: 'Replace Soon', color: 'text-red-400' },
 { key: 'at_risk', label: 'At Risk', color: 'text-orange-400' },
 { key: 'monitor', label: 'Monitor', color: 'text-yellow-400' },
 { key: 'healthy', label: 'Healthy', color: 'text-green-400' },
 ].map(f => (
 <button
 key={f.key}
 onClick={() => setFilter(f.key)}
 className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
 filter === f.key ? 'bg-[var(--color-brand-blue)] text-white' : `bg-white/5 ${f.color || 'text-[var(--color-text-muted)]'} hover:bg-white/10`
 }`}
 data-testid={`capex-filter-${f.key}`}
 >
 {f.label}
 </button>
 ))}
 </div>
 </div>
 <div className="max-h-[600px] overflow-y-auto">
 {filteredEquipment.length > 0 ? filteredEquipment.map(item => (
 <EquipmentRow
 key={item.id}
 item={item}
 justification={justifications[item.name]}
 isExpanded={!!expanded[item.id]}
 onToggle={() => setExpanded(prev => ({ ...prev, [item.id]: !prev[item.id] }))}
 />
 )) : (
 <p className="text-[var(--color-text-muted)] text-center py-8">No equipment matches this filter</p>
 )}
 </div>
 </Card>
 </div>
 );
};

export default CapexIntelligenceTab;
