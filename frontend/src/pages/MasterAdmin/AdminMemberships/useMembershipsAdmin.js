import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';

import { notify } from '@/components/notifications';
/** Thin data-layer hook for the Memberships Master Admin tab. */
const useMembershipsAdmin = () => {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [overview, setOverview] = useState(null);
  const [organizations, setOrganizations] = useState([]);
  const [revenue, setRevenue] = useState(null);
  const [engagement, setEngagement] = useState(null);
  const [instructors, setInstructors] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [bookingRules, setBookingRules] = useState(null);
  const [tierMatrix, setTierMatrix] = useState(null);
  const [featureFlags, setFeatureFlags] = useState(null);
  const [aiInsights, setAiInsights] = useState(null);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);

  const api = (path) => `${API}/master-admin/memberships${path}`;

  const loadAll = useCallback(async () => {
    setLoading(true);
    // Iter 216h271 — switched from Promise.all to allSettled. A single
    // 500 on one endpoint (e.g. revenue) used to nuke the whole page
    // and leave it stuck in loading. Now each tab loads what it can
    // and degrades gracefully; the toast still fires so the operator
    // knows something failed.
    const calls = [
      ['overview',     api('/overview')],
      ['organizations',api('/organizations')],
      ['revenue',      api('/revenue')],
      ['engagement',   api('/engagement')],
      ['instructors',  api('/instructors')],
      ['templates',    api('/templates/plans')],
      ['bookingRules', api('/booking-rules')],
      ['tiers',        api('/tiers')],
      ['featureFlags', api('/feature-flags')],
      ['audit',        api('/audit')],
    ];
    const results = await Promise.allSettled(
      calls.map(([, url]) => axios.get(url, { headers })),
    );
    const data = {};
    const failed = [];
    results.forEach((r, i) => {
      const key = calls[i][0];
      if (r.status === 'fulfilled') data[key] = r.value.data;
      else failed.push(key);
    });
    if (data.overview) setOverview(data.overview);
    if (data.organizations) setOrganizations(data.organizations.organizations || []);
    if (data.revenue) setRevenue(data.revenue);
    if (data.engagement) setEngagement(data.engagement);
    if (data.instructors) setInstructors(data.instructors);
    if (data.templates) setTemplates(data.templates.templates || []);
    if (data.bookingRules) setBookingRules(data.bookingRules.rules);
    if (data.tiers) setTierMatrix(data.tiers);
    if (data.featureFlags) setFeatureFlags(data.featureFlags);
    if (data.audit) setAudit(data.audit.audit || []);
    if (failed.length) {
      notify.error(`Memberships admin: ${failed.length} section${failed.length === 1 ? '' : 's'} failed to load (${failed.join(', ')})`);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  const loadAiInsights = useCallback(async () => {
    try {
      const r = await axios.get(api('/ai-insights'), { headers });
      setAiInsights(r.data);
    } catch {
      setAiInsights({ insights: [], generated_at: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const setOrgTier = async (orgId, tier) => {
    await axios.put(api(`/organizations/${orgId}/tier`), { memberships_tier: tier }, { headers });
    notify.success(`Tier set to ${tier.toUpperCase()}`);
    loadAll();
  };

  const setOrgOverrides = async (orgId, payload) => {
    await axios.put(api(`/organizations/${orgId}/overrides`), payload, { headers });
    notify.success('Overrides updated');
    loadAll();
  };

  const createTemplate = async (body) => {
    await axios.post(api('/templates/plans'), body, { headers });
    notify.success('Template created');
    loadAll();
  };

  const updateTemplate = async (id, body) => {
    await axios.patch(api(`/templates/plans/${id}`), body, { headers });
    notify.success('Template updated');
    loadAll();
  };

  const deleteTemplate = async (id) => {
    await axios.delete(api(`/templates/plans/${id}`), { headers });
    notify.success('Template deleted');
    loadAll();
  };

  const applyTemplate = async (id, organization_ids, lock) => {
    const r = await axios.post(api(`/templates/plans/${id}/apply`), { organization_ids, lock }, { headers });
    notify.success(`Applied to ${r.data.created} orgs`);
    loadAll();
    return r.data;
  };

  const saveBookingRules = async (body) => {
    await axios.put(api('/booking-rules'), body, { headers });
    notify.success('Booking rules saved');
    loadAll();
  };

  const saveTierMatrix = async (matrix) => {
    await axios.put(api('/tiers'), { matrix }, { headers });
    notify.success('Tier matrix saved');
    loadAll();
  };

  const saveFeatureFlags = async (flags) => {
    await axios.put(api('/feature-flags'), { flags }, { headers });
    notify.success('Feature flags saved');
    loadAll();
  };

  return {
    loading,
    overview, organizations, revenue, engagement, instructors,
    templates, bookingRules, tierMatrix, featureFlags, aiInsights, audit,
    reload: loadAll, loadAiInsights,
    setOrgTier, setOrgOverrides,
    createTemplate, updateTemplate, deleteTemplate, applyTemplate,
    saveBookingRules, saveTierMatrix, saveFeatureFlags,
  };
};

export default useMembershipsAdmin;
