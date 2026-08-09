import { AlertTriangle, Zap, Volume2, Wrench, ShieldAlert, HelpCircle } from 'lucide-react';

export const FAULT_TYPES = [
  { id: 'not_working', label: 'Not working', icon: Wrench,       tone: 'amber' },
  { id: 'noise',       label: 'Noise',       icon: Volume2,      tone: 'sky' },
  { id: 'electrical',  label: 'Electrical',  icon: Zap,          tone: 'red' },
  { id: 'damage',      label: 'Damage',      icon: AlertTriangle,tone: 'orange' },
  { id: 'safety',      label: 'Safety',      icon: ShieldAlert,  tone: 'red' },
  { id: 'other',       label: 'Other',       icon: HelpCircle,   tone: 'zinc' },
];

export const ONSETS = [
  { id: 'today',      label: 'Today' },
  { id: 'yesterday',  label: 'Yesterday' },
  { id: 'this_week',  label: 'This week' },
  { id: 'older',      label: 'Over a week ago' },
];

export const USABLE = [
  { id: 'yes',     label: 'Yes', help: 'Fully functional, cosmetic issue only' },
  { id: 'limited', label: 'Limited', help: 'Works but reduced function' },
  { id: 'no',      label: 'No', help: 'Completely unusable' },
];

export const SAFE = [
  { id: 'yes', label: 'Yes, safe to leave in service' },
  { id: 'no',  label: 'No — isolate immediately' },
];

export const emptyMachineData = () => ({
  fault_type: '',
  description: '',
  steps_taken: '',
  onset: '',
  usable: '',
  safe_in_service: '',
  attachment_urls: [],
});

export function priorityTone(p) {
  return {
    urgent: 'bg-red-500/20 text-red-600 dark:text-red-300',
    high:   'bg-orange-500/20 text-orange-600 dark:text-orange-300',
    medium: 'bg-amber-500/20 text-amber-600 dark:text-amber-300',
    low:    'bg-emerald-500/20 text-emerald-600 dark:text-emerald-300',
  }[p] || 'bg-black/10 dark:bg-white/10';
}
