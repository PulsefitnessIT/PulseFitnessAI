import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { Shield, Plus, Printer, Sparkles, ChevronDown, ChevronUp, Camera } from 'lucide-react';

const RISK_COLORS = {
 low: { bg: 'bg-green-500/20', text: 'text-green-400', label: 'Low' },
 medium: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', label: 'Medium' },
 high: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'High' },
};

const getRiskLevel = (rrn) => {
 if (rrn <= 6) return 'low';
 if (rrn <= 18) return 'medium';
 return 'high';
};

const RiskAssessmentTab = () => {
 const { _t } = useTranslation();
 const { user, API } = useAuth();
 const [assessments, setAssessments] = useState([]);
 const [sites, setSites] = useState([]);
 const [showCreateDialog, setShowCreateDialog] = useState(false);
 const [showViewDialog, setShowViewDialog] = useState(false);
 const [selectedRA, setSelectedRA] = useState(null);
 const [generating, setGenerating] = useState(false);
 const [saving, setSaving] = useState(false);
 const [photoAnalyzing, setPhotoAnalyzing] = useState(false);
 const [photos, setPhotos] = useState([]);
 const photoInputRef = useRef(null);
 const _printRef = useRef(null);

 const [form, setForm] = useState({
 title: '',
 site_name: '',
 assessor: user?.full_name || '',
 assessment_date: new Date().toISOString().split('T')[0],
 validity_period: '12 months',
 hazards: [],
 recommendations: [],
 notes: '',
 photo_url: null
 });

 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
 useEffect(() => { loadAssessments(); loadSites(); }, []);

 const loadAssessments = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/risk-assessments`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setAssessments(res.data.assessments || []);
 } catch (error) {
 console.error('Failed to load risk assessments:', error);
 }
 };

 const loadSites = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/sites`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 const siteList = res.data.sites || [];
 setSites(siteList);
 if (siteList.length === 1) {
 setForm(prev => ({ ...prev, site_name: siteList[0].name }));
 }
 } catch (error) {
 console.error('Failed to load sites:', error);
 }
 };

 const handleAIGenerate = async () => {
 if (!form.title) {
 notify.error('Enter an assessment title first (e.g.,"Treadmill")');
 return;
 }
 setGenerating(true);
 const token = localStorage.getItem('token');
 try {
 const res = await axios.post(`${API}/risk-assessments/ai-generate`, {
 site_name: form.site_name || 'Gym',
 equipment_types: [form.title],
 site_description: form.notes || '',
 specific_focus: form.title,
 assessor: form.assessor || '',
 assessment_date: form.assessment_date || ''
 }, { headers: { Authorization: `Bearer ${token}` } });

 const hazards = (res.data.hazards || []).map((h, _idx) => ({
 ...h,
 rrn: (h.plr || 1) * (h.psr || 1),
 post_rrn: (h.post_plr || 1) * (h.post_psr || 1)
 }));
 setForm({ ...form, hazards });
 notify.success(`AI generated ${hazards.length} hazards`);
 } catch (error) {
 notify.error('Failed to generate AI hazards');
 } finally {
 setGenerating(false);
 }
 };

 const handlePhotoAnalyze = async (fileList) => {
 const files = Array.from(fileList || []);
 if (!files.length) return;
 setPhotoAnalyzing(true);
 const token = localStorage.getItem('token');
 try {
 const fd = new FormData();
 files.forEach(f => fd.append('files', f));
 const res = await axios.post(`${API}/risk-assessments/photo-analyze`, fd, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
 });
 const d = res.data || {};
 const newHazards = (d.hazards || []).map(h => ({
 ...h,
 rrn: (h.plr || 1) * (h.psr || 1),
 post_rrn: (h.post_plr || 1) * (h.post_psr || 1),
 }));
 const urls = d.photo_urls || (d.photo_url ? [d.photo_url] : []);
 setPhotos(prev => [...prev, ...urls.map(u => ({ url: u }))]);
 setForm(prev => ({
 ...prev,
 hazards: [...prev.hazards, ...newHazards],
 photo_url: prev.photo_url || urls[0] || null,
 notes: [
 prev.notes,
 d.equipment_identified ? `AI photo review — Equipment: ${d.equipment_identified}` : '',
 d.environment_observations ? `Environment: ${d.environment_observations}` : '',
 ].filter(Boolean).join('\n'),
 }));
 notify.success(`AI reviewed ${urls.length} photo${urls.length !== 1 ? 's' : ''} — added ${newHazards.length} hazard${newHazards.length !== 1 ? 's' : ''}`);
 } catch (e) {
 notify.error('Photo analysis failed');
 } finally {
 setPhotoAnalyzing(false);
 }
 };

 const addBlankHazard = () => {
 setForm({
 ...form,
 hazards: [...form.hazards, {
 hazard: '', harm: '', who: '', recommended_controls: '',
 controls_in_place: '', plr: 1, psr: 1, rrn: 1,
 further_controls: '', post_plr: 1, post_psr: 1, post_rrn: 1
 }]
 });
 };

 const updateHazard = (idx, field, value) => {
 const updated = [...form.hazards];
 updated[idx] = { ...updated[idx], [field]: value };
 if (['plr', 'psr'].includes(field)) {
 updated[idx].rrn = (updated[idx].plr || 1) * (updated[idx].psr || 1);
 }
 if (['post_plr', 'post_psr'].includes(field)) {
 updated[idx].post_rrn = (updated[idx].post_plr || 1) * (updated[idx].post_psr || 1);
 }
 setForm({ ...form, hazards: updated });
 };

 const removeHazard = (idx) => {
 setForm({ ...form, hazards: form.hazards.filter((_, i) => i !== idx) });
 };

 const handleSave = async () => {
 if (!form.title || !form.site_name) {
 notify.error('Title and Site Name are required');
 return;
 }
 setSaving(true);
 const token = localStorage.getItem('token');
 try {
 const res = await axios.post(`${API}/risk-assessments`, form, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setAssessments([res.data, ...assessments]);
 setShowCreateDialog(false);
 setForm({
 title: '', site_name: '', assessor: user?.full_name || '',
 assessment_date: new Date().toISOString().split('T')[0],
 validity_period: '12 months', hazards: [], recommendations: [], notes: ''
 });
 notify.success('Risk Assessment saved');
 } catch (error) {
 notify.error('Failed to save risk assessment');
 } finally {
 setSaving(false);
 }
 };

 const handlePrint = (raToprint) => {
 const printWindow = window.open('', '_blank');
 const ra = raToprint || selectedRA;
 if (!ra || !printWindow) return;

 const hazardRows = (ra.hazards || []).map(h => {
 const rrn = (h.plr || 1) * (h.psr || 1);
 const postRrn = (h.post_plr || 1) * (h.post_psr || 1);
 const riskColor = rrn <= 6 ? 'var(--color-success-alt-2)' : rrn <= 18 ? 'var(--color-yellow)' : 'var(--color-danger)';
 const postColor = postRrn <= 6 ? 'var(--color-success-alt-2)' : postRrn <= 18 ? 'var(--color-yellow)' : 'var(--color-danger)';
 return `<tr>
 <td>${h.hazard || ''}</td>
 <td>${h.harm || ''}</td>
 <td>${h.who || ''}</td>
 <td>${h.recommended_controls || ''}</td>
 <td>${h.controls_in_place || ''}</td>
 <td style="text-align:center">${h.plr || ''}</td>
 <td style="text-align:center">${h.psr || ''}</td>
 <td style="text-align:center;background:${riskColor}20;color:${riskColor};font-weight:bold">${rrn}</td>
 <td>${h.further_controls || ''}</td>
 <td style="text-align:center">${h.post_plr || ''}</td>
 <td style="text-align:center">${h.post_psr || ''}</td>
 <td style="text-align:center;background:${postColor}20;color:${postColor};font-weight:bold">${postRrn}</td>
 </tr>`;
 }).join('');

 printWindow.document.write(`<!DOCTYPE html><html><head><title>Risk Assessment - ${ra.title}</title>
 <style>
 body { font-family: Arial, sans-serif; padding: 20px; color: #333; }
 h1 { color: var(--color-brand-blue); border-bottom: 2px solid var(--color-brand-blue); padding-bottom: 10px; }
 .header-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 20px 0; }
 .header-grid div { padding: 8px; background: var(--color-neutral-75); border-radius: 4px; }
 .header-grid label { font-weight: bold; font-size: 12px; color: #666; }
 table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 11px; }
 th { background: var(--color-brand-blue); color: white; padding: 8px; text-align: left; }
 td { padding: 6px 8px; border: 1px solid #ddd; vertical-align: top; }
 tr:nth-child(even) { background: var(--color-neutral-10); }
 .risk-key { display: flex; gap: 20px; margin: 10px 0; font-size: 12px; }
 .risk-key span { padding: 4px 12px; border-radius: 4px; }
 @media print { body { padding: 0; } }
 </style></head><body>
 <h1>Risk Assessment: ${ra.title}</h1>
 <div class="header-grid">
 <div><label>Site/Facility</label><br>${ra.site_name}</div>
 <div><label>Assessor</label><br>${ra.assessor}</div>
 <div><label>Date</label><br>${ra.assessment_date}</div>
 <div><label>Validity</label><br>${ra.validity_period || '12 months'}</div>
 </div>
 <div class="risk-key">
 <strong>Risk Rating: </strong>
 <span style="background:var(--color-success-alt-2)20;color:var(--color-success-alt-2)">Low (1-6)</span>
 <span style="background:var(--color-yellow)20;color:var(--color-yellow)">Medium (7-18)</span>
 <span style="background:var(--color-danger)20;color:var(--color-danger)">High (19-36)</span>
 </div>
 <table>
 <thead><tr>
 <th>Hazard</th><th>How Harmed</th><th>Who</th>
 <th>Recommended Controls</th><th>Controls in Place</th>
 <th>PLR</th><th>PSR</th><th>RRN</th>
 <th>Further Controls</th>
 <th>Post-PLR</th><th>Post-PSR</th><th>Post-RRN</th>
 </tr></thead>
 <tbody>${hazardRows}</tbody>
 </table>
 ${ra.notes ? `<div style="margin-top:20px;padding:15px;background:var(--color-neutral-75);border-radius:4px;"><strong>Notes:</strong><br>${ra.notes}</div>` : ''}
 <div style="margin-top:20px;padding:15px;background:#fff3cd;border:1px solid #ffc107;border-radius:4px;font-size:11px;color:#856404;">
 <strong>Disclaimer:</strong> This risk assessment is provided for example and guidance purposes only. Health and safety compliance remains the sole responsibility of the site owner, operator, and designated competent person(s). All assessments must be reviewed, validated, and signed off by an appropriately qualified assessor before implementation.
 </div>
 <div style="margin-top:30px;font-size:11px;color:#999;">Generated by Pulse Fitness AI | ${new Date().toLocaleDateString()}</div>
 </body></html>`);
 printWindow.document.close();
 printWindow.print();
 };

 const viewAssessment = (ra) => {
 setSelectedRA(ra);
 setShowViewDialog(true);
 };

 return (
 <div className="space-y-6" data-testid="risk-assessment-tab">
 {/* H&S Disclaimer Banner */}
 <div className="p-4 bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/30 rounded-lg flex items-start gap-3" data-testid="risk-assessment-disclaimer">
 <Shield size={20} className="text-amber-700 dark:text-amber-400 flex-shrink-0 mt-0.5" />
 <div>
 <p className="text-amber-800 dark:text-amber-400 font-semibold text-sm">Important — Health & Safety Responsibility</p>
 <p className="text-amber-700 dark:text-amber-300/80 text-xs mt-1">
 These risk assessments are provided for <strong>example and guidance purposes only</strong>. 
 Health and safety compliance remains the sole responsibility of the site owner, operator, and designated competent person(s). 
 All assessments must be reviewed, validated, and signed off by an appropriately qualified assessor before implementation.
 </p>
 </div>
 </div>

 <div className="flex items-center justify-between">
 <div>
 <h2 className="text-2xl font-semibold text-[var(--theme-text)]">Risk Assessments</h2>
 <p className="text-[var(--color-text-muted)]">Create, manage and print professional risk assessments for your facility</p>
 </div>
 <Button
 onClick={() => { setPhotos([]); setShowCreateDialog(true); }}
 className=""
 data-testid="new-risk-assessment-btn"
 >
 <Plus size={18} className="mr-1" /> New Assessment
 </Button>
 </div>

 {/* Assessment List */}
 <div className="grid grid-cols-1 gap-4">
 {assessments.map(ra => {
 const maxRRN = Math.max(...(ra.hazards || []).map(h => (h.plr || 1) * (h.psr || 1)), 0);
 const overallRisk = getRiskLevel(maxRRN);
 const rc = RISK_COLORS[overallRisk];
 return (
 <Card key={ra.id} className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6 hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors cursor-pointer" data-testid={`ra-card-${ra.id}`} onClick={() => viewAssessment(ra)}>
 <div className="flex items-start justify-between">
 <div>
 <div className="flex items-center gap-3 mb-2">
 <Shield className="text-[var(--color-brand-blue)]" size={20} />
 <h3 className="text-lg font-semibold text-[var(--theme-text)]">{ra.title}</h3>
 <Badge className={`${rc.bg} ${rc.text}`}>{rc.label} Risk</Badge>
 </div>
 <p className="text-[var(--color-text-muted)] text-sm">{ra.site_name} | Assessed by: {ra.assessor} | {ra.assessment_date}</p>
 <p className="text-[var(--color-text-muted)] text-sm mt-1">{(ra.hazards || []).length} hazards identified</p>
 </div>
 <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--theme-text)]" onClick={(e) => { e.stopPropagation(); handlePrint(ra); }}>
 <Printer size={16} className="mr-1" /> Print
 </Button>
 </div>
 </Card>
 );
 })}
 {assessments.length === 0 && (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-12 text-center">
 <Shield size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">No risk assessments yet. Create your first one.</p>
 </Card>
 )}
 </div>

 {/* Create Dialog */}
 <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] max-w-5xl max-h-[90vh] overflow-y-auto" data-testid="create-ra-dialog">
 <DialogHeader>
 <DialogTitle className="text-[var(--theme-text)]">New Risk Assessment</DialogTitle>
 </DialogHeader>

 <div className="space-y-4">
 {/* Instructions and Acronym Key */}
 <div className="p-4 bg-[rgb(var(--rgb-brand-blue)/0.1)] border border-[rgb(var(--rgb-brand-blue)/0.3)] rounded-lg" data-testid="ra-instructions">
 <h4 className="text-[var(--color-brand-blue)] text-sm font-semibold mb-2">How Risk Assessments Work</h4>
 <p className="text-[var(--color-text-muted)] text-xs mb-3">Enter a title describing what you want to assess (e.g.,"Treadmill" or"Free Weights Area"). The AI will generate hazards specific to that equipment or area only. You can also add hazards manually.</p>
 <div className="flex flex-wrap gap-3 text-xs">
 <span className="px-2 py-1 bg-[var(--theme-input-bg)] border border-[var(--theme-border)] rounded text-[var(--theme-text)]"><strong>PLR</strong> = Probability Likelihood Rating (1-6)</span>
 <span className="px-2 py-1 bg-[var(--theme-input-bg)] border border-[var(--theme-border)] rounded text-[var(--theme-text)]"><strong>PSR</strong> = Potential Severity Rating (1-6)</span>
 <span className="px-2 py-1 bg-[var(--theme-input-bg)] border border-[var(--theme-border)] rounded text-[var(--theme-text)]"><strong>RRN</strong> = Residual Risk Number (PLR x PSR)</span>
 </div>
 <div className="flex gap-3 mt-2 text-xs">
 <span className="px-2 py-1 rounded bg-green-500/20 text-green-400">Low Risk (1-6)</span>
 <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400">Medium Risk (7-18)</span>
 <span className="px-2 py-1 rounded bg-red-500/20 text-red-400">High Risk (19-36)</span>
 </div>
 </div>

 <div className="grid grid-cols-2 gap-4">
 <div>
 <Label className="text-[var(--theme-text)]">Assessment Title</Label>
 <Input value={form.title} onChange={e => setForm({...form, title: e.target.value})} placeholder="e.g., Treadmill Risk Assessment" className="bg-[var(--theme-input-bg)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="ra-title-input" />
 </div>
 <div>
 <Label className="text-[var(--theme-text)]">Site / Facility Name</Label>
 {sites.length > 0 ? (
 <Select value={form.site_name} onValueChange={v => setForm({...form, site_name: v})} data-testid="ra-site-select">
 <SelectTrigger className="bg-[var(--theme-input-bg)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="ra-site-trigger">
 <SelectValue placeholder="Select a site..." />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)]">
 {sites.map(s => (
 <SelectItem key={s.id} value={s.name} className="text-[var(--theme-text)]" data-testid={`ra-site-option-${s.id}`}>
 {s.name}{s.address ? ` — ${s.address}` : ''}
 </SelectItem>
 ))}
 </SelectContent>
 </Select>
 ) : (
 <Input value={form.site_name} onChange={e => setForm({...form, site_name: e.target.value})} placeholder="e.g., City Gym Manchester" className="bg-[var(--theme-input-bg)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="ra-site-input" />
 )}
 </div>
 <div>
 <Label className="text-[var(--theme-text)]">Assessor</Label>
 <Input value={form.assessor} onChange={e => setForm({...form, assessor: e.target.value})} className="bg-[var(--theme-input-bg)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="ra-assessor-input" />
 </div>
 <div>
 <Label className="text-[var(--theme-text)]">Assessment Date</Label>
 <Input type="date" value={form.assessment_date} onChange={e => setForm({...form, assessment_date: e.target.value})} className="bg-[var(--theme-input-bg)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="ra-date-input" />
 </div>
 </div>

 <div>
 <Label className="text-[var(--theme-text)]">Site Notes / Description</Label>
 <Textarea value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} rows={2} placeholder="Describe specific site conditions, layout, or concerns..." className="bg-[var(--theme-input-bg)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="ra-notes-input" />
 </div>

 {/* Hazards Section */}
 <div className="border-t border-[var(--theme-border)] pt-4">
 <div className="flex items-center justify-between mb-3">
 <h3 className="text-lg font-semibold text-[var(--theme-text)]">Hazards ({form.hazards.length})</h3>
 <div className="flex gap-2">
 <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--theme-text)]" onClick={addBlankHazard} data-testid="add-hazard-btn">
 <Plus size={14} className="mr-1" /> Add Hazard
 </Button>
 <input
 ref={photoInputRef}
 type="file"
 accept="image/*"
 multiple
 className="hidden"
 data-testid="ra-photo-input"
 onChange={(e) => { handlePhotoAnalyze(e.target.files); e.target.value = ''; }}
 />
 <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--theme-text)]" onClick={() => photoInputRef.current?.click()} disabled={photoAnalyzing} data-testid="ra-photo-analyze-btn">
 {photoAnalyzing ? (
 <span className="flex items-center gap-2">
 <span className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin"></span>
 Reviewing…
 </span>
 ) : (
 <><Camera size={14} className="mr-1" /> Analyse Photos (AI)</>
 )}
 </Button>
 <Button size="sm" className="" onClick={handleAIGenerate} disabled={generating || !form.title} data-testid="ai-generate-btn">
 {generating ? (
 <span className="flex items-center gap-2">
 <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
 Generating...
 </span>
 ) : (
 <><Sparkles size={14} className="mr-1" /> AI Generate</>
 )}
 </Button>
 </div>
 </div>

 {photos.length > 0 && (
 <div className="flex flex-wrap gap-2 mb-4" data-testid="ra-photo-thumbs">
 {photos.map((p, i) => (
 <div key={i} className="relative w-16 h-16 rounded-lg overflow-hidden border border-[var(--theme-border)]">
 <img src={p.url} alt={`RA photo ${i + 1}`} className="w-full h-full object-cover" loading="lazy" />
 </div>
 ))}
 <span className="self-center text-xs text-[var(--color-text-muted)]">{photos.length} photo{photos.length !== 1 ? 's' : ''} reviewed by AI</span>
 </div>
 )}

 {form.hazards.length === 0 && (
 <div className="text-center py-6 text-[var(--color-text-muted)]">
 <p>No hazards added yet. Use AI Generate or add manually.</p>
 </div>
 )}

 {form.hazards.map((h, idx) => (
 <HazardRow key={idx} hazard={h} idx={idx} onChange={updateHazard} onRemove={removeHazard} />
 ))}
 </div>

 <div className="flex gap-3 pt-4 border-t border-[var(--theme-border)]">
 <Button onClick={handleSave} disabled={saving} className="flex-1" data-testid="save-ra-btn">
 {saving ? 'Saving...' : 'Submit'}
 </Button>
 <Button variant="outline" className="border-[var(--theme-border)] text-[var(--theme-text)]" onClick={() => setShowCreateDialog(false)}>
 Cancel
 </Button>
 </div>
 </div>
 </DialogContent>
 </Dialog>

 {/* View Dialog */}
 <Dialog open={showViewDialog} onOpenChange={setShowViewDialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] max-w-5xl max-h-[90vh] overflow-y-auto" data-testid="view-ra-dialog">
 {selectedRA && (
 <>
 <DialogHeader>
 <div className="flex items-center justify-between">
 <DialogTitle className="text-[var(--theme-text)]">{selectedRA.title}</DialogTitle>
 <Button size="sm" onClick={handlePrint} className="bg-[var(--color-brand-blue)] text-white" data-testid="print-ra-btn">
 <Printer size={16} className="mr-1" /> Print
 </Button>
 </div>
 </DialogHeader>

 <div className="grid grid-cols-2 gap-4 mb-4">
 <div><span className="text-[var(--color-text-muted)] text-sm">Site:</span> <span className="text-[var(--theme-text)]">{selectedRA.site_name}</span></div>
 <div><span className="text-[var(--color-text-muted)] text-sm">Assessor:</span> <span className="text-[var(--theme-text)]">{selectedRA.assessor}</span></div>
 <div><span className="text-[var(--color-text-muted)] text-sm">Date:</span> <span className="text-[var(--theme-text)]">{selectedRA.assessment_date}</span></div>
 <div><span className="text-[var(--color-text-muted)] text-sm">Validity:</span> <span className="text-[var(--theme-text)]">{selectedRA.validity_period}</span></div>
 </div>

 <div className="flex gap-4 mb-4 text-sm">
 <span className="px-3 py-1 rounded bg-green-500/20 text-green-400">Low (1-6)</span>
 <span className="px-3 py-1 rounded bg-yellow-500/20 text-yellow-400">Medium (7-18)</span>
 <span className="px-3 py-1 rounded bg-red-500/20 text-red-400">High (19-36)</span>
 </div>

 <div className="overflow-x-auto">
 <table className="w-full text-sm">
 <thead>
 <tr className="bg-[rgb(var(--rgb-brand-blue)/0.2)]">
 <th className="p-2 text-left text-[var(--color-brand-blue)]">Hazard</th>
 <th className="p-2 text-left text-[var(--color-brand-blue)]">How Harmed</th>
 <th className="p-2 text-left text-[var(--color-brand-blue)]">Who</th>
 <th className="p-2 text-center text-[var(--color-brand-blue)]">PLR</th>
 <th className="p-2 text-center text-[var(--color-brand-blue)]">PSR</th>
 <th className="p-2 text-center text-[var(--color-brand-blue)]">RRN</th>
 <th className="p-2 text-left text-[var(--color-brand-blue)]">Controls</th>
 <th className="p-2 text-center text-[var(--color-brand-blue)]">Post-RRN</th>
 </tr>
 </thead>
 <tbody>
 {(selectedRA.hazards || []).map((h, idx) => {
 const rrn = h.rrn || (h.plr || 1) * (h.psr || 1);
 const postRrn = h.post_rrn || (h.post_plr || 1) * (h.post_psr || 1);
 const riskLvl = getRiskLevel(rrn);
 const postLvl = getRiskLevel(postRrn);
 return (
 <tr key={idx} className="border-b border-white/5">
 <td className="p-2 text-[var(--theme-text)] font-medium">{h.hazard}</td>
 <td className="p-2 text-[var(--color-text-muted)]">{h.harm}</td>
 <td className="p-2 text-[var(--color-text-muted)]">{h.who}</td>
 <td className="p-2 text-center text-[var(--theme-text)]">{h.plr}</td>
 <td className="p-2 text-center text-[var(--theme-text)]">{h.psr}</td>
 <td className={`p-2 text-center font-bold ${RISK_COLORS[riskLvl].text}`}>{rrn}</td>
 <td className="p-2 text-[var(--color-text-muted)] text-xs">{h.controls_in_place}{h.further_controls ? ` + ${h.further_controls}` : ''}</td>
 <td className={`p-2 text-center font-bold ${RISK_COLORS[postLvl].text}`}>{postRrn}</td>
 </tr>
 );
 })}
 </tbody>
 </table>
 </div>

 {selectedRA.notes && (
 <div className="mt-4 p-3 bg-[var(--theme-input-bg)] border border-[var(--theme-border)] rounded-lg">
 <p className="text-[var(--color-text-muted)] text-sm"><strong className="text-[var(--theme-text)]">Notes:</strong> {selectedRA.notes}</p>
 </div>
 )}
 </>
 )}
 </DialogContent>
 </Dialog>
 </div>
 );
};

