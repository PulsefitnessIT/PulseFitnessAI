import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { SectionCard } from './shared';

const BookingRulesTab = ({ rules, onSave }) => {
 const [form, setForm] = useState(null);
 useEffect(() => { if (rules) setForm({ ...rules }); }, [rules]);

 if (!form) return null;

 const save = () => {
 const payload = {
 booking_window_hours: Number(form.booking_window_hours),
 cancellation_cutoff_hours: Number(form.cancellation_cutoff_hours),
 waitlist_enabled: !!form.waitlist_enabled,
 max_waitlist: Number(form.max_waitlist),
 default_capacity: Number(form.default_capacity),
 no_show_penalty: form.no_show_penalty,
 no_show_strikes_before_block: Number(form.no_show_strikes_before_block),
 checkin_window_min: Number(form.checkin_window_min),
 instructor_assignment: form.instructor_assignment,
 allow_site_overrides: !!form.allow_site_overrides,
 };
 onSave(payload);
 };

 const Row = ({ label, children, hint }) => (
 <div className="border-b border-zinc-100 last:border-b-0 py-3 grid grid-cols-1 sm:grid-cols-3 gap-3 items-center">
 <div className="sm:col-span-2">
 <Label className="text-sm">{label}</Label>
 {hint && <p className="text-xs text-zinc-500 mt-0.5">{hint}</p>}
 </div>
 <div className="sm:justify-self-end w-full sm:w-auto sm:min-w-[180px]">{children}</div>
 </div>
 );

 return (
 <div className="space-y-4" data-testid="memberships-admin-booking-rules">
 <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/50 rounded-lg p-3 text-sm text-amber-800 dark:text-amber-200">
 <p className="font-semibold">Platform default booking rules</p>
 <p className="text-xs mt-1 opacity-90">
 These apply only to gyms that haven&apos;t set their own. Each gym can override them
 from <strong>Memberships → Booking rules</strong> in their own portal. When a gym saves their
 first override, this default stops applying to them.
 </p>
 </div>
 <SectionCard
 title="Platform default booking rules"
 action={
 <Button size="sm" className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]" onClick={save} data-testid="save-booking-rules">
 Save changes
 </Button>
 }
 >
 <Row label="Booking window (hours in advance)" hint="How far ahead members can book a class">
 <Input type="number" value={form.booking_window_hours} onChange={(e) => setForm({ ...form, booking_window_hours: e.target.value })} data-testid="rule-booking-window" />
 </Row>
 <Row label="Cancellation cut-off (hours before class)" hint="Below this, a cancel counts as a no-show">
 <Input type="number" value={form.cancellation_cutoff_hours} onChange={(e) => setForm({ ...form, cancellation_cutoff_hours: e.target.value })} data-testid="rule-cancel-cutoff" />
 </Row>
 <Row label="Default capacity" hint="Used when a new class template omits capacity">
 <Input type="number" value={form.default_capacity} onChange={(e) => setForm({ ...form, default_capacity: e.target.value })} data-testid="rule-default-capacity" />
 </Row>
 <Row label="Waitlist enabled">
 <Switch checked={form.waitlist_enabled} onCheckedChange={(v) => setForm({ ...form, waitlist_enabled: v })} data-testid="rule-waitlist-enabled" />
 </Row>
 <Row label="Max waitlist size">
 <Input type="number" value={form.max_waitlist} onChange={(e) => setForm({ ...form, max_waitlist: e.target.value })} data-testid="rule-max-waitlist" />
 </Row>
 <Row label="Check-in window (minutes)" hint="How long before class start check-in opens">
 <Input type="number" value={form.checkin_window_min} onChange={(e) => setForm({ ...form, checkin_window_min: e.target.value })} />
 </Row>
 <Row label="No-show penalty" hint="What happens when a member no-shows">
 <select className="w-full border border-zinc-200 rounded-md h-9 px-2 text-sm" value={form.no_show_penalty} onChange={(e) => setForm({ ...form, no_show_penalty: e.target.value })} data-testid="rule-noshow-penalty">
 <option value="warning">Warning only</option>
 <option value="credit_forfeit">Forfeit class credit</option>
 <option value="suspension">Temporary suspension</option>
 </select>
 </Row>
 <Row label="Strikes before booking block">
 <Input type="number" value={form.no_show_strikes_before_block} onChange={(e) => setForm({ ...form, no_show_strikes_before_block: e.target.value })} />
 </Row>
 <Row label="Instructor assignment" hint="How classes get an instructor by default">
 <select className="w-full border border-zinc-200 rounded-md h-9 px-2 text-sm" value={form.instructor_assignment} onChange={(e) => setForm({ ...form, instructor_assignment: e.target.value })}>
 <option value="manual">Manual</option>
 <option value="auto">Auto (next available)</option>
 <option value="balanced">Balanced (spread load)</option>
 </select>
 </Row>
 <Row label="Allow site overrides" hint="When off, these defaults are enforced platform-wide">
 <Switch checked={form.allow_site_overrides} onCheckedChange={(v) => setForm({ ...form, allow_site_overrides: v })} data-testid="rule-allow-overrides" />
 </Row>

 {form.updated_at && (
 <p className="text-[11px] text-zinc-400 mt-3">Last updated {new Date(form.updated_at).toLocaleString()} by {form.updated_by || 'system'}</p>
 )}
 </SectionCard>
 </div>
 );
};

export default BookingRulesTab;
