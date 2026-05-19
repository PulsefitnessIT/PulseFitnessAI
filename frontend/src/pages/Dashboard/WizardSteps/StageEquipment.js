import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import {
  UploadCloud, Sparkles, Plus, Trash2, Download, Info, ArrowRight, Loader2,
} from 'lucide-react';
import { StageIntro, StageFooter } from './SharedBits';

const StageEquipment = ({
  mode, setMode, rows, addRow, removeRow, updateRow,
  onSaveManual, onDownloadTemplate,
  csvFile, setCsvFile, csvImporting, onCsvUpload,
  onSkip, saving, alreadyDone,
}) => {
  const modes = [
    { id: 'csv',     label: 'Upload CSV',     icon: UploadCloud, hint: 'Best for 10+ machines' },
    { id: 'invoice', label: 'Invoice (AI)',   icon: Sparkles,    hint: 'Upload a PDF invoice — we\'ll parse it' },
    { id: 'manual',  label: 'Manual entry',   icon: Plus,        hint: 'Quick form for small lists' },
  ];

  return (
    <div className="space-y-5" data-testid="stage-equipment">
      <StageIntro title="Import your equipment" blurb="This is where the magic happens — every machine in the system unlocks AI triage, automated audits, and warranty tracking."
        badge="Stage 2 / 4" alreadyDone={alreadyDone} />

      {/* Mode selector */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {modes.map(m => {
          const Icon = m.icon; const active = mode === m.id;
          return (
            <button key={m.id} type="button" onClick={() => setMode(m.id)}
              className={`text-left p-3 rounded-lg border transition-all ${active ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.1)]' : 'border-[var(--theme-border)] bg-[var(--theme-surface)] hover:border-white/30'}`}
              data-testid={`equip-mode-${m.id}`}>
              <div className="flex items-center gap-2 mb-1">
                <Icon size={14} className={active ? 'text-[var(--color-brand-blue)]' : 'text-[var(--color-text-muted)]'} />
                <span className="text-sm font-medium text-white">{m.label}</span>
              </div>
              <p className="text-[10px] text-[var(--color-text-muted)]">{m.hint}</p>
            </button>
          );
        })}
      </div>

      {mode === 'csv' && (
        <div className="space-y-3" data-testid="equip-csv-panel">
          <div className="bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg p-4 flex items-center gap-3">
            <Info size={16} className="text-[var(--color-brand-blue)]" />
            <p className="text-sm text-[var(--color-text-muted)]">Download the template, fill it in, then drag-and-drop below.</p>
            <Button type="button" size="sm" variant="outline" onClick={onDownloadTemplate} className="ml-auto border-[var(--theme-border)] text-white" data-testid="download-template-btn">
              <Download size={14} className="mr-1" /> Template
            </Button>
          </div>
          <label className="block">
            <input type="file" accept=".csv" className="hidden" onChange={e => setCsvFile(e.target.files?.[0] || null)} data-testid="csv-file-input" />
            <div className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${csvFile ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-[var(--theme-border)] hover:border-[rgb(var(--rgb-brand-blue)/0.5)]'}`}>
              <UploadCloud size={24} className="mx-auto text-[var(--color-text-muted)] mb-2" />
              <p className="text-sm text-white">{csvFile ? csvFile.name : 'Click or drop a CSV file here'}</p>
              {csvFile && <p className="text-[10px] text-[var(--color-text-muted)] mt-1">Ready to import</p>}
            </div>
          </label>
          {csvFile && (
            <Button type="button" onClick={onCsvUpload} disabled={csvImporting} className="bg-[var(--color-brand-blue)] text-white w-full" data-testid="csv-import-btn">
              {csvImporting ? <><Loader2 size={14} className="mr-2 animate-spin" /> Importing...</> : <>Import {csvFile.name} <ArrowRight size={14} className="ml-2" /></>}
            </Button>
          )}
        </div>
      )}

      {mode === 'invoice' && (
        <div className="bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg p-6 text-center" data-testid="equip-invoice-panel">
          <Sparkles size={24} className="mx-auto text-[var(--color-brand-blue)] mb-2" />
          <p className="text-sm text-white font-medium mb-1">AI Invoice Import</p>
          <p className="text-xs text-[var(--color-text-muted)] mb-4">
            Upload a supplier invoice PDF — our AI extracts every machine automatically.
            Find it in the main Equipment tab after onboarding.
          </p>
          <Button type="button" variant="outline" onClick={() => setMode('manual')} className="border-[var(--theme-border)] text-white" data-testid="switch-to-manual-btn">
            Use manual entry instead
          </Button>
        </div>
      )}

      {mode === 'manual' && (
        <div className="space-y-3">
          {rows.map((r, i) => (
            <div key={i} className="bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg p-4" data-testid={`equip-row-${i}`}>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <Input value={r.name} onChange={e => updateRow(i, 'name', e.target.value)} placeholder="Name *" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`equip-name-${i}`} />
                <Select value={r.equipment_type} onValueChange={v => updateRow(i, 'equipment_type', v)}>
                  <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`equip-type-${i}`}><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]">
                    <SelectItem value="cardio">Cardio</SelectItem>
                    <SelectItem value="strength">Strength</SelectItem>
                    <SelectItem value="functional">Functional</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
                <Input value={r.manufacturer} onChange={e => updateRow(i, 'manufacturer', e.target.value)} placeholder="Manufacturer" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`equip-mfr-${i}`} />
                <Input value={r.model} onChange={e => updateRow(i, 'model', e.target.value)} placeholder="Model" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`equip-model-${i}`} />
                <Input value={r.serial_number} onChange={e => updateRow(i, 'serial_number', e.target.value)} placeholder="Serial #" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`equip-sn-${i}`} />
                <Input value={r.location} onChange={e => updateRow(i, 'location', e.target.value)} placeholder="Location" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`equip-loc-${i}`} />
              </div>
              {rows.length > 1 && (
                <button type="button" onClick={() => removeRow(i)} className="mt-2 text-xs text-red-400 flex items-center gap-1" data-testid={`remove-equip-${i}`}>
                  <Trash2 size={12} /> Remove
                </button>
              )}
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={addRow} className="border-[var(--theme-border)] text-[var(--color-text-muted)] hover:text-white" data-testid="add-equip-btn">
            <Plus size={14} className="mr-1" /> Add another machine
          </Button>
          <StageFooter onSave={onSaveManual} onSkip={onSkip} saving={saving} saveLabel="Save equipment" skipLabel="Skip for now" saveTestId="save-equipment-btn" />
        </div>
      )}

      {mode !== 'manual' && (
        <StageFooter onSave={null} onSkip={onSkip} saving={false} saveLabel="" skipLabel="Skip for now" saveTestId="" />
      )}
    </div>
  );
};

export default StageEquipment;