const HazardRow = ({ hazard, idx, onChange, onRemove }) => {
 const [expanded, setExpanded] = useState(true);
 const rrn = (hazard.plr || 1) * (hazard.psr || 1);
 const postRrn = (hazard.post_plr || 1) * (hazard.post_psr || 1);
 const riskLvl = getRiskLevel(rrn);
 const rc = RISK_COLORS[riskLvl];

 return (
 <div className="mb-3 bg-[var(--theme-input-bg)] border border-[var(--theme-border)] rounded-lg p-3" data-testid={`hazard-row-${idx}`}>
 <div className="flex items-center justify-between cursor-pointer" onClick={() => setExpanded(!expanded)}>
 <div className="flex items-center gap-2">
 <Badge className={`${rc.bg} ${rc.text}`}>RRN: {rrn}</Badge>
 <span className="text-[var(--theme-text)] text-sm font-medium">{hazard.hazard || `Hazard ${idx + 1}`}</span>
 </div>
 <div className="flex items-center gap-2">
 <Button size="sm" variant="ghost" className="text-red-400 h-6 w-6 p-0" onClick={(e) => { e.stopPropagation(); onRemove(idx); }}>x</Button>
 {expanded ? <ChevronUp size={16} className="text-[var(--color-text-muted)]" /> : <ChevronDown size={16} className="text-[var(--color-text-muted)]" />}
 </div>
 </div>

 {expanded && (
 <div className="mt-3 space-y-3">
 <div className="grid grid-cols-2 gap-3">
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Hazard</Label>
 <Input value={hazard.hazard} onChange={e => onChange(idx, 'hazard', e.target.value)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm h-8 mt-1" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">How might people be harmed</Label>
 <Input value={hazard.harm} onChange={e => onChange(idx, 'harm', e.target.value)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm h-8 mt-1" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Who might be harmed</Label>
 <Input value={hazard.who} onChange={e => onChange(idx, 'who', e.target.value)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm h-8 mt-1" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Controls in Place</Label>
 <Input value={hazard.controls_in_place} onChange={e => onChange(idx, 'controls_in_place', e.target.value)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm h-8 mt-1" />
 </div>
 </div>

 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Recommended Controls (industry practice)</Label>
 <Textarea value={hazard.recommended_controls} onChange={e => onChange(idx, 'recommended_controls', e.target.value)} rows={2} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm mt-1" />
 </div>

 <div className="grid grid-cols-6 gap-2">
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">PLR (1-6)</Label>
 <Input type="number" min={1} max={6} value={hazard.plr} onChange={e => onChange(idx, 'plr', parseInt(e.target.value) || 1)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm h-8 mt-1" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">PSR (1-6)</Label>
 <Input type="number" min={1} max={6} value={hazard.psr} onChange={e => onChange(idx, 'psr', parseInt(e.target.value) || 1)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm h-8 mt-1" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">RRN</Label>
 <div className={`mt-1 h-8 flex items-center justify-center rounded text-sm font-bold ${rc.bg} ${rc.text}`}>{rrn}</div>
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Post-PLR</Label>
 <Input type="number" min={1} max={6} value={hazard.post_plr} onChange={e => onChange(idx, 'post_plr', parseInt(e.target.value) || 1)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm h-8 mt-1" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Post-PSR</Label>
 <Input type="number" min={1} max={6} value={hazard.post_psr} onChange={e => onChange(idx, 'post_psr', parseInt(e.target.value) || 1)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm h-8 mt-1" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Post-RRN</Label>
 <div className={`mt-1 h-8 flex items-center justify-center rounded text-sm font-bold ${RISK_COLORS[getRiskLevel(postRrn)].bg} ${RISK_COLORS[getRiskLevel(postRrn)].text}`}>{postRrn}</div>
 </div>
 </div>

 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Further Control Measures</Label>
 <Textarea value={hazard.further_controls} onChange={e => onChange(idx, 'further_controls', e.target.value)} rows={2} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm mt-1" />
 </div>
 </div>
 )}
 </div>
 );
};

export default RiskAssessmentTab;
