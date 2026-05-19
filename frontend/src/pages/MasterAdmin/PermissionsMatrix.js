/**
 * Permissions matrix — SOC 2-friendly one-glance view of every Pulse Master
 * Admin and which organisations they've been attached to via the iter 216h
 * dual-role assignment.
 *
 * Two view modes:
 *   • "By admin"  — one row per admin, columns: name · email · attached count · org pills.
 *   • "By gym"    — one row per org, columns: org · attached admins (pills).
 *
 * Also exposes a CSV export button so compliance reviewers can pull a snapshot
 * without filing a backend ticket — useful as evidence artefact for quarterly
 * access reviews.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Building2, Search, Download, Users, RefreshCw, Filter, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { useInlineBanner } from '@/components/notifications';
import { SkeletonLine } from '@/components/shared/Skeleton';

const VIEWS = [
  { id: 'by-admin', label: 'By admin', icon: Users },
  { id: 'by-gym', label: 'By gym', icon: Building2 },
];

// CSV-safe cell — strips control chars, wraps in quotes, escapes inner quotes.
const csvCell = (v) => `"${String(v ?? '').replace(/"/g, '""').replace(/[\r\n]+/g, ' ')}"`;

const downloadCsv = (rows, filename) => {
  const csv = rows.map((r) => r.map(csvCell).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

const PermissionsMatrix = ({ API }) => {
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [view, setView] = useState('by-admin');
  const [admins, setAdmins] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [onlyAttached, setOnlyAttached] = useState(false);
  const { banner, show } = useInlineBanner();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, o] = await Promise.all([
        axios.get(`${API}/master-admin/pulse-admins`, { headers }),
        axios.get(`${API}/master-admin/organizations`, { headers }),
      ]);
      setAdmins((a.data.admins || []).filter((x) => x.active !== false));
      setOrgs(o.data.organizations || []);
    } catch (err) {
      show({ tone: 'error', title: "Couldn't load matrix", detail: err.response?.data?.detail });
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { load(); }, [load]);

  // ── Derived ─────────────────────────────────────────────────────────
  const orgLookup = useMemo(() => {
    const map = new Map();
    orgs.forEach((o) => map.set(o.id, o));
    return map;
  }, [orgs]);

  const adminsView = useMemo(() => {
    const q = query.trim().toLowerCase();
    return admins
      .filter((a) => {
        if (onlyAttached && (a.organization_memberships || []).length === 0) return false;
        if (!q) return true;
        return (
          (a.full_name || '').toLowerCase().includes(q) ||
          (a.email || '').toLowerCase().includes(q) ||
          (a.membership_org_names || []).some((m) => (m.name || '').toLowerCase().includes(q))
        );
      })
      .sort((a, b) => (a.full_name || '').localeCompare(b.full_name || ''));
  }, [admins, query, onlyAttached]);

  const gymsView = useMemo(() => {
    const q = query.trim().toLowerCase();
    // Build org → [admins attached] index.
    const idx = new Map();
    admins.forEach((a) => {
      (a.organization_memberships || []).forEach((oid) => {
        if (!idx.has(oid)) idx.set(oid, []);
        idx.get(oid).push(a);
      });
    });
    const rows = orgs.map((o) => ({
      org: o,
      admins: idx.get(o.id) || [],
    }));
    return rows
      .filter((r) => {
        if (onlyAttached && r.admins.length === 0) return false;
        if (!q) return true;
        return (
          (r.org.name || '').toLowerCase().includes(q) ||
          r.admins.some((a) =>
            (a.full_name || '').toLowerCase().includes(q) ||
            (a.email || '').toLowerCase().includes(q),
          )
        );
      })
      .sort((a, b) => (a.org.name || '').localeCompare(b.org.name || ''));
  }, [admins, orgs, query, onlyAttached]);

  // ── CSV exports ─────────────────────────────────────────────────────
  const exportCsv = () => {
    const ts = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    if (view === 'by-admin') {
      const rows = [['Admin name', 'Email', 'Role', 'Awaiting first login', 'Attached gym count', 'Attached gyms (semicolon-separated)']];
      adminsView.forEach((a) => {
        rows.push([
          a.full_name || '',
          a.email || '',
          'Pulse Platform Admin',
          a.must_change_password ? 'yes' : 'no',
          String((a.organization_memberships || []).length),
          (a.membership_org_names || []).map((m) => m.name).join('; '),
        ]);
      });
      downloadCsv(rows, `permissions-matrix-by-admin-${ts}.csv`);
    } else {
      const rows = [['Organisation', 'Org ID', 'Account type', 'Attached admin count', 'Attached admins (semicolon-separated)']];
      gymsView.forEach((r) => {
        rows.push([
          r.org.name || '',
          r.org.id,
          r.org.account_type || r.org.subscription_tier || '',
          String(r.admins.length),
          r.admins.map((a) => `${a.full_name} <${a.email}>`).join('; '),
        ]);
      });
      downloadCsv(rows, `permissions-matrix-by-gym-${ts}.csv`);
    }
    show({ tone: 'success', title: 'CSV exported', detail: 'Use this as the access-review evidence artefact for your next SOC 2 audit cycle.' });
  };

  // ── Render ──────────────────────────────────────────────────────────
  const totalAttachments = useMemo(
    () => admins.reduce((sum, a) => sum + (a.organization_memberships || []).length, 0),
    [admins],
  );
  const adminsWithAttachments = useMemo(
    () => admins.filter((a) => (a.organization_memberships || []).length > 0).length,
    [admins],
  );

  return (
    <div className="space-y-4" data-testid="permissions-matrix">
      {banner}

      {/* Summary tiles + controls */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3" data-testid="matrix-summary-tiles">
        <Card className="p-3 rounded-xl border-zinc-200">
          <p className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">Active admins</p>
          <p className="text-xl font-bold text-zinc-900 mt-0.5" data-testid="matrix-tile-admins">{admins.length}</p>
        </Card>
        <Card className="p-3 rounded-xl border-zinc-200">
          <p className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">With dual-role attachments</p>
          <p className="text-xl font-bold text-zinc-900 mt-0.5" data-testid="matrix-tile-with-attachments">{adminsWithAttachments}</p>
        </Card>
        <Card className="p-3 rounded-xl border-zinc-200">
          <p className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">Total attachments</p>
          <p className="text-xl font-bold text-zinc-900 mt-0.5" data-testid="matrix-tile-total-attachments">{totalAttachments}</p>
        </Card>
        <Card className="p-3 rounded-xl border-zinc-200">
          <p className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">Gyms in catalogue</p>
          <p className="text-xl font-bold text-zinc-900 mt-0.5" data-testid="matrix-tile-orgs">{orgs.length}</p>
        </Card>
      </div>

      {/* Toolbar */}
      <Card className="p-3 rounded-xl border-zinc-200">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="flex items-center gap-1 bg-zinc-100 rounded-full p-1" data-testid="matrix-view-switch">
            {VIEWS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setView(id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                  view === id ? 'bg-white shadow-sm text-zinc-900' : 'text-zinc-500 hover:text-zinc-700'
                }`}
                data-testid={`matrix-view-${id}`}
              >
                <Icon size={12} /> {label}
              </button>
            ))}
          </div>
          <div className="flex flex-1 items-center gap-2 md:max-w-xl md:ml-auto">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={view === 'by-admin' ? 'Search by admin, email, or gym…' : 'Search by gym or attached admin…'}
                className="pl-9 h-9 text-sm"
                data-testid="matrix-search"
              />
            </div>
            <Button
              type="button"
              variant={onlyAttached ? 'default' : 'outline'}
              size="sm"
              onClick={() => setOnlyAttached((v) => !v)}
              className={`text-xs h-9 ${onlyAttached ? 'bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]' : ''}`}
              data-testid="matrix-only-attached"
              title="Hide rows with zero attachments"
            >
              <Filter size={12} className="mr-1" /> Only attached
            </Button>
            <Button size="sm" variant="outline" onClick={load} disabled={loading} className="h-9 text-xs" data-testid="matrix-refresh">
              <RefreshCw size={12} className={`${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button size="sm" onClick={exportCsv} className="h-9 text-xs bg-zinc-900 hover:bg-zinc-800 text-white" data-testid="matrix-export-csv">
              <Download size={12} className="mr-1" /> Export CSV
            </Button>
          </div>
        </div>
      </Card>

      {/* Matrix table */}
      <Card className="rounded-xl border-zinc-200 overflow-hidden">
        {loading ? (
          <div className="p-5 space-y-3" data-testid="matrix-loading">
            {[0, 1, 2, 3].map((i) => <SkeletonLine key={i} width="100%" />)}
          </div>
        ) : view === 'by-admin' ? (
          <AdminMatrix rows={adminsView} orgLookup={orgLookup} />
        ) : (
          <GymMatrix rows={gymsView} />
        )}
      </Card>

      <div className="flex items-start gap-2 p-3 rounded-lg bg-zinc-50 border border-zinc-200 text-xs text-zinc-600" data-testid="matrix-soc2-hint">
        <ShieldCheck size={14} className="text-emerald-600 mt-0.5 shrink-0" />
        <p className="leading-relaxed">
          <strong>SOC 2 tip:</strong> export this matrix at the start of each quarterly access review.
          Compare against the previous quarter's CSV to spot stale attachments (e.g. ex-admins still bound to a gym, or admins added to too many gyms outside their scope).
        </p>
      </div>
    </div>
  );
};

