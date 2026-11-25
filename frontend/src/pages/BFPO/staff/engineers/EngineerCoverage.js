import { Badge } from '../../ui';

const STATUS = {
  territory_and_sites: ['Territory + sites', 'bg-emerald-50 text-emerald-700 border-emerald-200'],
  territory: ['Territory-wide', 'bg-emerald-50 text-emerald-700 border-emerald-200'],
  sites: ['Specific sites only', 'bg-cyan-50 text-cyan-700 border-cyan-200'],
  none: ['No coverage', 'bg-red-50 text-red-700 border-red-200'],
};

export function CoverageBadge({ coverage, testid }) {
  const [label, cls] = STATUS[coverage?.status || 'none'];
  return <Badge className={cls} data-testid={testid}>{label}</Badge>;
}

export function loginStatus(m) {
  if (!m.is_active) return ['Deactivated — cannot sign in', 'bg-slate-200 text-slate-600 border-slate-300'];
  if (m.invite_pending) return ['Invite sent — not signed in yet', 'bg-amber-50 text-amber-700 border-amber-200'];
  if (m.must_change_password) return ['Temporary password — must change on sign-in', 'bg-blue-50 text-blue-700 border-blue-200'];
  if (m.last_login) return [`Last signed in ${new Date(m.last_login).toLocaleDateString('en-GB')}`, 'bg-slate-50 text-slate-600 border-slate-200'];
  return ['Never signed in', 'bg-amber-50 text-amber-700 border-amber-200'];
}

export function EngineerCoverage({ m }) {
  const c = m.coverage || { territories: [], sites: [], issues: [], countries: [] };
  const terr = c.territories.filter((t) => !t.missing);
  const sites = c.sites.filter((s) => !s.missing);
  return (
    <div className="text-xs mt-1 space-y-0.5" data-testid={`engineer-coverage-${m.id}`}>
      <p className="text-slate-500" data-testid={`engineer-territories-${m.id}`}>
        <span className="font-semibold text-slate-600">Territories: </span>
        {terr.length ? terr.map((t) => t.name).join(', ') : 'none (no territory-wide access)'}
      </p>
      <p className="text-slate-500" data-testid={`engineer-sites-${m.id}`}>
        <span className="font-semibold text-slate-600">Specific sites: </span>
        {sites.length ? sites.map((s) => s.name).join(', ') : 'none'}
      </p>
      {c.countries.length > 1 && <p className="text-slate-400">Covers {c.countries.join(', ')}</p>}
      {c.issues.map((i) => <p key={i} className="text-amber-700" data-testid={`engineer-issue-${m.id}`}>{i}</p>)}
    </div>
  );
}
