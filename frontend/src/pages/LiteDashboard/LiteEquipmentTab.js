import { useState, useEffect } from 'react';
import { resolveEquipmentPhoto } from '@/utils/photoUrl';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, ChevronRight, ChevronDown, Shield, Sparkles, Loader2, Plus, ArrowRightLeft, Trash2, MapPin, FileText, AlertTriangle, CheckSquare, Square, Check, X } from 'lucide-react';
import { useAuth } from '@/App';

// MOD SOR (Schedule C) service-tier definitions — shown as hover
// tooltips on the cover pills so operators know what each contract covers.
export const CONTRACT_TYPE_TOOLTIP = {
  A: 'Type A — All-inclusive 12-month service, repair & maintenance (UK only), fixed price. (MOD SOR)',
  B: 'Type B — One-off service, repair & maintenance (UK only), fixed price, used as required. (MOD SOR)',
  C: 'Type C — Overseas requirement incl. operational theatres: quoted repair & maintenance for equipment outside the UK. (MOD SOR)',
};
import { useTranslation } from 'react-i18next';
import { useInlineBanner, InlineProgress, notify, useConfirm } from '@/components/notifications';
import EquipmentPlaceholder from '@/components/equipment/EquipmentPlaceholder';
import HelpHint from '@/components/HelpHint';

