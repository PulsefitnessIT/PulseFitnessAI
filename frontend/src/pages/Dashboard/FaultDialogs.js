import { useState, useCallback } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
 Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription
} from '@/components/ui/dialog';
import { AlertCircle, CheckCircle, Plus, Upload, Wrench, X, Image as ImageIcon, Video } from 'lucide-react';
import FaultTemplatePicker from './FaultTemplatePicker';
import FaultCodeSelect from './FaultCodeSelect';
import SaveAsTemplateButton from './SaveAsTemplateButton';
import { buildMachineTypeGroups, filterSerialsByGroup } from './faultMachineGrouping';
import { useBackGestureClose } from '@/lib/useBackGestureClose';
import CoverageBanner from '@/components/shared/CoverageBanner';

const FaultDialogs = ({
 // Issue dialog state
 showIssueDialog, issueStep, issueForm, setIssueForm, selectedMachineType, setSelectedMachineType,
 requireReporter = false, siteStaff = [], reporterStaffId = '', setReporterStaffId,
 allowOtherStaff = false, requireStaffPin = false, reporterPin = '', setReporterPin,
 reporterOther = {}, setReporterOther,
 allEquipment, issueLoading, issueMedia, setIssueMedia, faultMachines, activeMachineIdx, setActiveMachineIdx,
 triageResult, setTriageResult, machineTriageResults, resolutionNote, setResolutionNote,
 selectedFixStep, setSelectedFixStep, equipmentCoverage, coverageLoading, existingFaultWarning, setExistingFaultWarning,
 // Callbacks
 onResetDialog, onIssueSubmit, onAddMachine, onRemoveMachine, fetchCoverage,
 onResolution, onEngineerClick, setIssueStep, _setIssues,
 // PO Dialog state
 showPOPrompt, setShowPOPrompt, poForm, setPOForm, poCreating,
 onCreatePOAndLog, onSkipPOAndLog,
 // Success dialog
 showFaultSuccess, setShowFaultSuccess, faultSuccessType, lastIssue,
 // Service dialog
 showServiceDialog, setShowServiceDialog, serviceForm, setServiceForm, onServiceSubmit,
 // Helpers
 _getSeverityColor, getSeverityLabel, t, _i18n, issues,
 // Fault templates + codes
 API, canManageOrgTemplates,
}) => {
 // Iter 216f — back-gesture close on the main "Log a Fault" dialog so
 // mobile operators can swipe back to dismiss the modal instead of
 // accidentally exiting the dashboard. See `lib/useBackGestureClose.js`.
 const closeIssueDialog = useCallback(() => { onResetDialog && onResetDialog(); }, [onResetDialog]);
 useBackGestureClose(showIssueDialog, closeIssueDialog, 'gymaxis-issue-dialog');

 return (
 <>
 {/* Log Issue Dialog - Multi-step: Form → Triage → Resolution */}
 <Dialog open={showIssueDialog} onOpenChange={(open) => { if (!open) onResetDialog(); }}>
 <DialogContent
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] w-[calc(100vw-2rem)] max-w-3xl max-h-[90vh] overflow-y-auto"
 data-testid="issue-dialog"
 onInteractOutside={(e) => e.preventDefault()}
 onPointerDownOutside={(e) => e.preventDefault()}
 onFocusOutside={(e) => e.preventDefault()}
 onEscapeKeyDown={(e) => e.preventDefault()}
 >
 <DialogDescription className="sr-only">Log a fault: select the machine, describe the issue, attach photos or video, then submit.</DialogDescription>
 <DialogHeader>
 <DialogTitle className="text-[var(--theme-text)]" data-testid="issue-dialog-title">
 {issueStep === 'form' && t('faults.log_fault')}
 {issueStep === 'triage' && (faultMachines.length > 1
 ? t('triage.title_multi', { current: activeMachineIdx + 1, total: faultMachines.length })
 : t('triage.title')
 )}
 {issueStep === 'resolution' && (faultMachines.length > 1
 ? t('resolution.title_multi', { current: activeMachineIdx + 1, total: faultMachines.length })
 : t('resolution.title')
 )}
 </DialogTitle>
 </DialogHeader>

 {/* Step 1: Issue Form — multi-machine */}
 {issueStep === 'form' && (
 <form onSubmit={onIssueSubmit} className="space-y-4">
 {/* Site Staff Shared Login — mandatory "who is logging this fault?" */}
 {requireReporter && (
 <div className="rounded-lg border border-indigo-500/40 bg-indigo-500/5 p-3" data-testid="lite-fault-reporter">
 <Label className="text-[var(--theme-text)] font-semibold">{t('dialog.who_logging', 'Who is logging this fault?')} <span className="text-red-500">*</span></Label>
 <p className="text-xs text-[var(--color-text-muted)] mt-0.5 mb-2">{t('dialog.who_logging_help', 'Select your name so our service team knows who to contact if they need more information.')}</p>
 {siteStaff.length === 0 ? (
 <p className="text-xs text-amber-500" data-testid="lite-fault-reporter-empty">{t('dialog.no_staff', "Can't see your name? Please ask your site manager to add you to the site staff list.")}</p>
 ) : (
 <Select value={reporterStaffId || ''} onValueChange={(v) => setReporterStaffId && setReporterStaffId(v)}>
 <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] h-11" data-testid="lite-fault-reporter-select">
 <SelectValue placeholder={t('dialog.select_name', 'Select your name...')} />
 </SelectTrigger>
 <SelectContent>
 {siteStaff.map((s) => (
 <SelectItem key={s.id} value={s.id} data-testid={`lite-fault-reporter-${s.id}`}>{s.full_name} — {s.job_title}</SelectItem>
 ))}
 {allowOtherStaff && <SelectItem value="__other__" data-testid="lite-fault-reporter-other">Other staff member…</SelectItem>}
 </SelectContent>
 </Select>
 )}
 {reporterStaffId === '__other__' && (
 <div className="grid grid-cols-2 gap-2 mt-3" data-testid="lite-fault-other-fields">
 <Input placeholder="Full name" value={reporterOther.name || ''} onChange={(e) => setReporterOther({ ...reporterOther, name: e.target.value })} data-testid="lite-fault-other-name" />
 <Input placeholder="Job title" value={reporterOther.job_title || ''} onChange={(e) => setReporterOther({ ...reporterOther, job_title: e.target.value })} data-testid="lite-fault-other-title" />
 <Input placeholder="Email" value={reporterOther.email || ''} onChange={(e) => setReporterOther({ ...reporterOther, email: e.target.value })} data-testid="lite-fault-other-email" />
 <Input placeholder="Phone" value={reporterOther.phone || ''} onChange={(e) => setReporterOther({ ...reporterOther, phone: e.target.value })} data-testid="lite-fault-other-phone" />
 </div>
 )}
 {requireStaffPin && reporterStaffId && reporterStaffId !== '__other__' && siteStaff.find((s) => s.id === reporterStaffId)?.has_pin && (
 <div className="mt-3">
 <Label className="text-xs text-[var(--color-text-muted)]">Staff PIN</Label>
 <Input type="password" inputMode="numeric" value={reporterPin || ''} onChange={(e) => setReporterPin && setReporterPin(e.target.value.replace(/\D/g, '').slice(0, 8))} placeholder="Enter your PIN" className="h-10 mt-1" data-testid="lite-fault-reporter-pin" />
 </div>
 )}
 </div>
 )}
 {/* Quick-log template picker (org + personal templates) */}
 <FaultTemplatePicker
 API={API}
 onApply={(vals) => setIssueForm(prev => ({ ...prev, ...vals }))}
 />

 {/* Already-added machines */}
 {faultMachines.length > 0 && (
 <div className="space-y-2 mb-2" data-testid="fault-machines-list">
 <Label className="text-[var(--color-text-muted)] text-xs uppercase tracking-wide">{t('faults.machines_in_log', { count: faultMachines.length })}</Label>
 {faultMachines.map((m, idx) => (
 <div key={idx} className="flex items-center justify-between p-3 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg" data-testid={`fault-machine-${idx}`}>
 <div className="flex-1 min-w-0">
 <p className="text-[var(--theme-text)] text-sm font-medium truncate">{m.machine_type} — {m.serial_number}</p>
 <p className="text-[var(--color-text-muted)] text-xs truncate">{m.issue_description?.slice(0, 80)}{m.issue_description?.length > 80 ? '...' : ''}</p>
 </div>
 <div className="flex items-center gap-2 ml-2 flex-shrink-0">
 <Badge className={m.severity === 'critical' ? 'bg-red-500/20 text-red-400' : m.severity === 'medium' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}>{m.severity}</Badge>
 <button type="button" onClick={() => onRemoveMachine(idx)} className="text-red-400 hover:text-red-300 p-1"><X size={14} /></button>
 </div>
 </div>
 ))}
 <div className="border-t border-[var(--theme-border)] pt-3 mt-3">
 <p className="text-[var(--color-brand-blue)] text-xs font-medium">{t('faults.add_another_hint')}</p>
 </div>
 </div>
 )}

 {/* Machine Type dropdown — iter 216d2.
     Groups by the machine's display name (Lee's Feb-2026 fix:
     `equipment_type` was showing low-cardinality categories like
     "cardio (1)" instead of the actual "Treadmill (3)" label users
     expect). Falls back to `equipment_type` only when `name` is
     empty. The grouping key uses everything before the first comma
     so "Treadmill, Bay 3" and "Treadmill, Bay 4" collapse into
     one "Treadmill (2)" group — matching the Lite dialog behaviour. */}
 <div>
 <Label className="text-[var(--theme-text)]">{t('faults.machine_type')}</Label>
 <select
   value={selectedMachineType || ''}
   onChange={(ev) => { const v = ev.target.value; setSelectedMachineType(v); setIssueForm({...issueForm, serial_number: '', machine_type: v, supplier: ''}); }}
   onKeyDown={(e) => e.stopPropagation()}
   className="w-full bg-[var(--theme-surface)] border border-[var(--theme-border)] text-[var(--theme-text)] mt-2 h-10 px-3 rounded-md text-sm focus:outline-none focus:border-[color:var(--color-brand-cyan)]"
   data-testid="issue-type-select"
 >
 <option value="" disabled>Select machine type</option>
 {buildMachineTypeGroups(allEquipment).map(g => (
   <option key={g.type} value={g.type}>{g.label}</option>
 ))}
 {allEquipment.length === 0 && <option value="_none" disabled>{t('faults.no_equipment')}</option>}
 </select>
 </div>

 {/* Serial Number dropdown — iter 216d2: filters by the same derived
     name-key as the Machine Type dropdown, so picking "Treadmill"
     surfaces only treadmill serials. */}
 <div>
 <Label className="text-[var(--theme-text)]">{t('faults.serial_number')}</Label>
 {/* Iter 216h205 — Native input + datalist replaces the Radix Select
    for serial number. Solves the Radix Select-inside-Dialog portal
    conflict where clicking a Select option closed the Dialog. */}
 {/* Iter 216h205 retest2 — onKeyDown stopPropagation prevents Radix Dialog
   from intercepting keyboard events and closing the dialog. This is a known
   Radix issue (#3412) where inputs inside dialogs lose focus or cause the
   dialog to close when typing. */}
<input
   type="text"
   value={issueForm.serial_number || ''}
   onChange={(e) => {
     const val = e.target.value;
     const equip = allEquipment.find(eq => (eq.serial_number || eq.id) === val);
     if (equip) {
       setIssueForm({ ...issueForm, serial_number: equip.serial_number || equip.name, machine_type: selectedMachineType || equip.equipment_type || equip.name, supplier: equip.manufacturer || '' });
       fetchCoverage(equip.id);
       const serialKey = equip.serial_number || equip.name;
       const openFaults = issues.filter(i => i.status === 'open' && (i.serial_number === serialKey || i.serial_number === equip.name));
       if (openFaults.length > 0) setExistingFaultWarning({ faults: openFaults, machineName: equip.name || serialKey });
       else setExistingFaultWarning(null);
     } else {
       setIssueForm({ ...issueForm, serial_number: val });
     }
   }}
   onKeyDown={(e) => e.stopPropagation()}
   placeholder={selectedMachineType ? t('faults.select_serial') : t('faults.select_type_first')}
   list="issue-serial-datalist"
   autoComplete="off"
   className="w-full bg-[var(--theme-surface)] border border-[var(--theme-border)] text-[var(--theme-text)] mt-2 h-10 px-3 rounded-md text-sm focus:outline-none focus:border-[color:var(--color-brand-cyan)] disabled:opacity-60"
   disabled={!!issueForm.serial_unknown}
   data-testid="issue-serial-select"
 />
 <datalist id="issue-serial-datalist">
 {filterSerialsByGroup(allEquipment, selectedMachineType).map(e => (
   <option key={e.id} value={e.serial_number || e.id}>
     {e.name}{e.manufacturer ? ` (${e.manufacturer})` : ''}
   </option>
 ))}
 </datalist>
 {/* Iter 220dw — Serial-unknown escape hatch. Some machines have
     rubbed-off plates; previously customers had to either guess
     or abandon the fault. The checkbox + reason field stamps the
     case so the engineer's first-visit task captures the serial
     properly. Backend already accepts both fields (iter 220dt). */}
 <label className="flex items-center gap-2 mt-2 text-xs text-[var(--color-text-muted)] cursor-pointer select-none" data-testid="issue-serial-unknown-wrap">
   <input
     type="checkbox"
     checked={!!issueForm.serial_unknown}
     onChange={(e) => setIssueForm({ ...issueForm, serial_unknown: e.target.checked, serial_unknown_reason: e.target.checked ? (issueForm.serial_unknown_reason || 'rubbed_off') : '' })}
     data-testid="issue-serial-unknown"
   />
   Serial unknown / unreadable
 </label>
 {issueForm.serial_unknown && (
   <select
     value={issueForm.serial_unknown_reason || 'rubbed_off'}
     onChange={(e) => setIssueForm({ ...issueForm, serial_unknown_reason: e.target.value })}
     className="w-full bg-[var(--theme-surface)] border border-[var(--theme-border)] text-[var(--theme-text)] mt-1 h-9 px-3 rounded-md text-sm"
     data-testid="issue-serial-unknown-reason"
     onKeyDown={(e) => e.stopPropagation()}
   >
     <option value="rubbed_off">Plate rubbed off / unreadable</option>
     <option value="not_visible">Plate not visible / behind cladding</option>
     <option value="never_had_one">Machine has no serial plate</option>
   </select>
 )}
 </div>

 {/* Coverage Status — Iter 216h205 uses the shared CoverageBanner. */}
 {issueForm.serial_number && (
 <div data-testid="coverage-status-section">
 <CoverageBanner
  coverage={equipmentCoverage}
  loading={coverageLoading}
  testid="fault-coverage"
 />
 </div>
 )}

 {/* Existing fault warning */}
 {existingFaultWarning && issueForm.serial_number && (
 <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg space-y-3" data-testid="existing-fault-warning">
 <div className="flex items-start gap-2">
 <AlertCircle size={18} className="text-amber-400 flex-shrink-0 mt-0.5" />
 <div className="flex-1">
 <p className="text-amber-400 font-semibold text-sm">{existingFaultWarning.faults.length} open fault{existingFaultWarning.faults.length > 1 ? 's' : ''} already logged for {existingFaultWarning.machineName}</p>
 <div className="mt-2 space-y-2">
 {existingFaultWarning.faults.map((f, idx) => (
 <div key={idx} className="p-2 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded text-xs">
 <div className="flex items-center gap-2 mb-1">
 <Badge className={f.severity === 'critical' ? 'bg-red-500/20 text-red-400' : f.severity === 'medium' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}>{getSeverityLabel(f.severity)}</Badge>
 <span className="text-[var(--color-text-muted)]">{f.created_at ? new Date(f.created_at).toLocaleDateString() : ''}</span>
 </div>
 <p className="text-[var(--theme-text)]">{f.issue_description?.slice(0, 150)}{f.issue_description?.length > 150 ? '...' : ''}</p>
 </div>
 ))}
 </div>
 </div>
 </div>
 <div className="flex gap-2 justify-end">
 <button type="button" className="px-3 py-1.5 text-sm rounded-md border border-amber-500/30 text-amber-400 hover:bg-amber-500/10"
 onClick={() => { onResetDialog(); }} data-testid="cancel-duplicate-fault-btn">Cancel</button>
 <button type="button" className="px-3 py-1.5 text-sm rounded-md"
 onClick={() => { setExistingFaultWarning(null); }} data-testid="continue-log-fault-btn">Continue Anyway</button>
 </div>
 </div>
 )}

 <div>
 <Label htmlFor="issue_description" className="text-[var(--theme-text)]">{t('faults.issue_description')}</Label>
 <Textarea id="issue_description" value={issueForm.issue_description} onChange={(e) => setIssueForm({...issueForm, issue_description: e.target.value})}
 onKeyDown={(e) => e.stopPropagation()}
 required={faultMachines.length === 0} rows={4} placeholder={t('faults.description_placeholder')} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2" data-testid="issue-description-input" />
 </div>

 <div>
 <Label htmlFor="steps_taken" className="text-[var(--theme-text)]">{t('faults.steps_taken')}</Label>
 <p className="text-[var(--color-text-muted)] text-xs mb-1">{t('faults.steps_taken_hint')}</p>
 <Textarea id="steps_taken" value={issueForm.steps_taken} onChange={(e) => setIssueForm({...issueForm, steps_taken: e.target.value})}
 onKeyDown={(e) => e.stopPropagation()}
 rows={2} placeholder={t('faults.steps_taken_placeholder')} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="issue-steps-taken-input" />
 </div>

 <div>
 <Label htmlFor="severity" className="text-[var(--theme-text)]">{t('faults.severity')}</Label>
 <Select value={issueForm.severity} onValueChange={(val) => setIssueForm({...issueForm, severity: val})}>
 <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2" data-testid="issue-severity-select"><SelectValue /></SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] max-w-sm">
 <SelectItem value="operational_minor"><span className="font-medium text-green-400">Operational - Minor Issue</span></SelectItem>
 <SelectItem value="operational_fault"><span className="font-medium text-yellow-400">Operational - Fault Present</span></SelectItem>
 <SelectItem value="limited_use"><span className="font-medium text-orange-400">Limited Use</span></SelectItem>
 <SelectItem value="out_of_order"><span className="font-medium text-red-400">Out of Order</span></SelectItem>
 <SelectItem value="safety_critical"><span className="font-medium text-red-300">Safety Critical</span></SelectItem>
 </SelectContent>
 </Select>
 {issueForm.severity && (
 <div className={`mt-2 p-3 rounded-lg text-xs ${
 issueForm.severity === 'operational_minor' ? 'bg-green-500/10 border border-green-500/20 text-green-300' :
 issueForm.severity === 'operational_fault' ? 'bg-yellow-500/10 border border-yellow-500/20 text-yellow-300' :
 issueForm.severity === 'limited_use' ? 'bg-orange-500/10 border border-orange-500/20 text-orange-300' :
 issueForm.severity === 'safety_critical' ? 'bg-red-700/10 border border-red-700/20 text-red-300' :
 'bg-red-500/10 border border-red-500/20 text-red-300'
 }`} data-testid="severity-guidance">
 {issueForm.severity === 'operational_minor' && <><strong>Machine is fully usable</strong> — minor fault or annoyance.<br/>Examples: Cosmetic damage, slight noise, loose trim, worn decals</>}
 {issueForm.severity === 'operational_fault' && <><strong>Machine works but not as intended</strong> — could worsen if ignored.<br/>Examples: Resistance not accurate, console intermittent, belt slipping slightly, unusual noise under load</>}
 {issueForm.severity === 'limited_use' && <><strong>Machine partially usable but restricted</strong> — some functions unavailable.<br/>Examples: Speed limited, incline not working, one program available, reduced weight stack</>}
 {issueForm.severity === 'out_of_order' && <><strong>Cannot be used</strong> — must be taken out of service.<br/>Examples: Will not power on, unsafe to use, major mechanical failure</>}
 {issueForm.severity === 'safety_critical' && <><strong>Immediate safety hazard</strong> — isolate the machine immediately.<br/>Examples: Exposed wiring, structural failure, risk of injury, fire hazard</>}
 </div>
 )}
 </div>

 {/* Fault Code — powers trend analysis across gyms/parts */}
 <div data-testid="issue-fault-code-wrapper">
 <FaultCodeSelect
 API={API}
 value={issueForm.fault_code}
 onChange={(code) => setIssueForm({ ...issueForm, fault_code: code })}
 />
 <SaveAsTemplateButton
 API={API}
 issueForm={issueForm}
 privileged={canManageOrgTemplates}
 />
 </div>

{/* Iter 220dw — Job Type. Drives the engineer Summary chip + the
    per-machine custom-field auto-load. "Repair" is the default
    because the legacy Log-a-Fault flow only ever meant "fix it". */}
<div data-testid="issue-case-type-wrapper">
<Label htmlFor="case_type" className="text-[var(--theme-text)]">{t('faults.job_type', 'Job type')}</Label>
<select
  id="case_type"
  value={issueForm.case_type || 'repair'}
  onChange={(e) => setIssueForm({ ...issueForm, case_type: e.target.value })}
  onKeyDown={(e) => e.stopPropagation()}
  className="w-full bg-[var(--theme-surface)] border border-[var(--theme-border)] text-[var(--theme-text)] mt-2 h-10 px-3 rounded-md text-sm focus:outline-none focus:border-[color:var(--color-brand-cyan)]"
  data-testid="issue-case-type-select"
>
  <option value="repair">Repair</option>
  <option value="ppm">Preventative Maintenance Service</option>
  <option value="install">Installation</option>
  <option value="inspection">Safety / compliance inspection</option>
  <option value="callout">Emergency callout</option>
  <option value="audit">Asset audit</option>
</select>
<p className="text-[var(--color-text-muted)] text-[11px] mt-1">
  Helps us send the right engineer with the right kit + pre-load
  any machine-specific checklist fields.
</p>
</div>


 {/* Upload */}
 <div>
 <Label className="text-[var(--theme-text)]">{t('faults.upload_label')}</Label>
 <p className="text-[var(--color-text-muted)] text-xs mb-2">{t('faults.upload_hint')}</p>
 <label className="cursor-pointer">
 <input type="file" className="hidden" accept="image/*,video/*" multiple
 onChange={(e) => { const files = Array.from(e.target.files || []); setIssueMedia(prev => [...prev, ...files]); e.target.value = ''; }}
 data-testid="issue-media-input" />
 <div className="border-2 border-dashed border-[var(--theme-border)] rounded-lg p-4 text-center hover:border-[rgb(var(--rgb-brand-blue)/0.3)] transition-colors">
 <Upload size={20} className="mx-auto mb-1 text-[var(--color-text-muted)]" />
 <span className="text-[var(--color-text-muted)] text-sm">{t('faults.click_upload')}</span>
 </div>
 </label>
 {issueMedia.length > 0 && (
 <div className="flex flex-wrap gap-2 mt-2">
 {issueMedia.map((file, idx) => (
 <div key={idx} className="flex items-center gap-2 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded px-2 py-1">
 {file.type?.startsWith('video/') ? <Video size={14} className="text-[var(--color-brand-blue)]" /> : <ImageIcon size={14} className="text-[var(--color-brand-blue)]" />}
 <span className="text-[var(--theme-text)] text-xs truncate max-w-[120px]">{file.name}</span>
 <button type="button" onClick={() => setIssueMedia(issueMedia.filter((_, i) => i !== idx))} className="text-red-400 hover:text-red-300"><X size={12} /></button>
 </div>
 ))}
 </div>
 )}
 </div>

 {/* Multi-machine buttons */}
 <div className="flex gap-2">
 {issueForm.serial_number && issueForm.issue_description && (
 <Button type="button" variant="outline" onClick={onAddMachine} className="flex-1 border-[var(--theme-border)] text-[var(--color-text-muted)] hover:bg-white/5" data-testid="add-another-machine-btn">
 <Plus size={16} className="mr-1" /> {t('faults.add_another')}
 </Button>
 )}
 <Button type="submit" disabled={issueLoading || (!issueForm.serial_number && faultMachines.length === 0)} className="flex-1" data-testid="issue-submit-btn">
 {issueLoading ? (
 <span className="flex items-center gap-2">
 <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
 {faultMachines.length > 0 ? t('faults.running_triage_multi', { count: faultMachines.length + (issueForm.serial_number ? 1 : 0) }) : t('faults.running_triage')}
 </span>
 ) : (faultMachines.length > 0 ? t('faults.submit_triage_multi', { count: faultMachines.length + (issueForm.serial_number && issueForm.issue_description ? 1 : 0) }) : t('faults.submit_triage'))}
 </Button>
 </div>
 {allEquipment.length === 0 && <p className="text-yellow-400 text-xs text-center">{t('faults.no_equipment_hint')}</p>}
 </form>
 )}

 {/* Step 2: AI Triage Results */}
 {issueStep === 'triage' && triageResult && (
 <div className="space-y-4" data-testid="triage-results">
 {faultMachines.length > 1 && (
 <div className="flex gap-1 overflow-x-auto pb-2" data-testid="machine-tabs">
 {faultMachines.map((m, idx) => (
 <button key={idx} onClick={() => { setActiveMachineIdx(idx); setTriageResult(machineTriageResults[idx]); setSelectedFixStep(null); setResolutionNote(''); }}
 className={`px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-all ${idx === activeMachineIdx ? 'bg-[var(--color-brand-blue)] text-[var(--theme-text)]' : idx < activeMachineIdx ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-[var(--theme-surface)] text-[var(--color-text-muted)] border border-[var(--theme-border)]'}`}
 data-testid={`machine-tab-${idx}`}>{idx < activeMachineIdx ? '\u2713 ' : ''}{m.machine_type}</button>
 ))}
 </div>
 )}

 {faultMachines[activeMachineIdx] && (
 <div className="p-3 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg">
 <div className="flex items-center justify-between">
 <div>
 <p className="text-[var(--theme-text)] text-sm font-medium">{faultMachines[activeMachineIdx].machine_type} — {faultMachines[activeMachineIdx].serial_number}</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-0.5">{faultMachines[activeMachineIdx].issue_description?.slice(0, 120)}</p>
 </div>
 <Badge className={faultMachines[activeMachineIdx].severity === 'critical' ? 'bg-red-500/20 text-red-400' : faultMachines[activeMachineIdx].severity === 'medium' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}>{faultMachines[activeMachineIdx].severity}</Badge>
 </div>
 </div>
 )}

 {faultMachines[activeMachineIdx]?.steps_taken && (
 <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
 <p className="text-amber-400 text-xs font-medium mb-1">{t('triage.steps_acknowledged')}</p>
 <p className="text-[var(--color-text-muted)] text-sm">{faultMachines[activeMachineIdx].steps_taken}</p>
 </div>
 )}

 <div className="p-4 bg-[rgb(var(--rgb-brand-blue)/0.1)] border border-[rgb(var(--rgb-brand-blue)/0.3)] rounded-lg">
 <h4 className="text-[var(--color-brand-blue)] text-sm font-semibold mb-1">{t('triage.ai_diagnosis_label')}</h4>
 <p className="text-[var(--theme-text)]">{triageResult.diagnosis}</p>
 </div>

 <div className="flex items-center gap-3 flex-wrap">
 <Badge className={triageResult.can_fix_onsite ? 'bg-green-500/20 text-green-400 text-sm py-1 px-3' : 'bg-orange-500/20 text-orange-400 text-sm py-1 px-3'} data-testid="triage-fix-badge">
 {triageResult.can_fix_onsite ? t('triage.can_fix_badge') : t('triage.engineer_badge')}
 </Badge>
 {triageResult.estimated_time && <Badge className="bg-white/10 text-[var(--theme-text)] text-sm py-1 px-3 dark:bg-zinc-900">{t('triage.est_time', { time: triageResult.estimated_time })}</Badge>}
 {triageResult.fault_code && (
 <Badge
 className="bg-amber-500/20 text-amber-300 text-sm py-1 px-3 flex items-center gap-1"
 data-testid="triage-fault-code-badge"
 title="AI-suggested fault code for trend reporting"
 >
 <span className="text-xs opacity-80">AI fault code</span>
 <span className="font-semibold">{triageResult.fault_code}</span>
 </Badge>
 )}
 </div>

 <div>
 <h4 className="text-[var(--theme-text)] font-semibold mb-3">{t('triage.repair_steps')}</h4>
 <div className="space-y-3">
 {(triageResult.repair_steps || []).map((step, idx) => (
 <div key={idx} className="flex gap-3 p-3 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg" data-testid={`repair-step-${idx}`}>
 <div className="w-8 h-8 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center flex-shrink-0 mt-0.5">
 <span className="text-[var(--color-brand-blue)] text-sm font-bold">{step.step || idx + 1}</span>
 </div>
 <div className="flex-1">
 <p className="text-[var(--theme-text)] font-medium">{step.title}</p>
 <p className="text-[var(--color-text-muted)] text-sm mt-1">{step.instruction}</p>
 {step.safety_note && <p className="text-yellow-400 text-xs mt-2 flex items-center gap-1"><AlertCircle size={12} /> {step.safety_note}</p>}
 </div>
 </div>
 ))}
 </div>
 </div>

 {triageResult.tools_needed && triageResult.tools_needed.length > 0 && (
 <div className="p-3 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg">
 <p className="text-[var(--color-text-muted)] text-sm"><span className="text-[var(--theme-text)] font-medium">{t('triage.tools_needed_label')}: </span>{triageResult.tools_needed.join(', ')}</p>
 </div>
 )}

 {!triageResult.can_fix_onsite && triageResult.engineer_reason && (
 <div className="p-3 bg-orange-500/10 border border-orange-500/30 rounded-lg">
 <p className="text-orange-400 text-sm"><span className="font-medium">Engineer recommended: </span>{triageResult.engineer_reason}</p>
 </div>
 )}

 <div className="border-t border-[var(--theme-border)] pt-4 space-y-3">
 {equipmentCoverage && (
 <div className={`p-3 rounded-lg border flex items-center gap-2 ${equipmentCoverage.covered ? 'bg-green-500/10 border-green-500/20' : 'bg-amber-500/10 border-amber-500/20'}`} data-testid="triage-coverage-banner">
 <Badge className={equipmentCoverage.covered ? 'bg-green-500/20 text-green-400' : 'bg-amber-500/20 text-amber-400'}>
 {equipmentCoverage.covered ? (equipmentCoverage.type === 'warranty' ? t('triage.warranty_label') : t('triage.contract_label')) : t('triage.coverage_not_covered')}
 </Badge>
 <span className={`text-sm ${equipmentCoverage.covered ? 'text-[var(--theme-text)]' : 'text-amber-400'}`}>
 {equipmentCoverage.covered ? equipmentCoverage.label : t('triage.no_coverage_callout')}
 </span>
 </div>
 )}

 <p className="text-[var(--theme-text)] font-semibold">{t('triage.have_you_fixed')}</p>
 <Button onClick={() => setIssueStep('resolution')} className="w-full bg-green-600 hover:bg-green-700 text-[var(--theme-text)] py-3" data-testid="fixed-it-btn">
 <CheckCircle size={18} className="mr-2" /> {t('triage.yes_fixed')}
 </Button>
 <Button onClick={onEngineerClick} disabled={issueLoading} variant="outline" className="w-full border-orange-500/50 text-orange-400 hover:bg-orange-500/10 py-3" data-testid="log-engineer-btn">
 <Wrench size={18} className="mr-2" /> {issueLoading ? t('triage.logging') : t('triage.no_log_engineer')}
 </Button>
 </div>
 </div>
 )}

 {/* Step 3: Self-fix confirmation */}
 {issueStep === 'resolution' && (
 <div className="space-y-4" data-testid="resolution-step">
 <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg text-center">
 <CheckCircle size={40} className="mx-auto mb-2 text-green-400" />
 <p className="text-green-400 font-semibold">{t('triage.great_work')}</p>
 </div>

 {triageResult?.repair_steps && triageResult.repair_steps.length > 0 && (
 <div>
 <Label className="text-[var(--theme-text)] font-medium">{t('triage.which_step')}</Label>
 <p className="text-[var(--color-text-muted)] text-xs mb-3">{t('triage.which_step_hint')}</p>
 <div className="space-y-2">
 {triageResult.repair_steps.map((step, idx) => (
 <button key={idx} type="button" onClick={() => setSelectedFixStep(idx)}
 className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${selectedFixStep === idx ? 'border-green-500 bg-green-500/10' : 'border-[var(--theme-border)] bg-[var(--theme-surface)] hover:border-[var(--theme-border)]'}`}
 data-testid={`fix-step-option-${idx}`}>
 <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${selectedFixStep === idx ? 'border-green-500 bg-green-500' : 'border-white/30'}`}>
 {selectedFixStep === idx && <CheckCircle size={12} className="text-[var(--theme-text)]" />}
 </div>
 <div>
 <p className="text-[var(--theme-text)] text-sm font-medium">{step.title}</p>
 <p className="text-[var(--color-text-muted)] text-xs">{step.instruction?.substring(0, 80)}{step.instruction?.length > 80 ? '...' : ''}</p>
 </div>
 </button>
 ))}
 <button type="button" onClick={() => setSelectedFixStep(-1)}
 className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${selectedFixStep === -1 ? 'border-green-500 bg-green-500/10' : 'border-[var(--theme-border)] bg-[var(--theme-surface)] hover:border-[var(--theme-border)]'}`}
 data-testid="fix-step-option-other">
 <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${selectedFixStep === -1 ? 'border-green-500 bg-green-500' : 'border-white/30'}`}>
 {selectedFixStep === -1 && <CheckCircle size={12} className="text-[var(--theme-text)]" />}
 </div>
 <p className="text-[var(--theme-text)] text-sm">{t('triage.something_else')}</p>
 </button>
 </div>
 </div>
 )}

 <div>
 <Label className="text-[var(--theme-text)]">{t('triage.additional_notes')}</Label>
 <Textarea value={resolutionNote} onChange={(e) => setResolutionNote(e.target.value)} rows={2}
 placeholder={t('triage.notes_placeholder')} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2" data-testid="resolution-note-input" />
 <p className="text-[var(--color-text-muted)] text-xs mt-1">{t('triage.knowledge_hint')}</p>
 </div>

 <Button onClick={() => onResolution('self_fix')} disabled={issueLoading} className="w-full bg-green-600 hover:bg-green-700 text-[var(--theme-text)] py-3" data-testid="confirm-fixed-btn">
 {issueLoading ? t('triage.saving') : t('triage.confirm_close')}
 </Button>
 <Button variant="outline" className="w-full border-[var(--theme-border)] text-[var(--color-text-muted)]" onClick={() => setIssueStep('triage')}>{t('triage.back_to_triage')}</Button>
 </div>
 )}
 </DialogContent>
 </Dialog>

 {/* PO Required Prompt Dialog */}
 <Dialog open={showPOPrompt} onOpenChange={(open) => { if (!open) setShowPOPrompt(false); }}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] max-w-lg max-h-[90vh] overflow-y-auto" data-testid="po-prompt-dialog">
 <DialogHeader><DialogTitle className="text-[var(--theme-text)]" data-testid="po-prompt-title">{t('po.required')}</DialogTitle></DialogHeader>
 <div className="space-y-4">
 <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg" data-testid="no-coverage-warning">
 <p className="text-amber-400 text-sm font-medium flex items-center gap-2"><AlertCircle size={16} /> {t('po.not_covered_warning')}</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">{t('po.not_covered_desc')}</p>
 </div>
 <div><Label className="text-[var(--theme-text)]">PO Number (optional - auto-generated if blank)</Label><Input value={poForm.po_number} onChange={(e) => setPOForm({...poForm, po_number: e.target.value})} placeholder="e.g. PO-2026-001" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="po-number-input" /></div>
 <div><Label className="text-[var(--theme-text)]">Supplier Name</Label><Input value={poForm.supplier_name} onChange={(e) => setPOForm({...poForm, supplier_name: e.target.value})} placeholder="Supplier / manufacturer name" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="po-supplier-name" /></div>
 <div><Label className="text-[var(--theme-text)]">Supplier Email</Label><Input type="email" value={poForm.supplier_email} onChange={(e) => setPOForm({...poForm, supplier_email: e.target.value})} placeholder="supplier@example.com" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="po-supplier-email" /></div>
 <div><Label className="text-[var(--theme-text)]">Delivery / Site Address</Label><Input value={poForm.delivery_address} onChange={(e) => setPOForm({...poForm, delivery_address: e.target.value})} placeholder="Gym address for engineer visit" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="po-delivery-address" /></div>
 <div>
 <Label className="text-[var(--theme-text)]">{t('po.callout_cost')}</Label>
 <div className="flex items-center gap-2 mt-1">
 <span className="text-[var(--color-text-muted)]">{"\u00A3"}</span>
 <Input type="number" step="0.01" min="0" value={poForm.items[0]?.unit_price || ''} onChange={(e) => setPOForm({...poForm, items: [{ ...poForm.items[0], unit_price: parseFloat(e.target.value) || 0 }]})} placeholder="0.00" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]" data-testid="po-callout-cost" />
 <span className="text-[var(--color-text-muted)] text-sm">{t('po.vat')}</span>
 </div>
 </div>
 <div><Label className="text-[var(--theme-text)]">{t('po.notes')} ({t('diagnosis.model_label').split('(')[1]?.split(')')[0] || 'optional'})</Label><Textarea value={poForm.notes} onChange={(e) => setPOForm({...poForm, notes: e.target.value})} rows={2} placeholder={t('po.notes_placeholder')} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="po-notes" /></div>
 <div className="flex gap-3 pt-2">
 <Button variant="outline" onClick={onSkipPOAndLog} className="flex-1 border-[var(--theme-border)] text-[var(--color-text-muted)]" data-testid="skip-po-btn">{t('po.skip_log')}</Button>
 <Button onClick={onCreatePOAndLog} disabled={poCreating} className="flex-1" data-testid="create-po-btn">{poCreating ? t('po.creating') : t('po.create_log')}</Button>
 </div>
 </div>
 </DialogContent>
 </Dialog>

 {/* Fault Logged Success Dialog */}
 <Dialog open={showFaultSuccess} onOpenChange={setShowFaultSuccess}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] max-w-md" data-testid="fault-success-dialog">
   <FaultSuccessBody
     faultSuccessType={faultSuccessType}
     lastIssue={lastIssue}
     onClose={() => { setShowFaultSuccess(false); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
     API={API}
     t={t}
   />
 </DialogContent>
 </Dialog>

 {/* Service Request Dialog */}
 <Dialog open={showServiceDialog} onOpenChange={setShowServiceDialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]" data-testid="service-dialog">
 <DialogHeader><DialogTitle className="text-[var(--theme-text)]" data-testid="service-dialog-title">{t('service.title')}</DialogTitle></DialogHeader>
 <form onSubmit={onServiceSubmit} className="space-y-4">
 <div><Label htmlFor="service_machine_type" className="text-[var(--theme-text)]">{t('service.machine_type')}</Label><Input id="service_machine_type" value={serviceForm.machine_type} onChange={(e) => setServiceForm({...serviceForm, machine_type: e.target.value})} required className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2" data-testid="service-machine-input" /></div>
 <div><Label htmlFor="issue_summary" className="text-[var(--theme-text)]">{t('service.issue_summary')}</Label><Textarea id="issue_summary" value={serviceForm.issue_summary} onChange={(e) => setServiceForm({...serviceForm, issue_summary: e.target.value})} required rows={3} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2" data-testid="service-issue-input" /></div>
 <div><Label htmlFor="site_info" className="text-[var(--theme-text)]">{t('service.site_info')}</Label><Input id="site_info" value={serviceForm.site_info} onChange={(e) => setServiceForm({...serviceForm, site_info: e.target.value})} required placeholder={t('service.site_placeholder')} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2" data-testid="service-site-input" /></div>
 <div><Label htmlFor="contact_phone" className="text-[var(--theme-text)]">Contact Phone</Label><Input id="contact_phone" value={serviceForm.contact_phone} onChange={(e) => setServiceForm({...serviceForm, contact_phone: e.target.value})} required placeholder="+44 20 1234 5678" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-2" data-testid="service-phone-input" /></div>
 <Button type="submit" className="w-full" data-testid="service-submit-btn">{t('service.submit')}</Button>
 </form>
 </DialogContent>
 </Dialog>
 </>
 );
};

