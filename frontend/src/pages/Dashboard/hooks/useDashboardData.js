import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

import { notify } from '@/components/notifications';
/**
 * Parse the ai_triage JSON payload attached to each issue into ai_triage_parsed,
 * tolerating markdown code-fence wrappers.
 */
const parseAiTriage = (issue) => {
  if (!issue.ai_triage || issue.ai_triage_parsed) return issue;
  try {
    let cleaned = issue.ai_triage.trim();
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.split('\n').slice(1).join('\n').replace(/```$/, '').trim();
    }
    issue.ai_triage_parsed = JSON.parse(cleaned);
  } catch {
    // If parsing fails, leave ai_triage_parsed undefined
  }
  return issue;
};

/**
 * Loads the seven core dashboard data sets in parallel and exposes setters
 * so child handlers (issue creation, status updates) can keep state in sync.
 */
const useDashboardData = (API, { onPaymentSuccess } = {}) => {
  const [issues, setIssues] = useState([]);
  const [auditHistory, setAuditHistory] = useState([]);
  const [maintenanceTasks, setMaintenanceTasks] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [allEquipment, setAllEquipment] = useState([]);
  const [healthScore, setHealthScore] = useState(null);
  const [expiryAlertCount, setExpiryAlertCount] = useState(0);
  const [urgentExpiryAlerts, setUrgentExpiryAlerts] = useState([]);

  const loadData = useCallback(async () => {
    const token = localStorage.getItem('token');
    // Iter 216h62 — site-scoped suppliers (read activeSite from
    // localStorage cache so callers don't have to re-thread the prop).
    // Owners/managers viewing All-sites mode clear the cache, so we
    // automatically fall back to the org-wide list.
    let scopeSiteParam = '';
    try {
      const cached = localStorage.getItem('active_site_cache');
      if (cached) {
        const s = JSON.parse(cached);
        if (s?.id && !s?.is_default) scopeSiteParam = `?site_id=${encodeURIComponent(s.id)}`;
      }
    } catch { /* ignore */ }
    try {
      const [issuesRes, auditsRes, tasksRes, suppliersRes, equipmentRes, healthRes, expiryRes] = await Promise.all([
        axios.get(`${API}/issues`, { headers: { Authorization: `Bearer ${token}` } }),
        axios.get(`${API}/audit/history`, { headers: { Authorization: `Bearer ${token}` } }),
        axios.get(`${API}/maintenance/tasks`),
        axios.get(`${API}/suppliers${scopeSiteParam}`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: { suppliers: [] } })),
        axios.get(`${API}/equipment`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: { equipment: [] } })),
        axios.get(`${API}/gym-health-score`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: null })),
        axios.get(`${API}/expiry-alerts`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: { alerts: [], total: 0 } })),
      ]);

      setIssues((issuesRes.data.issues || []).map(parseAiTriage));
      setAuditHistory(auditsRes.data.audits || []);
      setMaintenanceTasks(tasksRes.data.tasks || []);
      setSuppliers(suppliersRes.data.suppliers || []);
      setAllEquipment(equipmentRes.data.equipment || []);
      if (healthRes.data) setHealthScore(healthRes.data);
      setExpiryAlertCount(expiryRes.data.total || 0);
      setUrgentExpiryAlerts((expiryRes.data.alerts || []).filter(a => a.days_remaining <= 30));
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    }
  }, [API]);

  const checkPaymentStatus = useCallback(async (sessionId, paymentSuccessMessage) => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API}/payments/status/${sessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.data.payment_status === 'paid') {
        notify.success(paymentSuccessMessage);
        onPaymentSuccess?.();
      }
    } catch (error) {
      console.error('Payment status check failed:', error);
    }
  }, [API, onPaymentSuccess]);

  // initial load
  // eslint-disable-next-line react-hooks/exhaustive-deps -- todo: review missing dep(s) 'loadData'; pre-existing as of iter 216h226-polish-5.
  useEffect(() => { loadData();   }, []);

  return {
    issues, setIssues,
    auditHistory, setAuditHistory,
    maintenanceTasks,
    suppliers,
    allEquipment,
    healthScore,
    expiryAlertCount,
    urgentExpiryAlerts,
    loadData,
    checkPaymentStatus,
    parseAiTriage,
  };
};

export default useDashboardData;
