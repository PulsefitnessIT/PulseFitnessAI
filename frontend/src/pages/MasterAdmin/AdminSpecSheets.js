import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import {
  Upload, FileText, Trash2, Loader2, Sparkles, CheckCircle,
  Image, RefreshCw, Search, X, ChevronDown, ChevronUp
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const AdminSpecSheets = ({ headers }) => {
  const [specSheets, setSpecSheets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [processingCount, setProcessingCount] = useState(0);
  const [expandedSpec, setExpandedSpec] = useState(null);
  const [rematching, setRematching] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const fileRef = useRef(null);

  const fetchSpecs = async () => {
    try {
      const res = await axios.get(`${API}/spec-sheets/list`, { headers });
      setSpecSheets(res.data.spec_sheets || []);
    } catch {
      // silent
    }
    setLoading(false);
  };

  useEffect(() => { fetchSpecs(); }, []);

  const processFiles = async (fileList) => {
    const pdfFiles = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfFiles.length === 0) { notify.error('No PDF files found'); return; }

    setUploading(true);
    setProcessingCount(pdfFiles.length);
    let successCount = 0;

    for (const file of pdfFiles) {
      try {
        const formData = new FormData();
        formData.append('file', file);
        await axios.post(`${API}/spec-sheets/upload`, formData, { headers, timeout: 120000 });
        successCount++;
        setProcessingCount(prev => prev - 1);
      } catch (err) {
        notify.error(`${file.name}: ${err.response?.data?.detail || 'Failed'}`);
        setProcessingCount(prev => prev - 1);
      }
    }

    setUploading(false);
    setProcessingCount(0);
    if (successCount > 0) {
      notify.success(`${successCount} spec sheet${successCount > 1 ? 's' : ''} uploaded and matched`);
      fetchSpecs();
    }
  };

  const handleFileInput = (e) => processFiles(e.target.files);
  const handleDragOver = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); };
  const handleDragLeave = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(false); };
  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation(); setDragOver(false);
    processFiles(e.dataTransfer?.files);
  };

  const handleDelete = async (specId, modelName) => {
    if (!window.confirm(`Delete spec sheet for "${modelName}"? This will remove it from all matched equipment.`)) return;
    try {
      await axios.delete(`${API}/spec-sheets/${specId}`, { headers });
      notify.success('Spec sheet deleted');
      fetchSpecs();
    } catch {
      notify.error('Delete failed');
    }
  };

  const handleRematch = async (specId) => {
    setRematching(specId);
    try {
      const res = await axios.post(`${API}/spec-sheets/${specId}/rematch`, {}, { headers });
      notify.success(`Matched to ${res.data.matched_count} equipment items`);
      fetchSpecs();
    } catch {
      notify.error('Rematch failed');
    }
    setRematching(null);
  };

  const filtered = specSheets.filter(s => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (s.equipment_model || '').toLowerCase().includes(q) ||
           (s.equipment_type || '').toLowerCase().includes(q) ||
           (s.manufacturer || '').toLowerCase().includes(q);
  });

  const levelColor = (l) => {
    const map = {
      'Premium': 'bg-amber-50 text-amber-700 border-amber-200',
      'Club Line': 'bg-indigo-50 text-indigo-700 border-indigo-200',
      'Classic': 'bg-cyan-50 text-cyan-700 border-cyan-200',
      'Dual': 'bg-violet-50 text-violet-700 border-violet-200',
    };
    return map[l] || 'bg-zinc-100 text-zinc-600 border-zinc-200';
  };

  const typeColor = (t) => {
    const map = {
      'Treadmill': 'bg-blue-50 text-blue-700 border-blue-200',
      'Cycle': 'bg-green-50 text-green-700 border-green-200',
      'Cross-Trainer': 'bg-purple-50 text-purple-700 border-purple-200',
      'Rower': 'bg-amber-50 text-amber-700 border-amber-200',
      'Strength': 'bg-red-50 text-red-700 border-red-200',
      'Functional': 'bg-teal-50 text-teal-700 border-teal-200',
    };
    return map[t] || 'bg-zinc-100 text-zinc-600 border-zinc-200';
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-400" size={24} /></div>;

  return (
    <div className="space-y-6" data-testid="admin-spec-sheets">
      {/* Upload Zone */}
      <Card
        className={`p-8 border-2 border-dashed transition-colors text-center cursor-pointer ${dragOver ? 'border-[var(--color-brand-blue-dark)] bg-[var(--color-brand-blue-dark)]/5' : 'border-zinc-200 hover:border-[var(--color-brand-blue-dark)]/30'}`}
        onClick={() => !uploading && fileRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        data-testid="spec-sheet-dropzone"
      >
        <input type="file" accept=".pdf" multiple onChange={handleFileInput} ref={fileRef} className="hidden" data-testid="spec-sheet-file-input" />
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 size={32} className="animate-spin text-[var(--color-brand-blue-dark)]" />
            <p className="text-sm text-zinc-600 font-medium">Processing spec sheets... ({processingCount} remaining)</p>
            <p className="text-xs text-zinc-400">AI is extracting model info and hero images</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="w-16 h-16 rounded-full bg-[var(--color-brand-blue-dark)]/10 flex items-center justify-center">
              <Upload size={24} className="text-[var(--color-brand-blue-dark)]" />
            </div>
            <p className="text-sm text-zinc-600 font-medium">
              {specSheets.length > 0 ? 'Upload more spec sheets' : 'Upload Pulse Fitness spec sheets'}
            </p>
            <p className="text-xs text-zinc-400">Drop PDFs here or click to browse. AI will extract model info, specs, and product images.</p>
          </div>
        )}
      </Card>

      {/* Search + Count */}
      {specSheets.length > 0 && (
        <div className="flex items-center justify-between gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search spec sheets..."
              className="w-full pl-9 pr-8 py-2 text-sm border border-zinc-200 rounded-lg focus:ring-1 focus:ring-[var(--color-brand-blue-dark)] focus:outline-none"
              data-testid="spec-search"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600">
                <X size={14} />
              </button>
            )}
          </div>
          <Badge className="bg-[var(--color-brand-blue-dark)]/10 text-[var(--color-brand-blue-dark)] border-[var(--color-brand-blue-dark)]/20">{specSheets.length} spec sheets</Badge>
        </div>
      )}

      {/* Spec Sheets Grid */}
      {filtered.length === 0 && specSheets.length === 0 ? (
        <Card className="p-12 text-center border-zinc-200">
          <FileText size={40} className="mx-auto text-zinc-300 mb-4" />
          <p className="text-zinc-500 text-sm">No spec sheets uploaded yet. Drop your Pulse Fitness PDFs above.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map(spec => (
            <Card key={spec.id} className="border-zinc-200 overflow-hidden" data-testid={`spec-sheet-${spec.id}`}>
              <div className="flex items-center gap-4 p-4">
                {/* Hero image thumbnail */}
                <div className="w-16 h-16 rounded-lg bg-zinc-100 border border-zinc-200 flex items-center justify-center shrink-0 overflow-hidden">
                  {spec.hero_image_url ? (
                    <img src={`${API}/spec-sheets/image/${spec.id}`}
                      alt={spec.equipment_model} className="w-full h-full object-contain" />
                  ) : (
                    <Image size={20} className="text-zinc-400" />
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-sm font-semibold text-zinc-900 truncate">{spec.equipment_model || spec.original_filename}</span>
                    {spec.product_level && (
                      <Badge className={`text-[10px] ${levelColor(spec.product_level)}`}>{spec.product_level}</Badge>
                    )}
                    <Badge className={`text-[10px] ${typeColor(spec.equipment_type)}`}>{spec.equipment_type}</Badge>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-zinc-500">
                    <span>{spec.manufacturer}</span>
                    {spec.matched_count > 0 && (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle size={12} /> {spec.matched_count} matched
                      </span>
                    )}
                    {spec.matched_count === 0 && (
                      <span className="text-amber-600">No matches yet</span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  <Button variant="ghost" size="sm" onClick={() => handleRematch(spec.id)} disabled={rematching === spec.id}
                    className="h-8 px-2 text-zinc-500 hover:text-[var(--color-brand-blue-dark)]" data-testid={`spec-rematch-${spec.id}`}>
                    {rematching === spec.id ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setExpandedSpec(expandedSpec === spec.id ? null : spec.id)}
                    className="h-8 px-2 text-zinc-500">
                    {expandedSpec === spec.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(spec.id, spec.equipment_model)}
                    className="h-8 px-2 text-zinc-400 hover:text-red-500" data-testid={`spec-delete-${spec.id}`}>
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>

              {/* Expanded Detail */}
              {expandedSpec === spec.id && (
                <div className="border-t border-zinc-200 p-4 bg-zinc-50">
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      {spec.description && <p className="text-sm text-zinc-600 mb-3">{spec.description}</p>}
                      {spec.key_specs && Object.keys(spec.key_specs).length > 0 && (
                        <div>
                          <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-2">Key Specifications</h4>
                          <div className="grid grid-cols-2 gap-1">
                            {Object.entries(spec.key_specs).map(([key, val]) => (
                              <div key={key} className="text-xs">
                                <span className="text-zinc-400">{key.replace(/_/g, ' ')}:</span>{' '}
                                <span className="text-zinc-700 font-medium">{val}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="mt-3">
                        <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-1">Matched Equipment IDs</h4>
                        {spec.matched_equipment_ids?.length > 0 ? (
                          <p className="text-xs text-zinc-600">{spec.matched_equipment_ids.length} items matched</p>
                        ) : (
                          <p className="text-xs text-zinc-400">No equipment matched. Try rematching.</p>
                        )}
                      </div>
                    </div>
                    <div>
                      {spec.pdf_url && (
                        <div className="border border-zinc-200 rounded-lg overflow-hidden bg-white">
                          <iframe
                            src={`${API}/spec-sheets/pdf/${spec.id}`}
                            title={spec.equipment_model}
                            className="w-full h-64"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default AdminSpecSheets;