const LiteEquipmentTab = ({
  filteredEquipment, search, onSearchChange,
  getEquipmentFaults, onSelectEquipment,
  _getSeverityStyle, _getSeverityLabel, _getStatusColor, onEquipmentUpdated,
  onAddEquipment, isPro = false,
}) => {
  const { API, sites, user } = useAuth();
  const { t } = useTranslation();
  const [bulkRunning, setBulkRunning] = useState(false);
  const { banner: bulkBanner, show: showBulkBanner } = useInlineBanner({ autoDismissMs: 8000 });
  const confirm = useConfirm();
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : '';
  // Iter 216h49 — owners/managers can move kit between sites + delete kit
  // directly from the list. `movingId` controls the inline site-picker
  // popover for one equipment row at a time.
  const [movingId, setMovingId] = useState(null);
  // Iter 2026-08-09 — collapse/expand each location zone so a large estate
  // list stays tidy. Persisted per-org in localStorage so the open/closed
  // state survives between visits.
  const collapseStorageKey = `pf-equip-collapsed-zones:${user?.organization_id || 'default'}`;
  const [collapsedZones, setCollapsedZones] = useState(() => {
    try {
      const raw = localStorage.getItem(collapseStorageKey);
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch { return new Set(); }
  });
  useEffect(() => {
    try { localStorage.setItem(collapseStorageKey, JSON.stringify(Array.from(collapsedZones))); } catch { /* noop */ }
  }, [collapsedZones, collapseStorageKey]);
  const toggleZone = (loc) => {
    setCollapsedZones((prev) => {
      const next = new Set(prev);
      if (next.has(loc)) next.delete(loc); else next.add(loc);
      return next;
    });
  };
  const canManageKit = user?.role === 'owner' || user?.role === 'manager' || user?.is_master_admin;
  const realSites = (sites || []).filter(s => !s.is_default);

  // Iter 2026-08-09 — Bulk "Move kit to a zone" (gym refit). Owners/managers
  // enter select mode, tick machines, then reassign them all to one location.
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkZone, setBulkZone] = useState('');
  const [bulkSite, setBulkSite] = useState('');
  const [bulkSaving, setBulkSaving] = useState(false);
  // Quick zone filter chips — jump straight to one location. null = All.
  const [zoneFilter, setZoneFilter] = useState(null);
  const zoneOptions = Array.from(
    new Set((filteredEquipment || []).map((e) => (e.location || '').trim()).filter(Boolean)),
  ).sort();
  const toggleSelectMode = () => {
    setSelectMode((on) => {
      if (on) { setSelectedIds(new Set()); setBulkZone(''); setBulkSite(''); }
      return !on;
    });
  };
  const toggleSelected = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const zoneAllSelected = (items) => items.length > 0 && items.every((e) => selectedIds.has(e.id));
  const toggleZoneSelectAll = (items) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const all = items.every((e) => next.has(e.id));
      items.forEach((e) => { if (all) next.delete(e.id); else next.add(e.id); });
      return next;
    });
  };
  const toggleSelectAllVisible = () => {
    setSelectedIds((prev) => {
      const all = (filteredEquipment || []).every((e) => prev.has(e.id));
      return all ? new Set() : new Set((filteredEquipment || []).map((e) => e.id));
    });
  };
  const undoBulkMove = async (moved) => {
    let ok = 0;
    for (const m of moved) {
      try {
        // Revert the site first (no-op if unchanged), then the location.
        if (m.prevSite) {
          try { await axios.post(`${API}/equipment/${m.id}/move`, { site_id: m.prevSite }, { headers: { Authorization: `Bearer ${token}` } }); } catch { /* skip site revert */ }
        }
        await axios.patch(
          `${API}/equipment/${m.id}`,
          { location: m.prev || '' },
          { headers: { Authorization: `Bearer ${token}` } },
        );
        ok += 1;
      } catch { /* skip */ }
    }
    if (ok > 0) {
      notify.success(`Reverted ${ok} ${ok === 1 ? 'machine' : 'machines'}`);
      onEquipmentUpdated && onEquipmentUpdated();
    } else {
      notify.error('Undo failed', 'Could not revert the move — try again.');
    }
  };
  const bulkMoveToZone = async () => {
    const zone = (bulkZone || '').trim();
    const targetSite = (bulkSite || '').trim();
    const targetSiteName = realSites.find((s) => s.id === targetSite)?.name;
    const ids = Array.from(selectedIds);
    if (!ids.length) { notify.error('Select at least one machine'); return; }
    // Snapshot each machine's current site + location so the move can be undone.
    const eqMap = new Map((filteredEquipment || []).map((e) => [e.id, e]));
    setBulkSaving(true);
    let failed = 0;
    const moved = [];
    for (const id of ids) {
      const eq = eqMap.get(id) || {};
      try {
        // Cross-site move first (if a different site was picked), then set the zone.
        if (targetSite && targetSite !== eq.site_id) {
          await axios.post(`${API}/equipment/${id}/move`, { site_id: targetSite }, { headers: { Authorization: `Bearer ${token}` } });
        }
        await axios.patch(
          `${API}/equipment/${id}`,
          { location: zone },
          { headers: { Authorization: `Bearer ${token}` } },
        );
        moved.push({ id, prev: (eq.location || '').trim(), prevSite: eq.site_id || '' });
      } catch { failed += 1; }
    }
    setBulkSaving(false);
    if (moved.length > 0) {
      const dest = targetSiteName
        ? `${targetSiteName}${zone ? ` · ${zone}` : ''}`
        : (zone || 'Unassigned');
      notify.success(
        `Moved ${moved.length} ${moved.length === 1 ? 'machine' : 'machines'} to ${dest}`,
        failed > 0 ? `${failed} could not be moved — try again.` : undefined,
        { ttl: 9000, action: { label: t('equip.bulk_undo', 'Undo'), onClick: () => undoBulkMove(moved) } },
      );
      setSelectMode(false);
      setSelectedIds(new Set());
      setBulkZone('');
      setBulkSite('');
      onEquipmentUpdated && onEquipmentUpdated();
    } else {
      notify.error('Move failed', 'None of the selected machines could be moved.');
    }
  };

  const moveEquipment = async (eqId, targetSiteId) => {
    try {
      const res = await axios.post(
        `${API}/equipment/${eqId}/move`,
        { site_id: targetSiteId },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      notify.success(
        res.data?.moved === false ? 'Already at that site' : 'Equipment moved',
        res.data?.to_site_name ? `Now at ${res.data.to_site_name}` : undefined,
      );
      setMovingId(null);
      onEquipmentUpdated && onEquipmentUpdated();
    } catch (e) {
      notify.error('Move failed', e?.response?.data?.detail || 'Try again or refresh.');
    }
  };

  const deleteEquipment = async (eq) => {
    const ok = await confirm({
      title: `Delete "${eq.name || 'this equipment'}"?`,
      detail: 'This permanently removes the kit and unlinks any open faults. Audit-logged. Cannot be undone.',
      tone: 'warning',
      confirmLabel: 'Delete kit',
    });
    if (!ok) return;
    try {
      await axios.delete(
        `${API}/equipment/${eq.id}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      notify.success('Equipment deleted');
      onEquipmentUpdated && onEquipmentUpdated();
    } catch (e) {
      notify.error('Delete failed', e?.response?.data?.detail || 'Try again.');
    }
  };

  const missingImages = filteredEquipment.filter(
    (eq) => !eq.photo_url && !eq.spec_sheet_id && !eq.auto_image_url
  ).length;

  // Iter 216h108 — chunked auto-lookup. Previously we called the
  // backend with limit=30 in one request — at ~3s/item that's ~90s,
  // which routinely exceeds the proxy timeout and produces the
  // generic "Network issue or upstream timeout" error users see.
  // Now we chunk client-side: 8 items per request, sequential, with
  // live progress. Total runs in the same wall-clock time but no
  // single request lasts more than ~25s.
  const [bulkProgress, setBulkProgress] = useState({ done: 0, total: 0, matched: 0 });
  const runBulkAutoLookup = async () => {
    if (bulkRunning) return;
    setBulkRunning(true);
    setBulkProgress({ done: 0, total: missingImages, matched: 0 });
    let totalMatched = 0;
    let totalExamined = 0;
    let totalSkipped = 0;
    let lastError = '';
    const CHUNK = 8;
    try {
      while (true) {
        const r = await axios.post(
          `${API}/equipment/lookup-images/batch?limit=${CHUNK}`,
          {},
          { headers: { Authorization: `Bearer ${token}` }, timeout: 60000 },
        );
        const examined = r.data?.total_examined || 0;
        totalExamined += examined;
        totalMatched += r.data?.matched || 0;
        totalSkipped += r.data?.skipped || 0;
        setBulkProgress((p) => ({
          done: p.done + examined,
          total: Math.max(p.total, p.done + examined),
          matched: totalMatched,
        }));
        // Stop when the backend returned fewer items than we asked
        // for — means we've exhausted the missing-image queue.
        if (examined < CHUNK) break;
      }
      showBulkBanner({
        tone: totalMatched > 0 ? 'success' : 'info',
        title: totalMatched > 0
          ? `Found ${totalMatched} new product ${totalMatched === 1 ? 'photo' : 'photos'}`
          : 'No matches this run',
        detail: totalMatched > 0
          ? `Checked ${totalExamined} machines · ${totalSkipped} didn't match a known manufacturer. Photos with an "AI?" badge need review.`
          : `Checked ${totalExamined} machines. Try ensuring the manufacturer field is spelled correctly, or upload a photo manually.`,
      });
      onEquipmentUpdated && onEquipmentUpdated();
    } catch (err) {
      lastError = err?.response?.data?.detail || err?.message || '';
      showBulkBanner({
        tone: 'error',
        title: 'Auto-lookup failed',
        detail: lastError
          ? `${lastError}. Already matched ${totalMatched} of ${totalExamined} checked so far — click again to resume.`
          : `Already matched ${totalMatched} of ${totalExamined} checked so far. Click again to resume, or check the manufacturer name spelling.`,
      });
    }
    setBulkRunning(false);
    setBulkProgress({ done: 0, total: 0, matched: 0 });
  };

  // Iter 2026-06 — group the equipment list by physical location with a
  // small header per zone (matches the Fault Wizard grouping) so operators
  // can find a machine faster. "Unassigned" always sorts last; headers only
  // show when there is more than one location.
  const UNASSIGNED_KEY = '__unassigned__';
  const equipmentGroups = (() => {
    const map = new Map();
    filteredEquipment.forEach((eq) => {
      const loc = (eq.location || '').trim() || UNASSIGNED_KEY;
      if (!map.has(loc)) map.set(loc, []);
      map.get(loc).push(eq);
    });
    const entries = Array.from(map.entries());
    entries.sort((a, b) => {
      if (a[0] === UNASSIGNED_KEY) return 1;
      if (b[0] === UNASSIGNED_KEY) return -1;
      return a[0].localeCompare(b[0]);
    });
    return entries;
  })();
  const showGroupHeaders = equipmentGroups.length > 1;
  // Reset a stale zone filter if that zone no longer exists (e.g. after a move).
  const zoneFilterActive = zoneFilter && equipmentGroups.some(([loc]) => loc === zoneFilter);
  const renderGroups = zoneFilterActive
    ? equipmentGroups.filter(([loc]) => loc === zoneFilter)
    : equipmentGroups;

  const renderEquipmentCard = (eq) => {
    const faults = getEquipmentFaults(eq);
    const openFaults = faults.filter(f => f.status !== 'resolved').length;
    const eqBorderColor = openFaults > 0 ? 'var(--color-danger)' : 'var(--color-success-alt-2)';
    const isSelected = selectedIds.has(eq.id);
    // Thumbnail fallback chain:
    //   1. Operator-uploaded on-site photo (best — ground truth)
    //   2. AI-matched manufacturer image (auto-lookup)
    //   3. Matched spec-sheet hero image (Pulse Fitness / Life Fitness / …)
    //   4. Machine-type logo placeholder (menu-bar pill style)
    const thumbUrl = resolveEquipmentPhoto(eq.photo_url)
      || eq.auto_image_url
      || (eq.spec_sheet_id ? `${API}/spec-sheets/image/${eq.spec_sheet_id}` : null);
    return (
      <Card key={eq.id} className="p-5 cursor-pointer hover:border-[rgb(var(--rgb-brand-cyan-hover)/0.3)] transition-all" style={{ background: 'var(--theme-surface, var(--color-surface-dark-alt))', borderLeft: `4px solid ${selectMode && isSelected ? 'var(--color-brand-cyan-hover)' : eqBorderColor}`, borderColor: selectMode && isSelected ? 'var(--color-brand-cyan-hover)' : eqBorderColor }} onClick={() => (selectMode ? toggleSelected(eq.id) : onSelectEquipment(eq))} data-testid={`lite-equip-${eq.id}`}>
        <div className="flex items-center gap-3">
          {selectMode && (
            <div className="shrink-0" data-testid={`lite-equip-select-${eq.id}`}>
              {isSelected
                ? <CheckSquare size={20} className="text-[var(--color-brand-cyan-hover)]" />
                : <Square size={20} className="text-[var(--color-text-muted)]" />}
            </div>
          )}
          <div className="relative w-10 h-10 rounded-lg overflow-hidden shrink-0">
            {/* Placeholder renders underneath — visible when no thumb,
                or when the img fails to load and hides itself. */}
            <EquipmentPlaceholder
              manufacturer={eq.manufacturer || eq.supplier}
              equipmentType={eq.equipment_type || eq.category}
              testId={`lite-equip-placeholder-${eq.id}`}
            />
            {thumbUrl && (
              <img
                src={thumbUrl}
                alt=""
                className="absolute inset-0 w-full h-full object-cover bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg"
                onError={(e) => { e.target.style.display = 'none'; }}
              />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white break-words leading-snug" data-testid={`lite-equip-name-${eq.id}`}>{eq.name}</p>
            {eq.serial_number && (
              <p className="text-[10px] font-mono text-[var(--color-text-muted)] truncate mt-0.5" data-testid={`lite-equip-serial-${eq.id}`}>
                S/N {eq.serial_number}
              </p>
            )}
            {eq.manufacturer && (
              <p className="text-xs text-[var(--color-text-muted)] truncate">{eq.manufacturer}</p>
            )}
            {eq.supplier && (
              <p className="text-[10px] text-indigo-400 truncate mt-0.5" data-testid={`lite-equip-supplier-${eq.id}`}>
                {t('equip.service_provider', 'Service Provider')}: {eq.supplier}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {openFaults > 0 && <Badge className="bg-red-500/15 text-red-400 border-0 text-xs">{openFaults} {openFaults > 1 ? t('faults.plural', 'faults') : t('faults.singular', 'fault')}</Badge>}
            {/* Cover pill. Warranty and contract are mutually exclusive:
                new kit ships with 1–4y warranty, then moves onto a
                Type A/B/C service contract once the warranty ends. */}
            {(() => {
              const today = new Date();
              const warrantyActive = eq.warranty_expiry && new Date(eq.warranty_expiry) > today;
              const ctype = (eq.contract_type || '').toUpperCase();
              const contractEnd = eq.contract_end_date || eq.sla_expiry || eq.service_contract_end;
              const contractActive = !!ctype || (contractEnd && new Date(contractEnd) > today);
              if (warrantyActive) {
                return (
                  <Badge className="bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold inline-flex items-center gap-1" data-testid={`lite-equip-pill-${eq.id}`}>
                    <Shield size={10} /> {t('equip.warranty', 'Warranty')}
                  </Badge>
                );
              }
              if (ctype && ['A', 'B', 'C'].includes(ctype)) {
                return (
                  <Badge className="bg-blue-500/15 text-blue-300 border border-blue-500/30 text-[10px] font-bold inline-flex items-center gap-1" data-testid={`lite-equip-pill-${eq.id}`} title={CONTRACT_TYPE_TOOLTIP[ctype]}>
                    <FileText size={10} /> {t(`equip.contract_type_${ctype.toLowerCase()}`, `Type ${ctype} Contract`)}
                  </Badge>
                );
              }
              if (contractActive) {
                return (
                  <Badge className="bg-blue-500/15 text-blue-300 border border-blue-500/30 text-[10px] font-bold inline-flex items-center gap-1" data-testid={`lite-equip-pill-${eq.id}`}>
                    <FileText size={10} /> {t('equip.under_contract', 'Under contract')}
                  </Badge>
                );
              }
              return (
                <Badge className="bg-zinc-500/15 text-zinc-300 border border-zinc-500/30 text-[10px] font-bold" data-testid={`lite-equip-pill-${eq.id}`}>
                  {t('equip.no_cover', 'No cover')}
                </Badge>
              );
            })()}
            {/* Iter 216h49 — owner/manager kit row actions. Stop
                propagation so clicks don't drill into the detail view.
                Hidden in bulk-select mode. */}
            {!selectMode && canManageKit && realSites.length > 1 && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-[var(--color-text-muted)] hover:text-white hover:bg-[var(--theme-surface-hover)]"
                onClick={(e) => { e.stopPropagation(); setMovingId(movingId === eq.id ? null : eq.id); }}
                data-testid={`lite-equip-move-${eq.id}`}
                title={t('equip.move_title', 'Move to another site')}
              >
                <ArrowRightLeft size={13} />
              </Button>
            )}
            {!selectMode && canManageKit && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-[var(--color-text-muted)] hover:text-red-400 hover:bg-red-500/10"
                onClick={(e) => { e.stopPropagation(); deleteEquipment(eq); }}
                data-testid={`lite-equip-delete-${eq.id}`}
                title={t('equip.delete_title', 'Delete kit')}
              >
                <Trash2 size={13} />
              </Button>
            )}
            {!selectMode && <ChevronRight size={16} className="text-[var(--color-text-muted)]" />}
          </div>
        </div>
        {movingId === eq.id && (
          <div
            onClick={(e) => e.stopPropagation()}
            className="mt-3 pt-3 border-t flex flex-col gap-1.5"
            style={{ borderColor: 'var(--theme-border)' }}
            data-testid={`lite-equip-move-picker-${eq.id}`}
          >
            <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
              {t('equip.move_prompt', { name: eq.name, defaultValue: 'Move "{{name}}" to which site?' })}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {realSites.map(s => (
                <Button
                  key={s.id}
                  type="button"
                  size="sm"
                  variant={s.id === eq.site_id ? 'secondary' : 'outline'}
                  disabled={s.id === eq.site_id}
                  className="h-8 text-xs"
                  onClick={() => moveEquipment(eq.id, s.id)}
                  data-testid={`lite-equip-move-target-${eq.id}-${s.id}`}
                >
                  <MapPin size={11} className="mr-1" />
                  {s.name}{s.id === eq.site_id ? ` (${t('equip.current', 'current')})` : ''}
                </Button>
              ))}
            </div>
          </div>
        )}
      </Card>
    );
  };

  return (
    <div className="space-y-4">
      {bulkBanner && <div>{bulkBanner}</div>}
      {bulkRunning && (
        <InlineProgress
          title={`Searching manufacturer websites… ${bulkProgress.done}/${bulkProgress.total || missingImages}`}
          detail={`Matched so far: ${bulkProgress.matched}. We process in chunks to avoid timeouts — leave the tab open while it runs.`}
        />
      )}
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" size={16} />
          <Input value={search} onChange={e => onSearchChange(e.target.value)} placeholder={t('equip.search', 'Search machines...')} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] pl-10 h-10" data-testid="lite-equip-search" />
        </div>
        <HelpHint guideId="service-equipment-photos" testId="help-hint-equipment" className="self-center" />
        {onAddEquipment && (
          <Button
            size="sm"
            className="h-10 text-xs bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
            onClick={onAddEquipment}
            data-testid="lite-equip-add-btn"
          >
            <Plus size={12} className="mr-1.5" /> {t('equip.add', 'Add equipment')}
          </Button>
        )}
        {/* Lite has no AI — the AI manufacturer-image lookup is Pro-only. */}
        {isPro && missingImages > 0 && (
          <Button
            size="sm"
            variant="outline"
            className="h-10 text-xs border-[var(--theme-border)] text-[var(--theme-text)] bg-[var(--theme-surface)] hover:bg-[var(--theme-surface)]"
            onClick={runBulkAutoLookup}
            disabled={bulkRunning}
            data-testid="lite-equip-auto-images"
          >
            {bulkRunning
              ? <><Loader2 size={12} className="mr-1.5 animate-spin" /> {t('equip.searching', 'Searching…')}</>
              : <><Sparkles size={12} className="mr-1.5" /> {t('equip.autofind', { count: missingImages, defaultValue: 'Auto-find {{count}} image' })}{missingImages > 1 ? t('equip.plural_s', 's') : ''}</>}
          </Button>
        )}
        {/* Bulk "Move kit to a zone" (gym refit) — owners/managers only. */}
        {canManageKit && filteredEquipment.length > 0 && !selectMode && (
          <Button
            size="sm"
            variant="outline"
            className="h-10 text-xs border-[var(--theme-border)] text-[var(--theme-text)] bg-[var(--theme-surface)] hover:bg-[var(--theme-surface)]"
            onClick={toggleSelectMode}
            data-testid="lite-equip-bulk-move-btn"
          >
            <ArrowRightLeft size={12} className="mr-1.5" /> {t('equip.bulk_move', 'Move kit')}
          </Button>
        )}
      </div>

      {/* Bulk-move action bar — appears in select mode. Tick machines, type or
          pick the target zone, Apply. Reassigns location for all selected. */}
      {selectMode && (
        <div className="sticky top-2 z-20 flex flex-col sm:flex-row sm:items-center gap-2 p-3 rounded-lg border border-[var(--color-brand-cyan-hover)]/40 bg-[var(--theme-surface)] shadow-lg" data-testid="lite-equip-bulk-bar">
          <div className="flex items-center gap-3 flex-1">
            <span className="text-sm font-semibold text-[var(--theme-text)]" data-testid="lite-equip-bulk-count">
              {t('equip.bulk_selected', { count: selectedIds.size, defaultValue: '{{count}} selected' })}
            </span>
            <button
              type="button"
              onClick={toggleSelectAllVisible}
              className="text-xs font-semibold text-[var(--color-brand-cyan-hover)] hover:underline"
              data-testid="lite-equip-bulk-selectall"
            >
              {(filteredEquipment || []).length > 0 && (filteredEquipment || []).every((e) => selectedIds.has(e.id))
                ? t('equip.bulk_clear', 'Clear all')
                : t('equip.bulk_selectall', 'Select all')}
            </button>
          </div>
          <div className="flex items-center gap-2">
            {realSites.length > 1 && (
              <select
                value={bulkSite}
                onChange={(e) => setBulkSite(e.target.value)}
                disabled={bulkSaving}
                className="h-9 w-full sm:w-40 px-2 rounded border border-[var(--theme-border)] bg-[var(--theme-surface)] text-[var(--theme-text)] text-sm focus:outline-none focus:border-[var(--color-brand-cyan-hover)]"
                data-testid="lite-equip-bulk-site-select"
              >
                <option value="">{t('equip.bulk_this_site', 'This site')}</option>
                {realSites.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            )}
            <input
              list="lite-equip-bulk-zone-list"
              value={bulkZone}
              onChange={(e) => setBulkZone(e.target.value)}
              placeholder={t('equip.bulk_zone_placeholder', 'Move to zone…')}
              maxLength={80}
              disabled={bulkSaving}
              className="h-9 w-full sm:w-48 px-2 rounded border border-[var(--theme-border)] bg-[var(--theme-surface)] text-[var(--theme-text)] text-sm focus:outline-none focus:border-[var(--color-brand-cyan-hover)]"
              data-testid="lite-equip-bulk-zone-input"
            />
            <datalist id="lite-equip-bulk-zone-list">
              {zoneOptions.map((l) => <option key={l} value={l} />)}
            </datalist>
            <Button
              size="sm"
              className="h-9 text-xs bg-[var(--color-brand-cyan-hover)] hover:opacity-90 text-white shrink-0"
              onClick={bulkMoveToZone}
              disabled={bulkSaving || selectedIds.size === 0}
              data-testid="lite-equip-bulk-apply"
            >
              {bulkSaving
                ? <><Loader2 size={12} className="mr-1.5 animate-spin" /> {t('equip.bulk_moving', 'Moving…')}</>
                : <><Check size={13} className="mr-1.5" /> {t('equip.bulk_apply', { count: selectedIds.size, defaultValue: 'Move {{count}}' })}</>}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-9 text-xs text-[var(--color-text-muted)] shrink-0"
              onClick={toggleSelectMode}
              disabled={bulkSaving}
              data-testid="lite-equip-bulk-cancel"
            >
              <X size={13} className="mr-1" /> {t('equip.bulk_cancel', 'Cancel')}
            </Button>
          </div>
        </div>
      )}

      {/* Zone summary cards — machine + open-fault counts per location at a glance.
          Click a card to filter to that zone. */}
      {showGroupHeaders && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2" data-testid="lite-equip-zone-summary">
          {equipmentGroups.map(([loc, items]) => {
            const zoneKey = loc === UNASSIGNED_KEY ? 'unassigned' : loc;
            const openFaults = items.reduce(
              (n, eq) => n + getEquipmentFaults(eq).filter(f => f.status !== 'resolved').length,
              0,
            );
            const active = zoneFilter === loc;
            return (
              <button
                key={loc}
                type="button"
                onClick={() => setZoneFilter(active ? null : loc)}
                className={`text-left p-3 rounded-lg border transition-colors ${active ? 'border-[var(--color-brand-cyan-hover)] bg-[rgb(var(--rgb-brand-cyan-hover)/0.08)]' : 'border-[var(--theme-border)] bg-[var(--theme-surface)] hover:border-[var(--color-brand-cyan-hover)]/50'}`}
                data-testid={`lite-equip-zone-summary-${zoneKey}`}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <MapPin size={12} className="text-[var(--color-text-muted)] shrink-0" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] truncate">
                    {loc === UNASSIGNED_KEY ? t('equip.unassigned_location', 'Unassigned') : loc}
                  </span>
                </div>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  <span className="text-2xl font-bold text-[var(--theme-text)] leading-none" data-testid={`lite-equip-zone-summary-count-${zoneKey}`}>{items.length}</span>
                  <span className="text-[10px] text-[var(--color-text-muted)]">{items.length === 1 ? t('equip.machine', 'machine') : t('equip.machines', 'machines')}</span>
                </div>
                {openFaults > 0 ? (
                  <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-bold text-red-400" data-testid={`lite-equip-zone-summary-faults-${zoneKey}`}>
                    <AlertTriangle size={9} /> {openFaults} {openFaults > 1 ? t('faults.plural', 'faults') : t('faults.singular', 'fault')}
                  </div>
                ) : (
                  <div className="mt-1 text-[10px] font-medium text-emerald-400" data-testid={`lite-equip-zone-summary-faults-${zoneKey}`}>
                    {t('equip.zone_no_faults', 'No open faults')}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Quick zone filter chips — jump straight to one location. */}
      {showGroupHeaders && (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="lite-equip-zone-chips">
          <button
            type="button"
            onClick={() => setZoneFilter(null)}
            className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full border transition-colors ${!zoneFilterActive ? 'bg-[var(--color-brand-cyan-hover)] text-white border-[var(--color-brand-cyan-hover)]' : 'bg-[var(--theme-surface)] text-[var(--color-text-muted)] border-[var(--theme-border)] hover:text-[var(--theme-text)]'}`}
            data-testid="lite-equip-zone-chip-all"
          >
            {t('equip.zone_all', 'All')} <span className="opacity-70">({filteredEquipment.length})</span>
          </button>
          {equipmentGroups.map(([loc, items]) => {
            const zoneKey = loc === UNASSIGNED_KEY ? 'unassigned' : loc;
            const active = zoneFilter === loc;
            return (
              <button
                key={loc}
                type="button"
                onClick={() => setZoneFilter(active ? null : loc)}
                className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full border transition-colors ${active ? 'bg-[var(--color-brand-cyan-hover)] text-white border-[var(--color-brand-cyan-hover)]' : 'bg-[var(--theme-surface)] text-[var(--color-text-muted)] border-[var(--theme-border)] hover:text-[var(--theme-text)]'}`}
                data-testid={`lite-equip-zone-chip-${zoneKey}`}
              >
                <MapPin size={11} className="opacity-80" />
                {loc === UNASSIGNED_KEY ? t('equip.unassigned_location', 'Unassigned') : loc}
                <span className="opacity-70">({items.length})</span>
              </button>
            );
          })}
        </div>
      )}

      <div className="space-y-2">
        {renderGroups.map(([loc, items]) => {
          const zoneKey = loc === UNASSIGNED_KEY ? 'unassigned' : loc;
          const collapsed = showGroupHeaders && collapsedZones.has(loc);
          const zoneOpenFaults = items.reduce(
            (n, eq) => n + getEquipmentFaults(eq).filter(f => f.status !== 'resolved').length,
            0,
          );
          return (
            <div key={loc} className="space-y-2" data-testid={`lite-equip-group-${zoneKey}`}>
              {showGroupHeaders && (
                <div className="flex items-center gap-1 pt-3 first:pt-0">
                  {selectMode && (
                    <button
                      type="button"
                      onClick={() => toggleZoneSelectAll(items)}
                      className="shrink-0 p-0.5"
                      title="Select all in this zone"
                      data-testid={`lite-equip-group-selectall-${zoneKey}`}
                    >
                      {zoneAllSelected(items)
                        ? <CheckSquare size={16} className="text-[var(--color-brand-cyan-hover)]" />
                        : <Square size={16} className="text-[var(--color-text-muted)]" />}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => toggleZone(loc)}
                    className="flex-1 flex items-center gap-2 group text-left"
                    aria-expanded={!collapsed}
                    data-testid={`lite-equip-group-toggle-${zoneKey}`}
                  >
                    {collapsed
                      ? <ChevronRight size={14} className="text-[var(--color-text-muted)] shrink-0 transition-transform group-hover:text-[var(--theme-text)]" />
                      : <ChevronDown size={14} className="text-[var(--color-text-muted)] shrink-0 transition-transform group-hover:text-[var(--theme-text)]" />}
                    <MapPin size={13} className="text-[var(--color-text-muted)] shrink-0" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] shrink-0 group-hover:text-[var(--theme-text)]" data-testid={`lite-equip-group-label-${zoneKey}`}>
                      {loc === UNASSIGNED_KEY ? t('equip.unassigned_location', 'Unassigned') : loc}
                    </h3>
                    <span className="text-[10px] text-[var(--color-text-muted)] shrink-0">({items.length})</span>
                    {zoneOpenFaults > 0 && (
                      <Badge className="bg-red-500/15 text-red-400 border-0 text-[10px] font-bold inline-flex items-center gap-1 shrink-0" data-testid={`lite-equip-group-faults-${zoneKey}`}>
                        <AlertTriangle size={9} /> {zoneOpenFaults} {zoneOpenFaults > 1 ? t('faults.plural', 'faults') : t('faults.singular', 'fault')}
                      </Badge>
                    )}
                    <div className="flex-1 h-px bg-[var(--theme-border)]" />
                  </button>
                </div>
              )}
              {!collapsed && items.map(renderEquipmentCard)}
            </div>
          );
        })}
        {filteredEquipment.length === 0 && <p className="text-center text-[var(--color-text-muted)] py-8 text-sm">{t('equip.no_equipment', 'No equipment found')}</p>}
      </div>
    </div>
  );
};

export default LiteEquipmentTab;
