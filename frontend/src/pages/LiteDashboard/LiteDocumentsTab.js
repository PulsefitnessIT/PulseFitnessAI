/**
 * LiteDocumentsTab — Pulse Pro / Lite documents centre.
 * (Iter 216j — full restore.)
 *
 * Operators wanted the original rich Documents experience back so they
 * could upload all Pulse Fitness manuals + RAMS + SOPs in one place and
 * have them AI-indexed. This tab re-introduces the full category set
 * (Manuals, Service Certs, Contracts, Risk Assessments, SOPs,
 * Compliance, Invoices, General, Other) plus the inline AI Q&A box.
 *
 * AI-indexed badge:
 *   Files with `ai_indexed: true` (set by /api/files/{id}/extract) get a
 *   green "AI" pill so operators can see at a glance which manuals are
 *   searchable. Files without it get a "Index" button that triggers
 *   extraction.
 */
import { useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  FileText, Shield, Upload, Eye, Download, Trash2, Receipt,
  ClipboardList, ClipboardCheck, ScrollText, FolderOpen, Sparkles, Loader2,
} from 'lucide-react';
import { useAuth } from '@/App';
import { useTranslation } from 'react-i18next';
import { notify } from '@/components/notifications';
import DocumentQA from '@/components/shared/DocumentQA';
import PageHeader from '@/components/shared/PageHeader';

// Category mapping — single source of truth for both filtering and the
// tab bar. Keys mirror the values stored on each File doc's `category`
// (some legacy aliases collapse into the canonical id).
const CATEGORY_MAP = [
  { id: 'general',             label: 'General',             icon: FolderOpen,      aliases: ['general', ''] },
  { id: 'manuals',             label: 'Manuals',             icon: FileText,        aliases: ['manuals', 'manual'] },
  { id: 'service-certificates',label: 'Service Certificates',icon: Shield,          aliases: ['service-certificates', 'certificates', 'cert'] },
  { id: 'contracts',           label: 'Contracts',           icon: ScrollText,      aliases: ['contracts', 'contract'] },
  { id: 'risk-assessments',    label: 'Risk Assessments',    icon: ClipboardList,   aliases: ['risk-assessments', 'risk_assessments', 'rams'] },
  { id: 'sops',                label: 'SOPs',                icon: ClipboardCheck,  aliases: ['sops', 'sop'] },
  { id: 'compliance',          label: 'Compliance',          icon: Shield,          aliases: ['compliance'] },
  { id: 'invoices',            label: 'Invoices',            icon: Receipt,         aliases: ['invoices', 'invoice'] },
];

const matchesCategory = (file, cat) => {
  const fileCat = (file.category || 'general').toLowerCase();
  return cat.aliases.includes(fileCat);
};

