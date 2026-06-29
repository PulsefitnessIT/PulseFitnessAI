import { useState, useEffect } from 'react';
import axios from 'axios';
import { queuedMutation } from '@/utils/queuedMutation';

import { notify } from '@/components/notifications';
const EMPTY_ISSUE_FORM = {
  serial_number: '', machine_type: '', issue_description: '',
  severity: 'operational_minor', supplier: '', steps_taken: '',
  fault_code: null,
  // Iter 220dw — Customer-portal Log-a-Fault now captures the
  // job type + serial-unknown escape hatch. Defaults match the
  // backend schema (iter 220dt) so existing flows stay identical
  // when the customer doesn't change them.
  case_type: 'repair',
  serial_unknown: false,
  serial_unknown_reason: '',
};

const EMPTY_PO_FORM = {
  po_number: '', supplier_name: '', supplier_email: '',
  delivery_address: '', notes: '',
  items: [{ description: 'Engineer callout - fault repair', quantity: 1, unit_price: 0 }],
};

const parseAiTriage = (issue) => {
  if (!issue.ai_triage || issue.ai_triage_parsed) return issue;
  try {
    let cleaned = issue.ai_triage.trim();
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.split('\n').slice(1).join('\n').replace(/```$/, '').trim();
    }
    issue.ai_triage_parsed = JSON.parse(cleaned);
  } catch {
    // swallow
  }
  return issue;
};

/**
 * Encapsulates the entire multi-machine fault-logging workflow:
 * per-machine form state, AI triage round-trip, self-fix vs engineer resolution,
 * PO prompt for out-of-coverage faults, media attachments, and status updates.
 */
const useIssueWorkflow = ({ API, i18n, t, setIssues, loadData, allEquipment, user }) => {
  const [showIssueDialog, setShowIssueDialog] = useState(false);
  const [issueLoading, setIssueLoading] = useState(false);
  const [issueStep, setIssueStep] = useState('form'); // 'form' | 'triage' | 'resolution'
  const [triageResult, setTriageResult] = useState(null);
  const [resolutionNote, setResolutionNote] = useState('');
  const [issueForm, setIssueForm] = useState(EMPTY_ISSUE_FORM);
  const [faultMachines, setFaultMachines] = useState([]);
  // Count of machines actually being triaged on the current submit. Captured
  // BEFORE setFaultMachines(machines) folds the active form into the list, so
  // the "Running AI Triage (N machines)" label can't double-count the
  // in-progress machine (Jun 2026 bug: 1 machine showed as "2 machines").
  const [submitCount, setSubmitCount] = useState(0);
  const [activeMachineIdx, setActiveMachineIdx] = useState(0);
  const [machineTriageResults, setMachineTriageResults] = useState([]);
  // Iter 216d — when the user is logging multiple machines, generate
  // ONE job_id at the start of the workflow and stamp every per-machine
  // POST with it so the fault list groups them under one expandable
  // parent and the supplier-email path bundles them into one message.
  // Lazy-initialised the first time we submit a machine on a multi-
  // machine workflow.
  const [currentJobId, setCurrentJobId] = useState(null);
  // Site Staff Shared Login — the shared kiosk account must pick "who is
  // logging this fault?" before submit. Storing reporter_staff_id + site_id
  // on issueForm means every per-machine payload (which spreads the form)
  // carries the reporter automatically.
  const isSharedLogin = !!user?.is_shared_site_login || user?.role === 'site_staff';
  const reporterSiteId = user?.site_id || (user?.allowed_site_ids || [])[0] || null;
  const [siteStaff, setSiteStaff] = useState([]);
  const [siteStaffSettings, setSiteStaffSettings] = useState({});
  const [reporterIsOther, setReporterIsOther] = useState(false);
  useEffect(() => {
    if (!isSharedLogin || !reporterSiteId) return;
    const token = localStorage.getItem('token');
    axios.get(`${API}/site-staff/active?site_id=${reporterSiteId}`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => { setSiteStaff(r.data.staff || []); setSiteStaffSettings(r.data.settings || {}); })
      .catch(() => setSiteStaff([]));
    setIssueForm((f) => ({ ...f, site_id: reporterSiteId }));
  }, [isSharedLogin, reporterSiteId, API]);
  const setReporterStaffId = (id) => {
    if (id === '__other__') {
      setReporterIsOther(true);
      setIssueForm((f) => ({ ...f, reporter_staff_id: '', site_id: reporterSiteId }));
    } else {
      setReporterIsOther(false);
      setIssueForm((f) => ({ ...f, reporter_staff_id: id, site_id: reporterSiteId,
        reporter_name: '', reporter_email: '', reporter_phone: '', reporter_job_title: '' }));
    }
  };
  const setReporterPin = (pin) => setIssueForm((f) => ({ ...f, reporter_pin: pin }));
  const setReporterOther = (o) => setIssueForm((f) => ({ ...f,
    reporter_name: o.name, reporter_job_title: o.job_title, reporter_email: o.email, reporter_phone: o.phone }));
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [issueMedia, setIssueMedia] = useState([]);
  const [showFaultSuccess, setShowFaultSuccess] = useState(false);
  const [faultSuccessType, setFaultSuccessType] = useState('self_fix');
  const [lastIssue, setLastIssue] = useState(null);    // {id, triage_steps:[]}
  const [existingFaultWarning, setExistingFaultWarning] = useState(null);
  const [selectedMachineType, setSelectedMachineType] = useState('');
  const [selectedFixStep, setSelectedFixStep] = useState(null);

  // Coverage + PO state
  const [equipmentCoverage, setEquipmentCoverage] = useState(null);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [showPOPrompt, setShowPOPrompt] = useState(false);
  const [poForm, setPOForm] = useState(EMPTY_PO_FORM);
  const [poCreating, setPOCreating] = useState(false);

  // Service request dialog
  const [showServiceDialog, setShowServiceDialog] = useState(false);
  const [serviceForm, setServiceForm] = useState({
    machine_type: '', issue_summary: '', site_info: '',
    contact_name: user?.full_name || '',
    contact_email: user?.email || '',
    contact_phone: '',
  });

  const resetIssueDialog = () => {
    setShowIssueDialog(false);
    setIssueStep('form');
    setTriageResult(null);
    setResolutionNote('');
    setSelectedFixStep(null);
    setIssueForm(EMPTY_ISSUE_FORM);
    setSelectedMachineType('');
    setIssueMedia([]);
    setEquipmentCoverage(null);
    setShowPOPrompt(false);
    setFaultMachines([]);
    setActiveMachineIdx(0);
    setSubmitCount(0);
    setMachineTriageResults([]);
    setCurrentJobId(null);
    setExistingFaultWarning(null);
  };

  const addMachineToFault = () => {
    if (!issueForm.serial_number || !issueForm.issue_description) {
      notify.error(t('faults.add_machine_error'));
      return;
    }
    const isDuplicate = faultMachines.some(
      m => m.serial_number === issueForm.serial_number && m.issue_description === issueForm.issue_description
    );
    if (isDuplicate) {
      notify.error(t('faults.duplicate_machine_error') || 'This machine with the same issue has already been added');
      return;
    }
    const machine = { ...issueForm, media: [...issueMedia] };
    setFaultMachines(prev => [...prev, machine]);
    setIssueForm(EMPTY_ISSUE_FORM);
    setSelectedMachineType('');
    setIssueMedia([]);
    setEquipmentCoverage(null);
    notify.success(t('faults.machine_added', { name: machine.machine_type }));
  };

  const removeMachineFromFault = (idx) => {
    setFaultMachines(prev => prev.filter((_, i) => i !== idx));
  };

  const handleIssueSubmit = async (e) => {
    e.preventDefault();
    if (isSharedLogin && !issueForm.reporter_staff_id && !reporterIsOther) {
      notify.error(siteStaff.length === 0
        ? 'No site staff have been added yet. Please contact your site manager to add staff before logging a fault.'
        : 'Please select the staff member logging this fault before submitting.');
      return;
    }
    if (isSharedLogin && reporterIsOther && (!issueForm.reporter_name || !issueForm.reporter_email || !issueForm.reporter_phone)) {
      notify.error('Please enter the name, email and phone for the staff member logging this fault.');
      return;
    }
    let machines = [...faultMachines];
    if (issueForm.serial_number && issueForm.issue_description) {
      const isDuplicate = faultMachines.some(
        m => m.serial_number === issueForm.serial_number && m.issue_description === issueForm.issue_description
      );
      if (!isDuplicate) machines.push({ ...issueForm, media: [...issueMedia] });
    }
    if (machines.length === 0) {
      notify.error(t('faults.add_machine_min'));
      return;
    }

    setSubmitCount(machines.length);
    setFaultMachines(machines);
    setIssueLoading(true);
    try {
      const token = localStorage.getItem('token');
      const triagePromises = machines.map(m =>
        axios.post(`${API}/issues/triage`, { ...m, language: i18n.language?.substring(0, 2) || 'en' }, {
          headers: { Authorization: `Bearer ${token}` },
        }).then(res => res.data).catch(() => ({
          diagnosis: 'AI triage unavailable for this machine',
          can_fix_onsite: null,
          repair_steps: [],
          raw_triage: '',
        }))
      );
      const results = await Promise.all(triagePromises);

      // Back-fill the AI-suggested fault_code onto each machine (only if user didn't pick one)
      machines = machines.map((m, idx) => {
        const suggested = results[idx]?.fault_code;
        if (suggested && !m.fault_code) return { ...m, fault_code: suggested };
        return m;
      });
      setFaultMachines(machines);
      // Also back-fill the active machine onto the shared issueForm so the fault-code dropdown reflects it
      if (results[0]?.fault_code && !issueForm.fault_code) {
        setIssueForm(prev => ({ ...prev, fault_code: results[0].fault_code }));
      }

      setMachineTriageResults(results);
      setActiveMachineIdx(0);
      setTriageResult(results[0]);
      setIssueStep('triage');
    } catch {
      notify.error(t('faults.triage_failed'));
    } finally {
      setIssueLoading(false);
    }
  };

  const fetchCoverage = async (equipId) => {
    setCoverageLoading(true);
    setEquipmentCoverage(null);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/equipment/${equipId}/coverage`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setEquipmentCoverage(res.data);
    } catch {
      setEquipmentCoverage(null);
    } finally {
      setCoverageLoading(false);
    }
  };

  const uploadMedia = async (issueId, media, token) => {
    // Iter 216h — pre-triage attachments must persist on the fault card
    // for both the customer and the supplier. Previously the failure
    // path was silent (console.error only) so users assumed photos had
    // attached when they hadn't. Now: explicit toast on failure and
    // sequential awaits so the parent caller can know whether all
    // attachments stored before showing the success banner.
    if (!issueId || !Array.isArray(media) || media.length === 0) return { ok: 0, failed: 0 };
    let ok = 0; let failed = 0;
    const failures = [];
    for (const file of media) {
      try {
        const formData = new FormData();
        formData.append('file', file);
        await axios.post(`${API}/issues/${issueId}/attachments`, formData, {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
        });
        ok += 1;
      } catch (err) {
        failed += 1;
        failures.push(file?.name || 'file');
        console.error('Failed to upload attachment:', err);
      }
    }
    if (failed > 0) {
      notify.error(`${failed} attachment(s) failed to upload: ${failures.join(', ')}. Re-upload from the fault card.`);
    } else if (ok > 0) {
      // Quiet success — the parent flow already shows a fault-success banner.
      console.log(`[fault] ${ok} attachment(s) saved`);
    }
    return { ok, failed };
  };

  const handleEngineerClick = async () => {
    const currentMachine = faultMachines[activeMachineIdx] || issueForm;
    if (equipmentCoverage?.covered) {
      handleResolution('engineer');
      return;
    }
    const equip = allEquipment.find(
      eq => (eq.serial_number || eq.id) === currentMachine.serial_number || eq.name === currentMachine.serial_number
    );
    const token = localStorage.getItem('token');

    let defaultItems = [{
      description: `Engineer callout - ${currentMachine.machine_type} fault repair (${currentMachine.serial_number})`,
      quantity: 1, unit_price: 0,
    }];
    let deliveryAddress = '';
    let supplierEmail = '';
    try {
      const [orgRes, supplierRes] = await Promise.all([
        axios.get(`${API}/settings/org-details`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: {} })),
        axios.get(
          `${API}/purchase-orders/supplier-lookup?equipment_serial=${encodeURIComponent(currentMachine.serial_number)}&supplier_name=${encodeURIComponent(currentMachine.supplier || '')}`,
          { headers: { Authorization: `Bearer ${token}` } },
        ).catch(() => ({ data: {} })),
      ]);
      const pricing = supplierRes.data?.pricing || {};
      deliveryAddress = orgRes.data?.address || '';
      supplierEmail = supplierRes.data?.supplier_email || '';
      const resolvedSupplierName = supplierRes.data?.supplier_name || '';
      const autoItems = [];
      if (pricing.callout_fee) autoItems.push({ description: `Engineer callout - ${currentMachine.machine_type} (${currentMachine.serial_number})`, quantity: 1, unit_price: pricing.callout_fee });
      if (pricing.labour_rate_per_hour) autoItems.push({ description: 'Labour (per hour)', quantity: 1, unit_price: pricing.labour_rate_per_hour });
      if (pricing.custom_items?.length > 0) {
        pricing.custom_items.forEach(ci => {
          if (ci.description) autoItems.push({ description: ci.description, quantity: ci.quantity || 1, unit_price: ci.unit_price || 0 });
        });
      }
      if (autoItems.length > 0) defaultItems = autoItems;
      setPOForm(prev => ({
        ...prev,
        supplier_name: resolvedSupplierName || equip?.manufacturer || currentMachine.supplier || prev.supplier_name,
        supplier_email: supplierEmail || prev.supplier_email,
        delivery_address: deliveryAddress || prev.delivery_address,
        items: defaultItems,
      }));
    } catch {
      setPOForm(prev => ({
        ...prev,
        supplier_name: equip?.manufacturer || currentMachine.supplier || prev.supplier_name,
        items: defaultItems,
      }));
    }
    setShowPOPrompt(true);
  };

  const handleCreatePOAndLog = async () => {
    setPOCreating(true);
    try {
      const token = localStorage.getItem('token');
      const currentMachine = faultMachines[activeMachineIdx] || issueForm;
      const currentTriage = machineTriageResults[activeMachineIdx] || triageResult;
      const payload = {
        ...currentMachine,
        resolution_type: 'engineer',
        ai_triage: currentTriage?.raw_triage || '',
        can_fix_onsite: currentTriage?.can_fix_onsite,
      };
      // Iter 216d — multi-machine flow gets one shared job_id so the
      // PO-backed engineer dispatch ties siblings together too.
      if (faultMachines.length > 1) {
        let jid = currentJobId;
        if (!jid) {
          jid = (typeof crypto !== 'undefined' && crypto.randomUUID)
            ? crypto.randomUUID()
            : `job-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
          setCurrentJobId(jid);
        }
        payload.job_id = jid;
      }
      const issueRes = await axios.post(`${API}/issues`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const issueId = issueRes.data?.id;

      if (issueId) await uploadMedia(issueId, currentMachine.media, token);

      await axios.post(`${API}/purchase-orders`, { ...poForm, issue_id: issueId }, {
        headers: { Authorization: `Bearer ${token}` },
      });

      setShowPOPrompt(false);
      setFaultSuccessType('engineer');
      setShowFaultSuccess(true);
      resetIssueDialog();
      loadData();
      notify.success(t('po.created_success'));
    } catch {
      notify.error(t('po.create_failed'));
    } finally {
      setPOCreating(false);
    }
  };

  const handleSkipPOAndLog = () => {
    setShowPOPrompt(false);
    handleResolution('engineer');
  };

  const handleResolution = async (resolutionType) => {
    setIssueLoading(true);
    try {
      const token = localStorage.getItem('token');
      const currentMachine = faultMachines[activeMachineIdx] || issueForm;
      const currentTriage = machineTriageResults[activeMachineIdx] || triageResult;

      let fixStepText = null;
      let fixStepTitle = null;
      if (resolutionType === 'self_fix' && selectedFixStep !== null && currentTriage?.repair_steps) {
        if (selectedFixStep >= 0 && selectedFixStep < currentTriage.repair_steps.length) {
          const step = currentTriage.repair_steps[selectedFixStep];
          fixStepTitle = step.title;
          fixStepText = step.instruction;
        }
      }

      const payload = {
        ...currentMachine,
        resolution_type: resolutionType,
        resolution_note: resolutionType === 'self_fix' ? resolutionNote : null,
        ai_triage: currentTriage?.raw_triage || '',
        can_fix_onsite: currentTriage?.can_fix_onsite,
        selected_fix_step: fixStepText,
        selected_fix_title: fixStepTitle,
      };

      // Iter 216d — multi-machine flow: stamp every sibling with one
      // shared job_id so the fault list groups them. Lazy-init on the
      // first machine; subsequent machines reuse the same id.
      if (faultMachines.length > 1) {
        let jid = currentJobId;
        if (!jid) {
          jid = (typeof crypto !== 'undefined' && crypto.randomUUID)
            ? crypto.randomUUID()
            : `job-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
          setCurrentJobId(jid);
        }
        payload.job_id = jid;
      }

      // Iter 215da — if offline OR the network drops, queue the fault
      // locally and auto-replay on reconnect. The operator sees an
      // optimistic "queued" toast instead of a red error.
      const queuedResult = await queuedMutation({
        method: 'POST',
        url: `${API}/issues`,
        body: payload,
        headers: { Authorization: `Bearer ${token}` },
        label: `Log fault: ${currentMachine.equipment_name || currentMachine.equipment_type || 'equipment'}`,
        kind: 'fault',
      });

      if (queuedResult?.queued) {
        notify.success(t('faults.queued_offline', 'Saved offline — will sync when you\'re back online'));
        resetIssueDialog();
        setFaultSuccessType(resolutionType);
        setShowFaultSuccess(true);
        return;
      }

      const response = { data: queuedResult };

      if (response.data?.id) await uploadMedia(response.data.id, currentMachine.media, token);

      const newIssue = parseAiTriage(response.data);
      setIssues(prev => [newIssue, ...prev]);
      // Capture for the post-log triage-feedback prompt.
      const triageStepTitles = (currentTriage?.repair_steps || [])
        .map(s => s?.title)
        .filter(Boolean);
      setLastIssue({ id: response.data?.id, triage_steps: triageStepTitles });

      if (activeMachineIdx < faultMachines.length - 1) {
        const nextIdx = activeMachineIdx + 1;
        setActiveMachineIdx(nextIdx);
        setTriageResult(machineTriageResults[nextIdx]);
        setResolutionNote('');
        setSelectedFixStep(null);
        setIssueStep('triage');
        notify.success(t('resolution.machine_saved', { current: activeMachineIdx + 1, total: faultMachines.length }));
      } else {
        resetIssueDialog();
        setFaultSuccessType(resolutionType);
        setShowFaultSuccess(true);
      }
    } catch {
      notify.error(t('faults.save_failed'));
    } finally {
      setIssueLoading(false);
    }
  };

  const handleUpdateIssueStatus = async (issueId, status) => {
    try {
      const token = localStorage.getItem('token');
      await axios.patch(`${API}/issues/${issueId}`, { status }, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setIssues(prev => prev.map(issue => issue.id === issueId ? { ...issue, status } : issue));
      notify.success(t('faults.status_updated'));
    } catch {
      notify.error(t('faults.status_failed'));
    }
  };

  const handleServiceRequest = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/service/request`, serviceForm, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setShowServiceDialog(false);
      notify.success(t('service.success'));
      setServiceForm({
        machine_type: '', issue_summary: '', site_info: '',
        contact_name: user?.full_name || '',
        contact_email: user?.email || '',
        contact_phone: '',
      });
    } catch {
      notify.error(t('service.failed'));
    }
  };

  return {
    // dialog & step state
    showIssueDialog, setShowIssueDialog,
    issueStep, setIssueStep,
    issueLoading,
    // form state
    issueForm, setIssueForm,
    issueMedia, setIssueMedia,
    selectedMachineType, setSelectedMachineType,
    // Site Staff Shared Login — reporter dropdown
    requireReporter: isSharedLogin, siteStaff,
    reporterStaffId: reporterIsOther ? '__other__' : (issueForm.reporter_staff_id || ''), setReporterStaffId,
    allowOtherStaff: !!siteStaffSettings.allow_other_staff,
    requireStaffPin: !!siteStaffSettings.require_staff_pin,
    reporterPin: issueForm.reporter_pin || '', setReporterPin,
    reporterOther: { name: issueForm.reporter_name || '', job_title: issueForm.reporter_job_title || '', email: issueForm.reporter_email || '', phone: issueForm.reporter_phone || '' }, setReporterOther,
    // triage
    triageResult, setTriageResult,
    machineTriageResults,
    // multi-machine
    faultMachines,
    submitCount,
    activeMachineIdx, setActiveMachineIdx,
    // resolution
    resolutionNote, setResolutionNote,
    selectedFixStep, setSelectedFixStep,
    selectedIssue, setSelectedIssue,
    // warnings & success
    existingFaultWarning, setExistingFaultWarning,
    showFaultSuccess, setShowFaultSuccess,
    faultSuccessType,
    lastIssue,
    // coverage & PO
    equipmentCoverage, coverageLoading,
    showPOPrompt, setShowPOPrompt,
    poForm, setPOForm, poCreating,
    // service request
    showServiceDialog, setShowServiceDialog,
    serviceForm, setServiceForm,
    // handlers
    resetIssueDialog,
    addMachineToFault,
    removeMachineFromFault,
    handleIssueSubmit,
    fetchCoverage,
    handleEngineerClick,
    handleCreatePOAndLog,
    handleSkipPOAndLog,
    handleResolution,
    handleUpdateIssueStatus,
    handleServiceRequest,
  };
};

export default useIssueWorkflow;