// ── Sub-views ──────────────────────────────────────────────────────────

const AdminMatrix = ({ rows, orgLookup }) => {
  if (rows.length === 0) {
    return <p className="p-8 text-center text-sm text-zinc-400" data-testid="matrix-empty-admins">No admins match this filter.</p>;
  }
  return (
    <div className="divide-y divide-zinc-100">
      <div className="hidden md:grid grid-cols-[2fr_2fr_auto_3fr] gap-3 px-4 py-2.5 bg-zinc-50 text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">
        <span>Admin</span>
        <span>Email</span>
        <span>Attached</span>
        <span>Gyms</span>
      </div>
      {rows.map((a) => (
        <div
          key={a.id}
          className="grid grid-cols-1 md:grid-cols-[2fr_2fr_auto_3fr] gap-2 md:gap-3 px-4 py-3 hover:bg-zinc-50"
          data-testid={`matrix-admin-row-${a.id}`}
        >
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-full bg-zinc-100 grid place-items-center text-zinc-500 shrink-0">
              <Users size={12} />
            </div>
            <span className="text-sm font-medium text-zinc-900 truncate" data-testid={`matrix-admin-name-${a.id}`}>
              {a.full_name}
            </span>
            {a.must_change_password && (
              <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                pending
              </span>
            )}
          </div>
          <span className="text-xs text-zinc-500 truncate md:self-center" data-testid={`matrix-admin-email-${a.id}`}>
            {a.email}
          </span>
          <span className="text-xs font-mono md:self-center text-zinc-700 md:text-center" data-testid={`matrix-admin-count-${a.id}`}>
            {(a.organization_memberships || []).length}
          </span>
          <div className="flex flex-wrap gap-1.5 md:self-center">
            {(a.membership_org_names || []).length === 0 ? (
              <span className="text-[11px] text-zinc-400 italic">— cross-platform only —</span>
            ) : (
              a.membership_org_names.map((m) => {
                const accountType = orgLookup.get(m.id)?.account_type;
                return (
                  <Badge
                    key={m.id}
                    variant="outline"
                    className="text-[11px] gap-1 bg-blue-50 border-blue-200 text-blue-800"
                    data-testid={`matrix-admin-gym-${a.id}-${m.id}`}
                  >
                    <Building2 size={10} />
                    {m.name}
                    {accountType && <span className="text-[9px] text-blue-500 uppercase">· {accountType}</span>}
                  </Badge>
                );
              })
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

const GymMatrix = ({ rows }) => {
  if (rows.length === 0) {
    return <p className="p-8 text-center text-sm text-zinc-400" data-testid="matrix-empty-gyms">No gyms match this filter.</p>;
  }
  return (
    <div className="divide-y divide-zinc-100">
      <div className="hidden md:grid grid-cols-[3fr_auto_3fr] gap-3 px-4 py-2.5 bg-zinc-50 text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">
        <span>Gym</span>
        <span>Attached</span>
        <span>Admins</span>
      </div>
      {rows.map(({ org, admins: attached }) => (
        <div
          key={org.id}
          className="grid grid-cols-1 md:grid-cols-[3fr_auto_3fr] gap-2 md:gap-3 px-4 py-3 hover:bg-zinc-50"
          data-testid={`matrix-gym-row-${org.id}`}
        >
          <div className="flex items-center gap-2 min-w-0">
            <Building2 size={14} className="text-zinc-400 shrink-0" />
            <span className="text-sm font-medium text-zinc-900 truncate" data-testid={`matrix-gym-name-${org.id}`}>{org.name}</span>
            {(org.account_type || org.subscription_tier) && (
              <span className="text-[10px] uppercase tracking-wider text-zinc-400 shrink-0">
                · {org.account_type || org.subscription_tier}
              </span>
            )}
          </div>
          <span className="text-xs font-mono md:self-center text-zinc-700 md:text-center" data-testid={`matrix-gym-count-${org.id}`}>
            {attached.length}
          </span>
          <div className="flex flex-wrap gap-1.5 md:self-center">
            {attached.length === 0 ? (
              <span className="text-[11px] text-zinc-400 italic">— no admins attached —</span>
            ) : (
              attached.map((a) => (
                <Badge
                  key={a.id}
                  variant="outline"
                  className="text-[11px] gap-1 bg-emerald-50 border-emerald-200 text-emerald-800"
                  data-testid={`matrix-gym-admin-${org.id}-${a.id}`}
                  title={a.email}
                >
                  <Users size={10} />
                  {a.full_name}
                </Badge>
              ))
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default PermissionsMatrix;
