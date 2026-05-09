import React, { useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Wrench, Search, ChevronRight, Shield, Camera, Sparkles, Loader2, Plus } from 'lucide-react';
import { useAuth } from '@/App';
import { useInlineBanner, InlineProgress } from '@/components/notifications';
import EquipmentPlaceholder from '@/components/equipment/EquipmentPlaceholder';
import HelpHint from '@/components/HelpHint';

const LiteEquipmentTab = ({
  filteredEquipment, search, onSearchChange,
  getEquipmentFaults, onSelectEquipment,
  getSeverityStyle, getSeverityLabel, getStatusColor, onEquipmentUpdated,
  onAddEquipment,
}) => {
  const { API } = useAuth();
  const [bulkRunning, setBulkRunning] = useState(false);
  const { banner: bulkBanner, show: showBulkBanner } = useInlineBanner({ autoDismissMs: 8000 });
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : '';
  const missingImages = filteredEquipment.filter(
    (eq) => !eq.photo_url && !eq.spec_sheet_id && !eq.auto_image_url
  ).length;

  const runBulkAutoLookup = async () => {
    if (bulkRunning) return;
    setBulkRunning(true);
    try {
      const r = await axios.post(
        `${API}/equipment/lookup-images/batch?limit=30`,
        {},
        { headers: { Authorization: `Bearer ${token}` } },
      );
      const { matched, total_examined, skipped } = r.data;
      showBulkBanner({
        tone: matched > 0 ? 'success' : 'info',
        title: matched > 0 ? `Found ${matched} new product ${matched === 1 ? 'photo' : 'photos'}` : 'No matches this run',
        detail: matched > 0
          ? `Checked ${total_examined} machines · ${skipped} didn't match a known manufacturer. Photos with an "AI?" badge need review.`
          : `Checked ${total_examined} machines. Try ensuring the manufacturer field is spelled correctly, or upload a photo manually.`,
      });
      onEquipmentUpdated && onEquipmentUpdated();
    } catch {
      showBulkBanner({
        tone: 'error',
        title: 'Auto-lookup failed',
        detail: 'Network issue or upstream timeout. Please try again in a moment.',
      });
    }
    setBulkRunning(false);
  };

  return (
    <div className="space-y-4">
      {bulkBanner && <div>{bulkBanner}</div>}
      {bulkRunning && (
        <InlineProgress
          title="Searching manufacturer websites…"
          detail="Checking each machine against known brands and verifying matches with AI. This takes ~3s per item."
        />
      )}
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" size={16} />
          <Input value={search} onChange={e => onSearchChange(e.target.value)} placeholder="Search machines..." className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] pl-10 h-10" data-testid="lite-equip-search" />
        </div>
        <HelpHint guideId="service-equipment-photos" testId="help-hint-equipment" className="self-center" />
        {onAddEquipment && (
          <Button
            size="sm"
            className="h-10 text-xs bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
            onClick={onAddEquipment}
            data-testid="lite-equip-add-btn"
          >
            <Plus size={12} className="mr-1.5" /> Add equipment
          </Button>
        )}
        {missingImages > 0 && (
          <Button
            size="sm"
            variant="outline"
            className="h-10 text-xs border-[var(--theme-border)] text-[var(--theme-text)] bg-[var(--theme-surface)] hover:bg-[var(--theme-surface)]"
            onClick={runBulkAutoLookup}
            disabled={bulkRunning}
            data-testid="lite-equip-auto-images"
          >
            {bulkRunning
              ? <><Loader2 size={12} className="mr-1.5 animate-spin" /> Searching…</>
              : <><Sparkles size={12} className="mr-1.5" /> Auto-find {missingImages} image{missingImages > 1 ? 's' : ''}</>}
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
                  <p className="text-sm font-medium text-white truncate" data-testid={`lite-equip-name-${eq.id}`}>{eq.name}</p>
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
                      Supplier: {eq.supplier}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {openFaults > 0 && <Badge className="bg-red-500/15 text-red-400 border-0 text-xs">{openFaults} fault{openFaults > 1 ? 's' : ''}</Badge>}
                  {eq.warranty_expiry && new Date(eq.warranty_expiry) > new Date() && <Shield size={14} className="text-emerald-400" />}
                  <ChevronRight size={16} className="text-[var(--color-text-muted)]" />
                </div>
              </div>
            </Card>
          );
        })}
        {filteredEquipment.length === 0 && <p className="text-center text-[var(--color-text-muted)] py-8 text-sm">No equipment found</p>}
      </div>
    </div>
  );
};

export default LiteEquipmentTab;
