/**
 * Master Admin Command Palette (⌘K / Ctrl+K).
 *
 * One global hotkey, two data sources:
 *   1. Static section list (from SidebarConfig) — jumps to ?section=<id>.
 *   2. Live organisation list — opens the org panel directly.
 *
 * Designed to stay tiny and additive — does not touch any existing
 * navigation or org-list code path. The palette closes itself on
 * Escape, click outside, or after a successful action.
 *
 * Mounted once near the root of MasterAdminPage so every section
 * inherits it automatically.
 */
import React, { useEffect, useState } from 'react';
import {
  Command, Building2, ArrowRight, Search,
} from 'lucide-react';

import {
  CommandDialog, CommandInput, CommandList, CommandEmpty, CommandItem, CommandGroup, CommandSeparator,
} from '@/components/ui/command';

import { SIDEBAR_ITEMS } from './SidebarConfig';

const allSections = (gymaxisOnly) => {
  const out = [];
  SIDEBAR_ITEMS.forEach((it) => {
    // Respect Pulse-admin scope: hide gymaxis-only sections from Pulse Admins.
    if (it.gymaxisOnly && !gymaxisOnly) return;
    const groupLabel = (it.group || 'main').replace('-', ' ');
    out.push({
      id: it.id,
      label: it.label,
      groupLabel,
      icon: it.icon,
    });
    // Sub-tabs are jumpable too if declared.
    (it.subTabs || []).forEach((st) => {
      if (st.gymaxisOnly && !gymaxisOnly) return;
      out.push({
        id: st.id,
        label: `${it.label} → ${st.label}`,
        groupLabel,
        icon: it.icon,
        isSubTab: true,
      });
    });
  });
  return out;
};

export default function CommandPalette({ orgs = [], onJumpSection, onOpenOrg, isPulseAdmin = false }) {
  const [open, setOpen] = useState(false);

  // Global hotkey: ⌘K / Ctrl+K.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((cur) => !cur);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const sections = React.useMemo(() => allSections(!isPulseAdmin), [isPulseAdmin]);

  const handleSection = (sectionId) => {
    setOpen(false);
    onJumpSection?.(sectionId);
  };

  const handleOrg = (org) => {
    setOpen(false);
    onOpenOrg?.(org);
  };

  return (
    <>
      {/* Floating keyboard hint pill — only shows on desktop */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hidden md:inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-white hover:bg-zinc-50 px-2.5 py-1.5 text-xs font-medium text-zinc-500 transition-colors"
        title="Open command palette (⌘K)"
        data-testid="command-palette-trigger"
      >
        <Search size={12} />
        <span>Search anything…</span>
        <span className="ml-2 inline-flex items-center gap-1 rounded border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 text-[10px] font-bold text-zinc-500">
          <Command size={9} /> K
        </span>
      </button>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          placeholder="Jump to a section, find an org, run a command…"
          data-testid="command-palette-input"
        />
        <CommandList>
          <CommandEmpty>No results.</CommandEmpty>

          <CommandGroup heading="Sections">
            {sections.map((s) => {
              const Icon = s.icon;
              return (
                <CommandItem
                  key={`sec-${s.id}`}
                  value={`section ${s.label} ${s.groupLabel} ${s.id}`}
                  onSelect={() => handleSection(s.id)}
                  data-testid={`command-section-${s.id}`}
                  className="cursor-pointer"
                >
                  {Icon && <Icon size={14} className="mr-2 text-zinc-500" />}
                  <span className="flex-1">{s.label}</span>
                  <span className="text-[10px] uppercase tracking-wider text-zinc-400">{s.groupLabel}</span>
                  <ArrowRight size={11} className="ml-2 text-zinc-300" />
                </CommandItem>
              );
            })}
          </CommandGroup>

          {orgs && orgs.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Organisations">
                {orgs.slice(0, 50).map((o) => (
                  <CommandItem
                    key={`org-${o.id}`}
                    value={`org ${o.name} ${o.id} ${o.account_type || ''} ${o.portal_type || ''}`}
                    onSelect={() => handleOrg(o)}
                    data-testid={`command-org-${o.id}`}
                    className="cursor-pointer"
                  >
                    <Building2 size={14} className="mr-2 text-zinc-500" />
                    <span className="flex-1 truncate">{o.name}</span>
                    <span className="text-[10px] uppercase tracking-wider text-zinc-400">
                      {o.is_test ? 'TEST · ' : ''}{o.account_type || o.portal_type || 'org'}
                    </span>
                    <ArrowRight size={11} className="ml-2 text-zinc-300" />
                  </CommandItem>
                ))}
                {orgs.length > 50 && (
                  <div className="px-3 py-2 text-[11px] text-zinc-400">
                    Showing first 50 of {orgs.length}. Refine your search to see more.
                  </div>
                )}
              </CommandGroup>
            </>
          )}
        </CommandList>
      </CommandDialog>
    </>
  );
}