export default FaultDialogs;


/* ─────────────────── Fault success + triage learning ─────────────────── */

function FaultSuccessBody({ faultSuccessType, lastIssue, onClose, API, t }) {
  const [step, setStep] = useState('success');   // 'success' | 'tried' | 'thanks'
  const [tried, setTried] = useState([]);        // selected step titles
  const [other, setOther] = useState('');
  const [outcome, setOutcome] = useState('');    // worked | no_change | made_worse
  const [saving, setSaving] = useState(false);

  const triageSteps = lastIssue?.triage_steps || [];
  const haveSuggestions = triageSteps.length > 0;

  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const post = async (attempted) => {
    if (!lastIssue?.id) { onClose(); return; }
    setSaving(true);
    try {
      await axios.post(
        `${API}/issues/${lastIssue.id}/triage-feedback`,
        { attempted, tried_steps: tried, tried_other: other.trim(), outcome: outcome || null },
        { headers },
      );
    } catch (_) {
      // Telemetry — never block the close flow.
    }
    setSaving(false);
    setStep('thanks');
  };

  const toggle = (title) => {
    setTried((prev) => prev.includes(title) ? prev.filter((x) => x !== title) : [...prev, title]);
  };

  if (step === 'success') {
    return (
      <div className="flex flex-col items-center text-center py-4">
        <div className="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center mb-4">
          <CheckCircle size={40} className="text-green-400" />
        </div>
        <h2 className="text-2xl font-bold text-[var(--theme-text)] mb-2" data-testid="fault-success-title">
          {faultSuccessType === 'self_fix' ? t('resolution.self_fix_title') : t('resolution.engineer_title')}
        </h2>
        <p className="text-[var(--color-text-muted)] mb-2">
          {faultSuccessType === 'self_fix' ? t('resolution.self_fix_msg') : t('resolution.engineer_msg')}
        </p>
        <p className="text-sm text-[var(--color-text-muted)] mb-5 mt-3">
          Quick question — did you try anything before logging this fault?
        </p>
        <div className="flex gap-3 w-full">
          <Button
            variant="outline"
            className="flex-1 border-[var(--theme-border)] text-[var(--theme-text)] hover:bg-white/5"
            onClick={() => post(false)}
            disabled={saving}
            data-testid="triage-feedback-no"
          >
            No, just logged it
          </Button>
          <Button
            className="flex-1 bg-[var(--color-brand-cyan)] text-zinc-900 hover:brightness-95"
            onClick={() => setStep('tried')}
            data-testid="triage-feedback-yes"
          >
            Yes, I tried things
          </Button>
        </div>
      </div>
    );
  }

  if (step === 'tried') {
    return (
      <div className="py-2">
        <h3 className="text-lg font-bold text-[var(--theme-text)] mb-1">Which fixes did you try?</h3>
        <p className="text-xs text-[var(--color-text-muted)] mb-3">This trains the AI brain so future jobs get smarter.</p>
        {haveSuggestions ? (
          <div className="space-y-2 mb-3" data-testid="triage-feedback-suggestions">
            {triageSteps.map((title, i) => (
              <label key={i} className="flex items-start gap-2 p-2 rounded-md border border-[var(--theme-border)] hover:bg-white/5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={tried.includes(title)}
                  onChange={() => toggle(title)}
                  className="mt-1 rounded"
                  data-testid={`triage-feedback-step-${i}`}
                />
                <span className="text-sm text-[var(--theme-text)]">{title}</span>
              </label>
            ))}
          </div>
        ) : (
          <p className="text-xs text-[var(--color-text-muted)] mb-3 italic">No AI triage steps were generated for this fault.</p>
        )}
        <div className="mb-3">
          <Label className="text-xs text-[var(--color-text-muted)]">Anything else?</Label>
          <Textarea
            value={other}
            onChange={(e) => setOther(e.target.value)}
            placeholder="e.g. I cycled the power, wiggled the cable, replaced the consumable…"
            rows={2}
            className="bg-white/5 border-[var(--theme-border)] text-[var(--theme-text)] text-sm mt-1"
            data-testid="triage-feedback-other"
          />
        </div>
        <div className="mb-3">
          <Label className="text-xs text-[var(--color-text-muted)]">Outcome</Label>
          <div className="flex gap-2 mt-1">
            {[
              { v: 'worked',     label: 'It worked' },
              { v: 'no_change',  label: 'No change' },
              { v: 'made_worse', label: 'Made it worse' },
            ].map((o) => (
              <button
                key={o.v}
                type="button"
                onClick={() => setOutcome(o.v)}
                className={`flex-1 px-2 py-1.5 text-xs rounded border ${outcome === o.v ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.1)] text-[var(--color-brand-cyan)]' : 'border-[var(--theme-border)] text-[var(--color-text-muted)] hover:bg-white/5'}`}
                data-testid={`triage-feedback-outcome-${o.v}`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-2 pt-3 border-t border-[var(--theme-border)]">
          <Button
            variant="outline"
            className="flex-1 border-[var(--theme-border)] text-[var(--theme-text)] hover:bg-white/5"
            onClick={() => post(true)}
            disabled={saving}
            data-testid="triage-feedback-skip"
          >
            Skip
          </Button>
          <Button
            className="flex-1 bg-[var(--color-brand-cyan)] text-zinc-900 hover:brightness-95"
            onClick={() => post(true)}
            disabled={saving || (tried.length === 0 && !other.trim())}
            data-testid="triage-feedback-submit"
          >
            {saving ? 'Saving…' : 'Submit feedback'}
          </Button>
        </div>
      </div>
    );
  }

  // step === 'thanks'
  return (
    <div className="flex flex-col items-center text-center py-6">
      <div className="w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center mb-3">
        <CheckCircle size={32} className="text-emerald-400" />
      </div>
      <h3 className="text-lg font-bold text-[var(--theme-text)] mb-1">Thanks!</h3>
      <p className="text-sm text-[var(--color-text-muted)] mb-5">Feedback captured — the AI brain just got smarter.</p>
      <Button onClick={onClose} className="px-8" data-testid="triage-feedback-done">Done</Button>
    </div>
  );
}