const LiteDocumentsTab = ({ files, onView, onDownload, onDelete, onUpload }) => {
  const { API } = useAuth();
  const { t } = useTranslation();
  // Iter 238 — translated category label (kebab-case id → snake_case key)
  const catLabel = (c) => t(`docs.cat_${c.id.replace(/-/g, '_')}`, c.label);
  const [activeDocTab, setActiveDocTab] = useState('manuals');
  const [indexing, setIndexing] = useState({}); // { [fileId]: bool }
  // Iter 216h49 — drag-and-drop dropzone matching the spec-sheet pattern.
  // `dragOver` flips the dropzone styling; the dragenter/over/leave/drop
  // handlers stopPropagation so the GlobalDragGuard doesn't intercept.
  const [dragOver, setDragOver] = useState(false);

  // Build the filtered set per category, plus a catch-all "Other" for
  // anything stored under a non-canonical category.
  const knownAliases = new Set(CATEGORY_MAP.flatMap((c) => c.aliases));
  const otherFiles = files.filter((f) => !knownAliases.has((f.category || 'general').toLowerCase()));
  const tabs = [
    ...CATEGORY_MAP.map((c) => ({ ...c, items: files.filter((f) => matchesCategory(f, c)) })),
    ...(otherFiles.length > 0 ? [{ id: 'other', label: 'Other', icon: FolderOpen, items: otherFiles }] : []),
  ];

  const activeSection = tabs.find((t) => t.id === activeDocTab) || tabs[0];

  const _totalIndexed = files.filter((f) => f.ai_extracted).length;
  const _totalIndexable = files.filter((f) => /\.(pdf|docx?|txt)$/i.test(f.original_filename || '')).length;

  const handleIndex = async (file) => {
    setIndexing((prev) => ({ ...prev, [file.id]: true }));
    try {
      await axios.post(`${API}/files/${file.id}/extract`, {}, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
      });
      notify.success('AI indexed', `${file.original_filename} is now searchable via Document Q&A`);
      // Mutate the local state optimistically so the UI flips to the
      // "AI" badge without forcing a parent reload. The parent's next
      // /files/list call will reconcile.
      file.ai_extracted = true;
    } catch (err) {
      notify.error('Indexing failed', err?.response?.data?.detail || 'Could not extract text from this file. Try a different format.');
    } finally {
      setIndexing((prev) => ({ ...prev, [file.id]: false }));
    }
  };

  return (
    <div className="space-y-5" data-testid="lite-documents-tab">
      <PageHeader
        title={t('dashboard.documents', 'Documents')}
        subtitle={t('docs.subtitle', 'Manuals, certificates, RAMS, SOPs and invoices — AI-indexed for fast lookup')}
        icon={FileText}
        testId="lite-documents-header"
      />

      {/* AI Q&A panel — operators ask "what does our Matrix Treadmill
          T7xe service procedure say about belt tension?" and the LLM
          answers from the indexed manuals. Iter 216bn — the headline
          AI-indexing status card was removed per Lee's feedback; the
          indexing still happens (per-file Index button + auto-trigger
          on upload), users just don't need a percentage gauge cluttering
          the page. */}
      <DocumentQA compact />

      {/* Iter 216h49 — Drag-and-drop dropzone. Matches the spec-sheet
          pattern (AdminSpecSheets) so the gesture is consistent across
          the platform. Always uploads into the *currently active* category
          tab so operators can drag a Matrix T75 manual onto the Manuals
          tab and have it auto-categorised. */}
      {onUpload ? (
        <div
          className={`p-6 border-2 border-dashed rounded-xl text-center cursor-pointer transition-colors ${
            dragOver ? 'border-[var(--color-brand-blue)] bg-[var(--color-brand-blue)]/5' : ''
          }`}
          style={{
            borderColor: dragOver ? 'var(--color-brand-blue)' : 'var(--theme-border)',
            background: dragOver ? 'rgb(var(--rgb-brand-cyan-hover) / 0.04)' : 'transparent',
          }}
          onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); }}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); setDragOver(false); }}
          onDrop={(e) => {
            e.preventDefault(); e.stopPropagation(); setDragOver(false);
            if (activeDocTab !== 'other') onUpload(e.dataTransfer?.files, activeDocTab);
          }}
          onClick={() => {
            // Trigger the hidden input for the currently active category
            const el = document.getElementById(`doc-dropzone-input-${activeDocTab}`);
            if (el) el.click();
          }}
          data-testid="doc-dropzone"
        >
          <input
            id={`doc-dropzone-input-${activeDocTab}`}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt"
            className="hidden"
            onChange={(e) => onUpload(e, activeDocTab)}
            data-testid="doc-dropzone-input"
          />
          <Upload size={22} className="mx-auto mb-2" style={{ color: 'var(--color-brand-blue)' }} />
          <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>
            {t('docs.drop_files', 'Drop files here or click to browse')}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
            {t('docs.upload_hint_pre', 'Files will upload into the active')} <strong>{activeDocTab.replace(/-/g, ' ')}</strong> {t('docs.upload_hint_post', 'tab. Progress shows in the bottom-right drawer.')}
          </p>
        </div>
      ) : null}

      {/* Category tab bar */}
      <div
        className="flex gap-1 p-1 rounded-lg overflow-x-auto"
        style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}
        data-testid="doc-tab-bar"
      >
        {tabs.map((tab) => {
          const active = activeDocTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveDocTab(tab.id)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap"
              style={{
                background: active ? 'rgb(var(--rgb-brand-cyan-hover) / 0.15)' : 'transparent',
                color: active ? 'var(--color-brand-cyan-hover)' : 'var(--theme-text-muted)',
              }}
              data-testid={`doc-tab-${tab.id}`}
            >
              <tab.icon size={14} />
              {catLabel(tab)}
              <Badge
                className="ml-1 text-[10px] px-1.5 py-0"
                style={{
                  background: active ? 'rgb(var(--rgb-brand-cyan-hover) / 0.2)' : 'var(--theme-surface-2)',
                  color: active ? 'var(--color-brand-cyan-hover)' : 'var(--theme-text-muted)',
                }}
              >
                {tab.items.length}
              </Badge>
            </button>
          );
        })}
      </div>

      {/* Active section — file list + upload CTA */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{catLabel(activeSection)}</p>
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            {t('docs.file_count', { count: activeSection.items.length, defaultValue: '{{count}} file' })}{activeSection.items.length !== 1 ? t('equip.plural_s', 's') : ''}
          </p>
        </div>
        {onUpload && activeSection.id !== 'other' ? (
          <label className="cursor-pointer" data-testid={`doc-upload-label-${activeSection.id}`}>
            <input
              type="file"
              className="hidden"
              onChange={(e) => onUpload(e, activeSection.id)}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt"
              data-testid="doc-upload-input"
            />
            <span
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md font-semibold cursor-pointer transition-opacity hover:opacity-90"
              style={{ background: 'var(--color-brand-blue)', color: '#fff' }}
            >
              <Upload size={12} /> {t('docs.upload_to', 'Upload to')} {catLabel(activeSection)}
            </span>
          </label>
        ) : null}
      </div>

      <Card style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        {activeSection.items.length > 0 ? (
          <div className="divide-y" style={{ borderColor: 'var(--theme-border)' }}>
            {activeSection.items.map((f) => {
              const indexable = /\.(pdf|docx?|txt)$/i.test(f.original_filename || '');
              return (
                <div
                  key={f.id}
                  className="p-3 flex items-center gap-3 hover:opacity-95"
                  data-testid={`lite-doc-${f.id}`}
                >
                  <FileText size={16} className="flex-shrink-0" style={{ color: 'var(--theme-text-muted)' }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm truncate" style={{ color: 'var(--theme-text)' }}>{f.original_filename}</p>
                      {f.ai_extracted ? (
                        <Badge
                          className="text-[9px] font-bold px-1.5 py-0"
                          style={{ background: 'rgb(16 185 129 / 0.15)', color: '#059669', border: '1px solid rgb(16 185 129 / 0.3)' }}
                          data-testid={`lite-doc-indexed-${f.id}`}
                        >
                          <Sparkles size={9} className="mr-0.5 inline" /> AI
                        </Badge>
                      ) : null}
                    </div>
                    <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                      {f.created_at ? new Date(f.created_at).toLocaleDateString() : ''}
                      {f.supplier_name ? ` · ${f.supplier_name}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    {indexable && !f.ai_extracted ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs"
                        style={{ borderColor: 'var(--theme-border)', color: 'var(--color-brand-blue)' }}
                        onClick={() => handleIndex(f)}
                        disabled={!!indexing[f.id]}
                        data-testid={`lite-doc-index-${f.id}`}
                      >
                        {indexing[f.id] ? <Loader2 size={12} className="animate-spin" /> : <><Sparkles size={12} className="mr-1" /> Index</>}
                      </Button>
                    ) : null}
                    <Button size="sm" variant="outline" className="h-8" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} onClick={() => onView(f)} data-testid={`lite-doc-view-${f.id}`}><Eye size={14} /></Button>
                    <Button size="sm" variant="outline" className="h-8" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} onClick={() => onDownload(f)} data-testid={`lite-doc-download-${f.id}`}><Download size={14} /></Button>
                    <Button size="sm" variant="outline" className="h-8 text-red-400 hover:bg-red-500/10" style={{ borderColor: 'var(--theme-border)' }} onClick={() => onDelete(f)} data-testid={`lite-doc-delete-${f.id}`}><Trash2 size={14} /></Button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-10 text-center">
            <activeSection.icon size={28} className="mx-auto mb-2 opacity-30" style={{ color: 'var(--theme-text-muted)' }} />
            <p className="text-sm mb-3" style={{ color: 'var(--theme-text-muted)' }}>
              {t('docs.none_yet', { cat: catLabel(activeSection).toLowerCase(), defaultValue: 'No {{cat}} uploaded yet.' })}
            </p>
            {onUpload && activeSection.id !== 'other' ? (
              <label className="cursor-pointer">
                <input
                  type="file"
                  className="hidden"
                  onChange={(e) => onUpload(e, activeSection.id)}
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt"
                  data-testid={`doc-empty-upload-input-${activeSection.id}`}
                />
                <span
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md font-semibold cursor-pointer"
                  style={{ background: 'var(--color-brand-blue)', color: '#fff' }}
                >
                  <Upload size={12} /> {t('docs.upload_first', { cat: catLabel(activeSection).toLowerCase().replace(/s$/, ''), defaultValue: 'Upload your first {{cat}}' })}
                </span>
              </label>
            ) : null}
          </div>
        )}
      </Card>
    </div>
  );
};

export default LiteDocumentsTab;
