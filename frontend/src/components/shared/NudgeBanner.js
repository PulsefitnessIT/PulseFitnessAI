/**
 * NudgeBanner — compact in-app banner listing open proactive nudges for the
 * caller's org. Polls ``/api/nudges`` on mount and lets owners/managers
 * dismiss items inline.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, Bell, Wrench, X, KeyRound } from 'lucide-react';
import { Link } from 'react-router-dom';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ICONS = {
  'nudge.warranty_expiring': Wrench,
  'nudge.ppm_overdue': AlertTriangle,
  'nudge.supplier_sla_drift': Bell,
  'nudge.password_rotation': KeyRound,
};

const TONE = {
  high: 'border-red-500/40 bg-red-500/10 text-red-100',
  med: 'border-amber-500/40 bg-amber-500/10 text-amber-100',
  low: 'border-sky-500/40 bg-sky-500/10 text-sky-100',
  info: 'border-white/10 bg-white/5 text-white/80',
};

export default function NudgeBanner({ canDismiss = true }) {
  const [nudges, setNudges] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const [nudgesRes, meRes] = await Promise.allSettled([
        axios.get(`${API}/nudges`, { headers: { Authorization: `Bearer ${token}` } }),
        axios.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const base = nudgesRes.status === 'fulfilled' ? (nudgesRes.value.data?.nudges || []) : [];
      // Synthesize a client-side password rotation nudge from /auth/me flags.
      if (meRes.status === 'fulfilled' && meRes.value.data?.password_needs_rotation) {
        base.unshift({
          id: '__password_rotation__',
          type: 'nudge.password_rotation',
          severity: 'med',
          summary: 'Your password is older than the policy allows',
          customer_safe_message: `Your password is older than ${meRes.value.data.password_max_age_days || 180} days. Please change it from Account → Reset password.`,
          synthetic: true,
        });
      }
      setNudges(base);
    } catch {
      setNudges([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const dismiss = async (id) => {
    if (id === '__password_rotation__') {
      setNudges((prev) => prev.filter((n) => n.id !== id));
      return;
    }
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/nudges/${id}/dismiss`, null, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setNudges((prev) => prev.filter((n) => n.id !== id));
    } catch {
      // soft-fail: banner stays visible if the dismiss call fails
    }
  };

  if (loading || !nudges.length) return null;

  return (
    <div className="mb-6 space-y-2" data-testid="nudge-banner">
      {nudges.map((n) => {
        const Icon = ICONS[n.type] || Bell;
        const toneClass = TONE[n.severity] || TONE.info;
        return (
          <div
            key={n.id}
            className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${toneClass}`}
            data-testid={`nudge-${n.type}`}
          >
            <Icon size={18} className="mt-0.5 flex-shrink-0" />
            <div className="flex-1 text-sm">
              <div className="font-medium leading-snug">
                {n.customer_safe_message || n.summary}
              </div>
              {n.payload?.count ? (
                <div className="mt-1 text-xs opacity-80">
                  {n.payload.count} item{n.payload.count === 1 ? '' : 's'} flagged
                </div>
              ) : null}
            </div>
            {canDismiss && (
              <button
                type="button"
                onClick={() => dismiss(n.id)}
                className="flex-shrink-0 rounded-full p-1 hover:bg-white/10"
                aria-label="Dismiss"
                data-testid={`nudge-dismiss-${n.id}`}
              >
                <X size={16} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
