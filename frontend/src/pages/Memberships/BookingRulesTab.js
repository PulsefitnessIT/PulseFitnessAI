/**
 * Per-gym Booking Rules tab — Memberships Console.
 *
 * Each gym sets the policies that govern bookings, cancellations and
 * waitlists. Until they save the first override they inherit the platform
 * defaults from master admin (banner explains this). A "Reset to platform
 * default" button drops the local override.
 *
 * Backed by `GET/PUT/POST /api/memberships/booking-rules` endpoints.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, Save, RotateCcw, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { notify, useConfirm } from '@/components/notifications';

const FIELD_HELPERS = {
  booking_window_hours:        'How far in advance members can book a class (hours).',
  cancellation_cutoff_hours:   'Members must cancel this many hours before the class to avoid a no-show.',
  max_waitlist:                'Hard cap on waitlist size per class.',
  default_capacity:            'Used when a class doesn\'t set its own capacity.',
  no_show_strikes_before_block: 'How many no-shows before the member is blocked from booking.',
  checkin_window_min:          'Minutes before/after class start when QR check-in is accepted.',
};

const PENALTY_OPTIONS = [
  { value: 'warning',         label: 'Warning only' },
  { value: 'credit_forfeit',  label: 'Forfeit class credit' },
  { value: 'suspension',      label: 'Auto-suspend after N strikes' },
];

const ASSIGNMENT_OPTIONS = [
  { value: 'manual',   label: 'Manual — manager picks each instructor' },
  { value: 'auto',     label: 'Auto — system picks the next available instructor' },
  { value: 'balanced', label: 'Balanced — even out the rota by class count' },
];

export default function BookingRulesTab({ API, headers }) {
  const [rules, setRules] = useState(null);
  const [inherited, setInherited] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const confirm = useConfirm();

  const load = React.useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/memberships/booking-rules`, { headers });
      setRules(data.rules || {});
      setInherited(!!data.inherited);
    } catch (e) {
      notify.error('Failed to load booking rules', e.response?.data?.detail || 'Try refreshing.');
    }
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  if (!rules) {
    return (
      <div className="flex items-center justify-center py-16" data-testid="booking-rules-loading">
        <Loader2 className="animate-spin" size={20} style={{ color: 'var(--theme-text-muted)' }} />
      </div>
    );
  }

  const setField = (k, v) => setRules({ ...rules, [k]: v });

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        booking_window_hours: Number(rules.booking_window_hours) || 168,
        cancellation_cutoff_hours: Number(rules.cancellation_cutoff_hours) || 12,
        waitlist_enabled: !!rules.waitlist_enabled,
        max_waitlist: Number(rules.max_waitlist) || 0,
        default_capacity: Number(rules.default_capacity) || 20,
        no_show_penalty: rules.no_show_penalty || 'warning',
        no_show_strikes_before_block: Number(rules.no_show_strikes_before_block) || 3,
        checkin_window_min: Number(rules.checkin_window_min) || 15,
        instructor_assignment: rules.instructor_assignment || 'manual',
        allow_site_overrides: !!rules.allow_site_overrides,
      };
      await axios.put(`${API}/memberships/booking-rules`, payload, { headers });
      notify.success('Booking rules saved', inherited ? 'You\'re now using your own rules instead of the platform default.' : 'Updated.');
      setInherited(false);
      load();
    } catch (e) {
      notify.error('Save failed', e.response?.data?.detail || 'Try again.');
    } finally {
      setSaving(false);
    }
  };

  const resetToPlatform = async () => {
    const ok = await confirm({
      title: 'Reset to platform default?',
      detail: 'Your gym-specific overrides will be deleted and you\'ll inherit the master admin\'s defaults. You can always re-customise later.',
      tone: 'warning',
      confirmLabel: 'Reset',
      cancelLabel: 'Keep my rules',
    });
    if (!ok) return;
    setResetting(true);
    try {
      await axios.post(`${API}/memberships/booking-rules/reset-to-platform`, {}, { headers });
      notify.success('Reset to platform default');
      setInherited(true);
      load();
    } catch (e) {
      notify.error('Reset failed', e.response?.data?.detail || 'Try again.');
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="booking-rules-tab">
      {inherited && (
        <div className="rounded-lg p-3 text-sm flex items-start gap-2" data-testid="booking-rules-inherited-banner"
          style={{ background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.35)', color: 'var(--theme-text)' }}>
          <Info size={16} className="text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">You\'re using the platform default</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              Save any change below to switch this gym to its own rules. Until then, anything master admin tweaks
              centrally will flow through automatically.
            </p>
          </div>
        </div>
      )}

      <div className="rounded-lg p-5 space-y-5"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <NumberField label="Booking window (hours)" k="booking_window_hours" rules={rules} setField={setField} min={1} max={4320} />
          <NumberField label="Cancellation cutoff (hours)" k="cancellation_cutoff_hours" rules={rules} setField={setField} min={0} max={720} />
          <NumberField label="Default class capacity" k="default_capacity" rules={rules} setField={setField} min={1} max={500} />
          <NumberField label="Check-in window (minutes)" k="checkin_window_min" rules={rules} setField={setField} min={0} max={120} />
        </div>

        {/* Waitlist */}
        <div className="rounded-md p-3 flex items-center justify-between"
          style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
          <div>
            <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Waitlist enabled</p>
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Auto-promote when seats open up.</p>
          </div>
          <Switch checked={!!rules.waitlist_enabled} onCheckedChange={(v) => setField('waitlist_enabled', v)} data-testid="booking-rules-waitlist" />
        </div>
        {rules.waitlist_enabled && (
          <NumberField label="Max waitlist per class" k="max_waitlist" rules={rules} setField={setField} min={0} max={500} />
        )}

        {/* No-show policy */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SelectField label="No-show penalty" k="no_show_penalty" rules={rules} setField={setField} options={PENALTY_OPTIONS} />
          <NumberField label="Strikes before block" k="no_show_strikes_before_block" rules={rules} setField={setField} min={1} max={20} />
        </div>

        {/* Instructor assignment */}
        <SelectField label="Instructor assignment" k="instructor_assignment" rules={rules} setField={setField} options={ASSIGNMENT_OPTIONS} />

        {/* Site overrides */}
        <div className="rounded-md p-3 flex items-center justify-between"
          style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
          <div>
            <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Allow per-site overrides</p>
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Multi-site gyms can give each site its own rules.</p>
          </div>
          <Switch checked={!!rules.allow_site_overrides} onCheckedChange={(v) => setField('allow_site_overrides', v)} data-testid="booking-rules-site-overrides" />
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t" style={{ borderColor: 'var(--theme-border)' }}>
          {!inherited && (
            <Button variant="outline" size="sm" onClick={resetToPlatform} disabled={resetting} data-testid="booking-rules-reset">
              <RotateCcw size={12} className="mr-1.5" /> {resetting ? 'Resetting…' : 'Reset to platform default'}
            </Button>
          )}
          <Button size="sm" onClick={save} disabled={saving} className="bg-[var(--color-brand-cyan)] text-zinc-900 hover:bg-[rgb(var(--rgb-brand-cyan)/0.9)]" data-testid="booking-rules-save">
            <Save size={12} className="mr-1.5" /> {saving ? 'Saving…' : 'Save booking rules'}
          </Button>
        </div>
      </div>
    </div>
  );
}

const NumberField = ({ label, k, rules, setField, min, max }) => (
  <div>
    <Label className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{label}</Label>
    <Input type="number" min={min} max={max} value={rules[k] ?? ''}
      onChange={(e) => setField(k, e.target.value)}
      className="mt-1" data-testid={`booking-rules-${k}`} />
    {FIELD_HELPERS[k] && (
      <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>{FIELD_HELPERS[k]}</p>
    )}
  </div>
);

const SelectField = ({ label, k, rules, setField, options }) => (
  <div>
    <Label className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{label}</Label>
    <select value={rules[k] || ''} onChange={(e) => setField(k, e.target.value)}
      className="w-full mt-1 h-9 px-2 rounded-md text-sm"
      style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}
      data-testid={`booking-rules-${k}`}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </div>
);
