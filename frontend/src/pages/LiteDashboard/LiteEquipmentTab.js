import { useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, ChevronRight, Shield, Sparkles, Loader2, Plus, ArrowRightLeft, Trash2, MapPin, FileText } from 'lucide-react';
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
  const canManageKit = user?.role === 'owner' || user?.role === 'manager' || user?.is_master_admin;
  const realSites = (sites || []).filter(s => !s.is_default);

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
      </div>

      <div className="space-y-2">
        {filteredEquipment.map(eq => {
          const faults = getEquipmentFaults(eq);
          const openFaults = faults.filter(f => f.status !== 'resolved').length;
          const eqBorderColor = openFaults > 0 ? 'var(--color-danger)' : 'var(--color-success-alt-2)';
          // Thumbnail fallback chain:
          //   1. Operator-uploaded on-site photo (best — ground truth)
          //   2. AI-matched manufacturer image (auto-lookup)
          //   3. Matched spec-sheet hero image (Pulse Fitness / Life Fitness / …)
          //   4. Machine-type logo placeholder (menu-bar pill style)
          // The img.onError handler falls back through each layer in turn so
          // a broken spec-sheet URL still lands on the placeholder.
          const thumbUrl = eq.photo_url
            || eq.auto_image_url
            || (eq.spec_sheet_id ? `${API}/spec-sheets/image/${eq.spec_sheet_id}` : null);
          return (
            <Card key={eq.id} className="p-5 cursor-pointer hover:border-[rgb(var(--rgb-brand-cyan-hover)/0.3)] transition-all" style={{ background: 'var(--theme-surface, var(--color-surface-dark-alt))', borderLeft: `4px solid ${eqBorderColor}`, borderColor: eqBorderColor }} onClick={() => onSelectEquipment(eq)} data-testid={`lite-equip-${eq.id}`}>
              <div className="flex items-center gap-3">
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
                      propagation so clicks don't drill into the detail view. */}
                  {canManageKit && realSites.length > 1 && (
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
                  {canManageKit && (
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
                  <ChevronRight size={16} className="text-[var(--color-text-muted)]" />
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
        })}
        {filteredEquipment.length === 0 && <p className="text-center text-[var(--color-text-muted)] py-8 text-sm">{t('equip.no_equipment', 'No equipment found')}</p>}
      </div>
    </div>
  );
};

export default LiteEquipmentTab;
