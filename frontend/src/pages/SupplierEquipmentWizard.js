import { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card } from '../components/ui/card';
import { Checkbox } from '../components/ui/checkbox';
import {
  Wrench, Search, Upload, FileSpreadsheet, CheckCircle2, AlertCircle, Send, Loader2, X,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });

const CSV_TEMPLATE_HEADER =
  'Name,Equipment Type,Manufacturer,Model,Serial Number,Location,Install Date,Warranty Expiry,Notes\n';

function downloadTemplate() {
  const blob = new Blob([CSV_TEMPLATE_HEADER], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'equipment_template.csv';
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Wizard shown right after a new supplier is created (or re-opened from the
 * supplier card). Lets the user assign existing equipment and/or import new
 * equipment via CSV, then sends the branded welcome email with an attached
 * machine list.
 */
export default function SupplierEquipmentWizard({ supplier, open, onClose, onComplete }) {
  const [tab, setTab] = useState('assign');
  const [equipmentList, setEquipmentList] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sendingWelcome, setSendingWelcome] = useState(false);
  const [assignedCount, setAssignedCount] = useState(0);
  const [csvFile, setCsvFile] = useState(null);
  const [csvResult, setCsvResult] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [notifyOnAssign, setNotifyOnAssign] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!open || !supplier) return;
    setSelectedIds(new Set());
    setSearch('');
    setCsvFile(null);
    setCsvResult(null);
    setTab('assign');
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, supplier]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [allEq, supEq] = await Promise.all([
        axios.get(`${API}/equipment`, authHeaders()),
        axios.get(`${API}/suppliers/${supplier.id}/equipment`, authHeaders()),
      ]);
      const all = allEq.data?.equipment || [];
      setEquipmentList(all);
      const supIds = new Set((supEq.data?.equipment || []).map((e) => e.id));
      setSelectedIds(supIds);
      setAssignedCount(supEq.data?.count || 0);
    } catch (_e) {
      notify.error('Failed to load equipment');
    } finally {
      setLoading(false);
    }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return equipmentList;
    return equipmentList.filter((e) => {
      const hay = [e.name, e.equipment_type, e.manufacturer, e.model, e.serial_number, e.supplier]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  }, [equipmentList, search]);

  const toggleId = (id) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelectedIds(next);
  };

  const toggleAll = () => {
    const visibleIds = filtered.map((e) => e.id);
    const allSelected = visibleIds.every((id) => selectedIds.has(id));
    const next = new Set(selectedIds);
    visibleIds.forEach((id) => { if (allSelected) next.delete(id); else next.add(id); });
    setSelectedIds(next);
  };

  const handleAssign = async () => {
    if (selectedIds.size === 0) {
      notify.info('Pick at least one machine first');
      return;
    }
    setSaving(true);
    try {
      const r = await axios.post(
        `${API}/suppliers/${supplier.id}/assign-equipment`,
        { equipment_ids: Array.from(selectedIds), notify: notifyOnAssign && !!supplier.email },
        authHeaders(),
      );
      const suffix = r.data?.notified ? ` — ${supplier.name} notified by email` : '';
      notify.success(`${r.data.assigned} machine(s) assigned to ${supplier.name}${suffix}`);
      await loadData();
    } catch (e) {
      notifyApiError(notify, e, 'Assignment failed');
    } finally {
      setSaving(false);
    }
  };

  const handleCsvUpload = async () => {
    if (!csvFile) return;
    setUploading(true);
    setCsvResult(null);
    try {
      const form = new FormData();
      form.append('file', csvFile);
      const r = await axios.post(
        `${API}/suppliers/${supplier.id}/import-equipment-csv`,
        form,
        {
          ...authHeaders(),
          headers: { ...authHeaders().headers, 'Content-Type': 'multipart/form-data' },
        },
      );
      setCsvResult(r.data);
      notify.success(`${r.data.created} machine(s) imported under ${supplier.name}`);
      await loadData();
    } catch (e) {
      notifyApiError(notify, e, 'CSV upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleSendWelcomeAndFinish = async () => {
    // If the user has changes staged on the assign tab, persist them first.
    if (tab === 'assign' && selectedIds.size > 0 && assignedCount !== selectedIds.size) {
      await handleAssign();
    }
    if (!supplier.email) {
      notify.info('Supplier has no email — finishing without welcome');
      onComplete?.();
      onClose();
      return;
    }
    setSendingWelcome(true);
    try {
      await axios.post(`${API}/suppliers/${supplier.id}/send-welcome`, {}, authHeaders());
      notify.success(`Welcome email sent to ${supplier.name} with machine list`, { duration: 6000 });
      onComplete?.();
      onClose();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to send welcome email');
    } finally {
      setSendingWelcome(false);
    }
  };

  const handleSkip = () => {
    onComplete?.();
    onClose();
  };

  if (!supplier) return null;

  const visibleIds = filtered.map((e) => e.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-3xl" data-testid="supplier-equipment-wizard">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wrench size={16} className="text-indigo-600" />
            Link machines to <span className="text-indigo-600">{supplier.name}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="text-xs text-zinc-600 bg-indigo-50 border border-indigo-100 rounded-lg p-3 -mt-1">
          Assign existing equipment, or import new equipment from a spreadsheet.
          When you click <strong>Send welcome email</strong>, {supplier.name} will receive
          a branded email with the full machine list attached as a CSV.
        </div>

        <Tabs value={tab} onValueChange={setTab} className="mt-3">
          <TabsList className="grid grid-cols-2 w-full">
            <TabsTrigger value="assign" data-testid="wizard-tab-assign">Assign existing</TabsTrigger>
            <TabsTrigger value="import" data-testid="wizard-tab-import">Import from CSV</TabsTrigger>
          </TabsList>

          {/* ── Tab 1: Assign existing equipment ───────────────── */}
          <TabsContent value="assign" className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                <Input
                  placeholder="Search by name, type, serial…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                  data-testid="wizard-search-input"
                />
              </div>
              <Button
                variant="outline" size="sm" onClick={toggleAll}
                data-testid="wizard-toggle-all"
              >
                {allVisibleSelected ? 'Clear visible' : 'Select visible'}
              </Button>
            </div>

            <div className="border border-zinc-200 rounded-lg max-h-80 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center p-10 text-zinc-500 text-sm gap-2">
                  <Loader2 size={14} className="animate-spin" /> Loading equipment…
                </div>
              ) : filtered.length === 0 ? (
                <div className="p-10 text-center text-sm text-zinc-500">
                  No equipment found. Use the <strong>Import from CSV</strong> tab to add new machines.
                </div>
              ) : (
                <ul className="divide-y divide-zinc-100">
                  {filtered.map((e) => {
                    const selected = selectedIds.has(e.id);
                    const otherSupplier = e.supplier && e.supplier !== supplier.name;
                    return (
                      <li
                        key={e.id}
                        className={`flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-zinc-50 ${selected ? 'bg-indigo-50/50' : ''}`}
                        onClick={() => toggleId(e.id)}
                        data-testid={`wizard-eq-row-${e.id}`}
                      >
                        <Checkbox
                          checked={selected}
                          onCheckedChange={() => toggleId(e.id)}
                          onClick={(ev) => ev.stopPropagation()}
                          className="mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-zinc-900 truncate">{e.name || 'Unnamed'}</p>
                          <p className="text-xs text-zinc-500 truncate">
                            {[e.equipment_type, e.manufacturer, e.serial_number, e.location]
                              .filter(Boolean).join(' · ')}
                          </p>
                          {otherSupplier && (
                            <p className="text-[11px] text-amber-600 mt-1 flex items-center gap-1">
                              <AlertCircle size={11} /> Currently assigned to {e.supplier} — will be overwritten
                            </p>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <div className="flex items-center justify-between text-xs gap-3">
              <span className="text-zinc-600">
                <strong className="text-zinc-900">{selectedIds.size}</strong> selected
                {assignedCount > 0 && (
                  <>  ·  <span className="text-emerald-600">{assignedCount} already assigned</span></>
                )}
              </span>
              <div className="flex items-center gap-3">
                {supplier.email && (
                  <label className="flex items-center gap-1.5 cursor-pointer" data-testid="wizard-notify-wrapper">
                    <input
                      type="checkbox" checked={notifyOnAssign}
                      onChange={(e) => setNotifyOnAssign(e.target.checked)}
                      className="accent-indigo-500"
                      data-testid="wizard-notify-checkbox"
                    />
                    <span className="text-zinc-700">Notify {supplier.name} by email</span>
                  </label>
                )}
                <Button
                  size="sm" variant="outline"
                  disabled={saving || selectedIds.size === 0}
                  onClick={handleAssign}
                  data-testid="wizard-save-assignment"
                >
                  {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <CheckCircle2 size={14} className="mr-1" />}
                  Save assignment
                </Button>
              </div>
            </div>
          </TabsContent>

          {/* ── Tab 2: CSV import ──────────────────────────────── */}
          <TabsContent value="import" className="space-y-3">
            <Card className="p-5 bg-zinc-50 border-dashed">
              <div className="flex items-start gap-3">
                <FileSpreadsheet size={20} className="text-indigo-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-zinc-900">CSV format</p>
                  <p className="text-xs text-zinc-600 mt-1">
                    Columns (in any order, case-insensitive):
                    <code className="block mt-1 text-[11px] font-mono bg-white rounded p-2 border border-zinc-200">
                      Name, Equipment Type, Manufacturer, Model, Serial Number, Location, Install Date, Warranty Expiry, Notes
                    </code>
                    <span className="block mt-1">
                      Only <strong>Name</strong> is required. Dates can be <code>YYYY-MM-DD</code>.
                    </span>
                  </p>
                  <Button
                    size="sm" variant="link" className="px-0 h-auto mt-1"
                    onClick={downloadTemplate}
                    data-testid="wizard-download-template"
                  >
                    Download blank template →
                  </Button>
                </div>
              </div>
            </Card>

            <div>
              <Label className="text-xs">Upload CSV file</Label>
              <div className="mt-1 flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file" accept=".csv,text/csv"
                  onChange={(e) => { setCsvFile(e.target.files?.[0] || null); setCsvResult(null); }}
                  className="flex-1 text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-zinc-100 file:text-zinc-700 hover:file:bg-zinc-200 cursor-pointer"
                  data-testid="wizard-csv-file"
                />
                <Button
                  size="sm" disabled={!csvFile || uploading} onClick={handleCsvUpload}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                  data-testid="wizard-csv-upload"
                >
                  {uploading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Upload size={14} className="mr-1" />}
                  Import
                </Button>
              </div>
            </div>

            {csvResult && (
              <Card className={`p-3 ${csvResult.errors?.length ? 'bg-amber-50 border-amber-200' : 'bg-emerald-50 border-emerald-200'}`}>
                <p className="text-sm font-medium">
                  {csvResult.errors?.length
                    ? <><AlertCircle size={14} className="inline -mt-0.5 mr-1" /> Imported {csvResult.created}, skipped {csvResult.errors.length}</>
                    : <><CheckCircle2 size={14} className="inline -mt-0.5 mr-1" /> Imported {csvResult.created} machine(s)</>}
                </p>
                {csvResult.errors?.length > 0 && (
                  <ul className="mt-2 text-[11px] text-amber-700 space-y-0.5">
                    {csvResult.errors.slice(0, 5).map((err, i) => (
                      <li key={i}>Row {err.row}: {err.error}</li>
                    ))}
                    {csvResult.errors.length > 5 && <li>…and {csvResult.errors.length - 5} more</li>}
                  </ul>
                )}
              </Card>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter className="!justify-between mt-4">
          <Button variant="ghost" size="sm" onClick={handleSkip} data-testid="wizard-skip">
            <X size={14} className="mr-1" /> Skip for now
          </Button>
          <Button
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
            disabled={sendingWelcome || saving}
            onClick={handleSendWelcomeAndFinish}
            data-testid="wizard-finish"
          >
            {sendingWelcome ? <Loader2 size={14} className="animate-spin mr-1" /> : <Send size={14} className="mr-1" />}
            Send welcome email &amp; finish
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
