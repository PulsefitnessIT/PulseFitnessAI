/**
 * Iter 220e3 — Contracts catalog hook + tier defaults.
 *
 * The CRM → Contracts wizard, comparison matrix, template manager
 * and the new Inclusions / Exclusions / Consumables / Response Times
 * tabs ALL consume this one catalog so labels stay in lockstep across
 * surfaces and the tenant-level relabel hook (Contract Settings) works
 * everywhere at once.
 */
import { useEffect, useState, useMemo } from 'react';
import axios from 'axios';

const FALLBACK_CATALOG = {
  inclusion_groups: [
    { key: 'technical_support', label: 'Technical Support', items: [
      { key: 'technical_support', label: 'Technical support' },
      { key: 'remote_support', label: 'Remote support' },
      { key: 'local_engineer_support', label: 'Local engineer support' },
      { key: 'pm_training', label: 'PM guidance / training' },
    ]},
    { key: 'online_support', label: 'Online Support', items: [
      { key: 'portal_access', label: 'Customer portal access' },
      { key: 'online_manuals', label: 'Online manuals' },
      { key: 'service_report_access', label: 'Service report access' },
      { key: 'asset_history', label: 'Asset history access' },
      { key: 'customer_fault_logging', label: 'Customer fault logging' },
    ]},
    { key: 'maintenance', label: 'Maintenance', items: [
      { key: 'callout', label: 'Callout included' },
      { key: 'labour', label: 'Labour included' },
      { key: 'preventative_maintenance', label: 'Preventative maintenance' },
      { key: 'major_parts', label: 'Major parts' },
      { key: 'wear_tear_parts', label: 'Wear & tear parts' },
      { key: 'treadmill_beds', label: 'Treadmill beds' },
      { key: 'treadmill_belts', label: 'Treadmill belts' },
      { key: 'upholstery', label: 'Upholstery' },
      { key: 'software_updates', label: 'Software updates' },
      { key: 'response_time', label: 'Organised response time' },
      { key: 'annual_inspection', label: 'Annual inspection' },
      { key: 'safety_inspection', label: 'Safety inspection' },
      { key: 'asset_condition_report', label: 'Asset condition report' },
      { key: 'capex_recommendation', label: 'CAPEX recommendation' },
    ]},
    { key: 'extras', label: 'Extra Services', items: [
      { key: 'discounted_wear_tear', label: 'Discounted wear & tear parts' },
      { key: 'discounted_aesthetic', label: 'Discounted aesthetic parts' },
      { key: 'discounted_labour_rate', label: 'Discounted labour rate' },
      { key: 'discounted_callout_rate', label: 'Discounted callout rate' },
      { key: 'priority_booking', label: 'Priority engineer booking' },
      { key: 'emergency_upgrade', label: 'Emergency response upgrade' },
      { key: 'annual_audit', label: 'Annual equipment audit' },
      { key: 'staff_training', label: 'Staff training' },
      { key: 'monthly_site_report', label: 'Monthly site report' },
      { key: 'quarterly_asset_review', label: 'Quarterly asset review' },
    ]},
  ],
  exclusion_items: [
    { key: 'misuse', label: 'Customer misuse' },
    { key: 'accidental', label: 'Accidental damage' },
    { key: 'vandalism', label: 'Vandalism' },
    { key: 'cosmetic', label: 'Cosmetic damage' },
    { key: 'upholstery_excl', label: 'Upholstery (if not included)' },
    { key: 'beds_excl', label: 'Treadmill beds / decks (if not included)' },
    { key: 'belts_excl', label: 'Treadmill belts (if not included)' },
    { key: 'consumables_excl', label: 'Consumables' },
    { key: 'cleaning', label: 'Cleaning products' },
    { key: 'corrosion', label: 'Corrosion / rust' },
    { key: 'electrical_supply', label: 'Poor electrical supply' },
    { key: 'equipment_misuse', label: 'Misuse of equipment' },
    { key: 'relocation', label: 'Equipment relocation' },
    { key: 'carriage', label: 'Carriage and insurance' },
    { key: 'third_party_delays', label: 'Third-party delays' },
    { key: 'obsolete_parts', label: 'Obsolete parts' },
  ],
  consumable_presets: [
    { name: 'Belt lubricant', default_charge: 0, included_default: true },
    { name: 'Cleaning solutions', default_charge: 12, included_default: false },
  ],
  response_time_bands: [
    { key: 'emergency', label: 'Emergency', default_hours: 4 },
    { key: 'urgent', label: 'Urgent', default_hours: 24 },
    { key: 'standard', label: 'Standard', default_hours: 72 },
    { key: 'remote_support', label: 'Remote support', default_hours: 2 },
    { key: 'parts_quotation', label: 'Parts quotation', default_hours: 48 },
    { key: 'first_attendance', label: 'First attendance', default_hours: 48 },
  ],
};

export function useContractCatalog(API, headers) {
  const [catalog, setCatalog] = useState(FALLBACK_CATALOG);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/crm/v2/contract-catalog`, { headers: headers() })
      .then(res => { if (alive && res.data) setCatalog(res.data); })
      .catch(() => { /* fallback already in state */ })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [API, headers]);
  return { catalog, loading };
}

export function useContractTemplates(API, headers) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const reload = useMemo(() => () => {
    setLoading(true);
    return axios.get(`${API}/crm/v2/contract-templates`, { headers: headers() })
      .then(res => setTemplates(res.data.templates || []))
      .catch(() => setTemplates([]))
      .finally(() => setLoading(false));
  }, [API, headers]);
  useEffect(() => { reload(); }, [reload]);
  return { templates, loading, reload };
}

export default FALLBACK_CATALOG;
