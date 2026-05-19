import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import axios from 'axios';
import { notify } from '@/components/notifications';
import DocumentQA from '@/components/shared/DocumentQA';
import { useUploadQueue } from '@/components/shared/UploadQueue';
import {
 FileText, Upload, FolderOpen, Book, Award, Search, Trash2, Download,
 Eye, Image, FileSpreadsheet, Brain, Loader2, Copy, Building2, X, CloudUpload, CheckCircle, RefreshCw
} from 'lucide-react';

const GlobalDocumentsTab = () => {
 const { API } = useAuth();
 const [documents, setDocuments] = useState([]);
 const [suppliers, setSuppliers] = useState([]);
 const [organizations, setOrganizations] = useState([]);
 const [loading, setLoading] = useState(true);
 const [searchQuery, setSearchQuery] = useState('');
 const [supplierFilter, setSupplierFilter] = useState('all');
 const [categoryFilter, setCategoryFilter] = useState('all');
 const [showDuplicatesOnly, setShowDuplicatesOnly] = useState(false);
 const [duplicateCount, setDuplicateCount] = useState(0);

 // Upload state
 const [showUploadDialog, setShowUploadDialog] = useState(false);
 const [uploadFiles, setUploadFiles] = useState([]);
 const [uploadSupplier, setUploadSupplier] = useState('');
 const [uploadCategory, setUploadCategory] = useState('manuals');
 const [autoDetect, setAutoDetect] = useState(false);
 const [uploadResult, setUploadResult] = useState(null);
 const fileInputRef = useRef(null);
 const dragRef = useRef(null);

 // Viewer state
 const [viewDoc, setViewDoc] = useState(null);
 const [viewBlobUrl, setViewBlobUrl] = useState(null);
 const [viewLoading, setViewLoading] = useState(false);

 // Assign to org state
 const [assignDialog, setAssignDialog] = useState(null);
 // Iter 216h35 — adopt the global UploadQueueDrawer so a bulk upload
 // can continue in the background after the dialog closes. The
 // dialog state stays for choosing supplier/category before kick-off;
 // once the request is in-flight the drawer takes over.
 const { enqueue } = useUploadQueue();

 // AI scan state
 const [scanning, setScanning] = useState(false);

 const token = localStorage.getItem('token');
 const headers = { Authorization: `Bearer ${token}` };

 const loadDocuments = useCallback(async () => {
 setLoading(true);
 try {
 const [docsRes, orgsRes] = await Promise.all([
 axios.get(`${API}/master-admin/documents`, { headers, params: { duplicates_only: showDuplicatesOnly || undefined } }),
 axios.get(`${API}/master-admin/organizations`, { headers }),
 ]);
 setDocuments(docsRes.data.files || []);
 setSuppliers(docsRes.data.suppliers || []);
 setDuplicateCount(docsRes.data.duplicate_count || 0);
 setOrganizations(orgsRes.data.organizations || []);
 } catch {
 notify.error('Failed to load documents');
 }
 setLoading(false);
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
 }, [API, showDuplicatesOnly]);

 useEffect(() => { loadDocuments(); }, [loadDocuments]);

 // Filtered documents
 const filtered = documents.filter(d => {
 if (supplierFilter !== 'all' && (d.supplier_name || 'Uncategorised') !== supplierFilter) return false;
 if (categoryFilter !== 'all' && d.category !== categoryFilter) return false;
 if (searchQuery) {
 const q = searchQuery.toLowerCase();
 const match = (d.original_filename || '').toLowerCase().includes(q) ||
 (d.supplier_name || '').toLowerCase().includes(q) ||
 (d.org_name || '').toLowerCase().includes(q);
 if (!match) return false;
 }
 return true;
 });

 // Group by supplier for summary
 const supplierGroups = {};
 documents.forEach(d => {
 const s = d.supplier_name || 'Uncategorised';
 supplierGroups[s] = (supplierGroups[s] || 0) + 1;
 });

 // Upload handlers
 // Iter 216h33 — dragenter must also preventDefault so Safari/Firefox
 // don't snap the cursor to "no-drop" before dragover registers.
 const handleDragEnter = (e) => {
 e.preventDefault();
 e.stopPropagation();
 dragRef.current?.classList.add('border-blue-500');
 };
 const handleDrop = (e) => {
 e.preventDefault();
 e.stopPropagation();
 dragRef.current?.classList.remove('border-blue-500');
 const files = Array.from(e.dataTransfer.files);
 setUploadFiles(prev => [...prev, ...files]);
 };

 const handleDragOver = (e) => {
 e.preventDefault();
 e.stopPropagation();
 dragRef.current?.classList.add('border-blue-500');
 };

 const handleDragLeave = (e) => {
 e.preventDefault();
 dragRef.current?.classList.remove('border-blue-500');
 };

 const handleFileSelect = (e) => {
 const files = Array.from(e.target.files);
 setUploadFiles(prev => [...prev, ...files]);
 e.target.value = '';
 };

 const removeUploadFile = (idx) => {
 setUploadFiles(prev => prev.filter((_, i) => i !== idx));
 };

 const handleMassUpload = async () => {
 if (!uploadFiles.length) return;
 if (!autoDetect && !uploadSupplier.trim()) {
 notify.error('Please enter a supplier name or enable auto-detect');
 return;
 }
 // Iter 216h35 — enqueue ONE bulk task so the drawer shows live
 // progress while the dialog closes. The endpoint accepts all files
 // in a single FormData, so we wrap the bulk POST in an enqueue()
 // call whose `file` is a synthetic descriptor with the count.
 const files = uploadFiles;
 const supplier = autoDetect ? 'Auto-detecting...' : uploadSupplier.trim();
 const category = uploadCategory;
 const autoFlag = autoDetect;
 const totalSize = files.reduce((s, f) => s + (f.size || 0), 0);
 const bulkLabel = `${files.length} document${files.length === 1 ? '' : 's'} → ${supplier === 'Auto-detecting...' ? 'auto-detect' : supplier}`;
 const synthetic = new File([], bulkLabel, { type: 'application/octet-stream' });
 Object.defineProperty(synthetic, 'size', { value: totalSize });

 enqueue([synthetic], async (_synth, onProgress) => {
 const formData = new FormData();
 files.forEach(f => formData.append('files', f));
 formData.append('supplier_name', supplier);
 formData.append('category', category);
 formData.append('auto_detect', autoFlag);
 const res = await axios.post(`${API}/master-admin/documents/upload`, formData, {
 headers: { ...headers, 'Content-Type': 'multipart/form-data' },
 timeout: 300000,
 onUploadProgress: (evt) => {
 if (evt.total && onProgress) onProgress((evt.loaded / evt.total) * 100);
 },
 });
 const { uploaded, duplicates_found, detected_suppliers, auto_detected } = res.data;
 if (auto_detected && detected_suppliers && Object.keys(detected_suppliers).length > 0) {
 setUploadResult({ detected_suppliers, uploaded, duplicates_found });
 notify.success(`${uploaded} document${uploaded !== 1 ? 's' : ''} uploaded — AI detected suppliers`);
 } else {
 notify.success(`${uploaded} document${uploaded !== 1 ? 's' : ''} uploaded${duplicates_found > 0 ? ` (${duplicates_found} duplicate${duplicates_found !== 1 ? 's' : ''} detected)` : ''}`);
 }
 loadDocuments();
 }, { source: 'global-documents' });

 // Close dialog immediately; drawer takes over visibility.
 setShowUploadDialog(false);
 setUploadFiles([]);
 setUploadSupplier('');
 setAutoDetect(false);
 };

 // Document actions
 const handleDelete = async (fileId) => {
 try {
 await axios.delete(`${API}/master-admin/documents/${fileId}`, { headers });
 setDocuments(prev => prev.filter(d => d.id !== fileId));
 notify.success('Document deleted');
 } catch {
 notify.error('Failed to delete');
 }
 };

 const handleAssignOrg = async (fileId, orgId) => {
 try {
 await axios.put(`${API}/master-admin/documents/${fileId}/assign-org?org_id=${orgId}`, {}, { headers });
 notify.success('Document assigned');
 setAssignDialog(null);
 loadDocuments();
 } catch {
 notify.error('Failed to assign');
 }
 };

 const _handleUpdateSupplier = async (fileId, newSupplier) => {
 try {
 await axios.put(`${API}/master-admin/documents/${fileId}/supplier?supplier_name=${encodeURIComponent(newSupplier)}`, {}, { headers });
 notify.success('Supplier updated');
 loadDocuments();
 } catch {
 notify.error('Failed to update supplier');
 }
 };

 const handleViewDoc = async (doc) => {
 setViewDoc(doc);
 setViewLoading(true);
 if (viewBlobUrl) URL.revokeObjectURL(viewBlobUrl);
 setViewBlobUrl(null);
 try {
 const res = await axios.get(`${API}/files/${doc.id}`, { headers, responseType: 'arraybuffer' });
 const ct = res.headers['content-type'] || doc.content_type || 'application/octet-stream';
 const blob = new Blob([res.data], { type: ct });
 setViewBlobUrl(URL.createObjectURL(blob));
 } catch {
 notify.error('Failed to load document');
 setViewDoc(null);
 }
 setViewLoading(false);
 };

 const handleDownload = async (doc) => {
 try {
 const res = await axios.get(`${API}/files/${doc.id}`, { headers, responseType: 'arraybuffer' });
 const blob = new Blob([res.data]);
 const url = URL.createObjectURL(blob);
 const link = document.createElement('a');
 link.href = url;
 link.download = doc.original_filename || 'download';
 document.body.appendChild(link);
 link.click();
 link.remove();
 URL.revokeObjectURL(url);
 } catch {
 notify.error('Failed to download');
 }
 };

 const handleAIScan = async () => {
 setScanning(true);
 try {
 const res = await axios.post(`${API}/master-admin/documents/ai-scan-duplicates`, {}, { headers });
 const { duplicates } = res.data;
 if (duplicates.length === 0) {
 notify.success('No semantic duplicates found');
 } else {
 notify.success(`Found ${duplicates.length} potential duplicate group${duplicates.length !== 1 ? 's' : ''}`);
 }
 loadDocuments();
 } catch {
 notify.error('AI scan failed');
 }
 setScanning(false);
 };

 const isImage = (doc) => (doc.content_type || '').toLowerCase().startsWith('image/');
 const isPDF = (doc) => (doc.content_type || '').toLowerCase() === 'application/pdf' || (doc.original_filename || '').toLowerCase().endsWith('.pdf');
 const isViewable = (doc) => isImage(doc) || isPDF(doc);

 const getFileIcon = (doc) => {
 if (isImage(doc)) return <Image size={18} className="text-blue-400" />;
 if (isPDF(doc)) return <FileText size={18} className="text-red-400" />;
 const fn = (doc.original_filename || '').toLowerCase();
 if (fn.endsWith('.xlsx') || fn.endsWith('.xls') || fn.endsWith('.csv')) return <FileSpreadsheet size={18} className="text-green-400" />;
 return <FileText size={18} className="text-blue-400" />;
 };

 const formatSize = (bytes) => {
 if (!bytes) return '';
 if (bytes < 1024) return `${bytes} B`;
 if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
 return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
 };

 const categories = [
 { key: 'manuals', label: 'Manuals', icon: Book },
 { key: 'certificates', label: 'Certificates', icon: Award },
 { key: 'contracts', label: 'Contracts', icon: FileText },
 ];

 if (loading) {
 return (
 <div className="flex items-center justify-center h-64" data-testid="global-docs-loading">
 <RefreshCw className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} size={24} />
 </div>
 );
 }

 return (
 <div className="space-y-6" data-testid="global-documents-tab">
 {/* Header */}
 <div className="flex items-center justify-between flex-wrap gap-3">
 <div>
 <h2 className="text-2xl font-semibold" style={{ color: 'var(--theme-text)' }}>Global Document Library</h2>
 <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
 {documents.length} documents across {Object.keys(supplierGroups).length} suppliers
 </p>
 </div>
 <div className="flex items-center gap-2">
 <Button
 variant="outline"
 size="sm"
 onClick={handleAIScan}
 disabled={scanning}
 className="border-purple-500/30 text-purple-400 hover:bg-purple-500/10"
 data-testid="ai-scan-btn"
 >
 {scanning ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Brain size={14} className="mr-1" />}
 AI Duplicate Scan
 </Button>
 <Button
 onClick={() => setShowUploadDialog(true)}
 className=""
 data-testid="mass-upload-btn"
 >
 <CloudUpload size={16} className="mr-2" /> Mass Upload
 </Button>
 </div>
 </div>

 {/* Supplier Cards */}
 <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide" data-testid="supplier-pills">
 <button
 onClick={() => setSupplierFilter('all')}
 className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${supplierFilter === 'all' ? 'text-white bg-[var(--color-brand-blue)]' : ''}`}
 style={supplierFilter !== 'all' ? { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text-muted)' } : {}}
 data-testid="supplier-filter-all"
 >
 All ({documents.length})
 </button>
 {suppliers.map(s => (
 <button
 key={s}
 onClick={() => setSupplierFilter(s)}
 className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${supplierFilter === s ? 'text-white bg-[var(--color-brand-blue)]' : ''}`}
 style={supplierFilter !== s ? { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text-muted)' } : {}}
 data-testid={`supplier-filter-${s.replace(/\s/g, '-')}`}
 >
 {s} ({supplierGroups[s] || 0})
 </button>
 ))}
 </div>

 {/* Document Q&A */}
 <DocumentQA compact />

 {/* Filters Row */}
 <div className="flex items-center gap-3 flex-wrap">
 <div className="relative flex-1 min-w-[200px]">
 <Search className="absolute left-3 top-1/2 -translate-y-1/2" size={16} style={{ color: 'var(--theme-text-muted)' }} />
 <Input
 value={searchQuery}
 onChange={e => setSearchQuery(e.target.value)}
 placeholder="Search by filename, supplier, or gym..."
 className="pl-10"
 style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="global-doc-search"
 />
 </div>
 <div className="flex gap-2">
 {categories.map(c => (
 <button
 key={c.key}
 onClick={() => setCategoryFilter(categoryFilter === c.key ? 'all' : c.key)}
 className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${categoryFilter === c.key ? 'bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)]' : ''}`}
 style={categoryFilter !== c.key ? { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text-muted)' } : { border: '1px solid rgba(0,85,255,0.3)' }}
 data-testid={`category-filter-${c.key}`}
 >
 <c.icon size={12} /> {c.label}
 </button>
 ))}
 </div>
 {duplicateCount > 0 && (
 <button
 onClick={() => setShowDuplicatesOnly(!showDuplicatesOnly)}
 className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${showDuplicatesOnly ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30' : ''}`}
 style={!showDuplicatesOnly ? { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text-muted)' } : {}}
 data-testid="duplicates-filter"
 >
 <Copy size={12} /> {duplicateCount} Duplicates
 </button>
 )}
 </div>

 {/* Document Table */}
 <Card className="overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
 <div className="overflow-x-auto">
 <table className="w-full text-sm" data-testid="global-docs-table">
 <thead>
 <tr style={{ borderBottom: '1px solid var(--theme-border)' }}>
 {['Document', 'Supplier', 'Category', 'Gym', 'Size', 'Date', 'Status', 'Actions'].map(h => (
 <th key={h} className="text-left p-3 text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{h}</th>
 ))}
 </tr>
 </thead>
 <tbody>
 {filtered.map(doc => (
 <tr key={doc.id} className="hover:opacity-80 transition-opacity" style={{ borderBottom: '1px solid var(--theme-border)' }} data-testid={`global-doc-row-${doc.id}`}>
 <td className="p-3">
 <div className="flex items-center gap-2.5 min-w-0">
 <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'var(--theme-bg)' }}>
 {getFileIcon(doc)}
 </div>
 <span className="font-medium truncate max-w-[200px]" style={{ color: 'var(--theme-text)' }}>{doc.original_filename}</span>
 </div>
 </td>
 <td className="p-3">
 <span className="text-xs px-2 py-1 rounded-full" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }}>
 {doc.supplier_name || 'Uncategorised'}
 </span>
 </td>
 <td className="p-3 capitalize" style={{ color: 'var(--theme-text-muted)' }}>{doc.category || '—'}</td>
 <td className="p-3">
 <span className="text-xs" style={{ color: doc.organization_id ? 'var(--theme-text)' : 'var(--theme-text-muted)' }}>
 {doc.org_name || 'Global'}
 </span>
 </td>
 <td className="p-3 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{formatSize(doc.size)}</td>
 <td className="p-3 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
 {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '—'}
 </td>
 <td className="p-3">
 <div className="flex items-center gap-1.5">
 {doc.ai_extracted && <Badge className="bg-purple-500/15 text-purple-400 text-[9px]"><Brain size={8} className="mr-0.5" /> Indexed</Badge>}
 {doc.is_duplicate && <Badge className="bg-amber-500/15 text-amber-400 text-[9px]"><Copy size={8} className="mr-0.5" /> Dup ({doc.duplicate_count})</Badge>}
 {!doc.ai_extracted && !doc.is_duplicate && <span style={{ color: 'var(--theme-text-muted)' }}>—</span>}
 </div>
 </td>
 <td className="p-3">
 <div className="flex items-center gap-1">
 {isViewable(doc) && (
 <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleViewDoc(doc)} data-testid={`view-${doc.id}`}>
 <Eye size={13} style={{ color: 'var(--theme-text-muted)' }} />
 </Button>
 )}
 <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleDownload(doc)} data-testid={`dl-${doc.id}`}>
 <Download size={13} style={{ color: 'var(--theme-text-muted)' }} />
 </Button>
 <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setAssignDialog(doc)} data-testid={`assign-${doc.id}`}>
 <Building2 size={13} style={{ color: 'var(--theme-text-muted)' }} />
 </Button>
 <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleDelete(doc.id)} data-testid={`del-${doc.id}`}>
 <Trash2 size={13} className="text-red-400" />
 </Button>
 </div>
 </td>
 </tr>
 ))}
 </tbody>
 </table>
 </div>
 {filtered.length === 0 && (
 <div className="p-12 text-center">
 <FolderOpen size={40} className="mx-auto mb-3" style={{ color: 'var(--theme-text-muted)' }} />
 <p style={{ color: 'var(--theme-text-muted)' }}>
 {documents.length === 0 ? 'No documents uploaded yet. Use Mass Upload to get started.' : 'No documents match your filters'}
 </p>
 </div>
 )}
 </Card>

 {/* Mass Upload Dialog */}
 <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
 <DialogContent className="max-w-2xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="mass-upload-dialog">
 <DialogHeader>
 <DialogTitle style={{ color: 'var(--theme-text)' }}>Mass Upload Documents</DialogTitle>
 </DialogHeader>

 <div className="space-y-4">
 {/* Auto-detect Toggle */}
 <div
 className="flex items-center justify-between p-3 rounded-xl cursor-pointer transition-colors"
 style={{ background: autoDetect ? 'rgba(168,85,247,0.1)' : 'var(--theme-bg)', border: autoDetect ? '1px solid rgba(168,85,247,0.3)' : '1px solid var(--theme-border)' }}
 onClick={() => setAutoDetect(!autoDetect)}
 data-testid="auto-detect-toggle"
 >
 <div className="flex items-center gap-2.5">
 <Brain size={18} className={autoDetect ? 'text-purple-400' : ''} style={!autoDetect ? { color: 'var(--theme-text-muted)' } : {}} />
 <div>
 <p className="text-sm font-medium" style={{ color: 'var(--theme-text)' }}>AI Auto-detect Supplier</p>
 <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>AI reads each document and identifies the manufacturer</p>
 </div>
 </div>
 <div className={`w-10 h-5 rounded-full transition-colors flex items-center ${autoDetect ? 'bg-purple-500 justify-end' : 'justify-start'}`} style={!autoDetect ? { background: 'var(--theme-border)' } : {}}>
 <div className="w-4 h-4 rounded-full bg-white dark:bg-white mx-0.5 shadow-sm" />
 </div>
 </div>

 {/* Supplier Name (hidden when auto-detect is on) */}
 {!autoDetect && (
 <div>
 <label className="text-xs font-medium mb-1 block" style={{ color: 'var(--theme-text-muted)' }}>Supplier / Manufacturer *</label>
 <Input
 value={uploadSupplier}
 onChange={e => setUploadSupplier(e.target.value)}
 placeholder="e.g. Pulse Fitness, Technogym, Life Fitness..."
 style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="upload-supplier-input"
 />
 </div>
 )}

 {/* Category */}
 <div>
 <label className="text-xs font-medium mb-1 block" style={{ color: 'var(--theme-text-muted)' }}>Category</label>
 <div className="flex gap-2">
 {categories.map(c => (
 <button
 key={c.key}
 onClick={() => setUploadCategory(c.key)}
 className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${uploadCategory === c.key ? 'bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)] border border-[rgb(var(--rgb-brand-blue)/0.3)]' : ''}`}
 style={uploadCategory !== c.key ? { background: 'var(--theme-bg)', border: '1px solid var(--theme-border)', color: 'var(--theme-text-muted)' } : {}}
 data-testid={`upload-category-${c.key}`}
 >
 <c.icon size={12} /> {c.label}
 </button>
 ))}
 </div>
 </div>

 {/* Drop Zone */}
 <div
 ref={dragRef}
 onDragEnter={handleDragEnter}
 onDrop={handleDrop}
 onDragOver={handleDragOver}
 onDragLeave={handleDragLeave}
 onClick={() => fileInputRef.current?.click()}
 className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors hover:border-[rgb(var(--rgb-brand-blue)/0.5)]"
 style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg)' }}
 data-testid="upload-dropzone"
 >
 <CloudUpload size={36} className="mx-auto mb-3" style={{ color: 'var(--theme-text-muted)' }} />
 <p className="font-medium" style={{ color: 'var(--theme-text)' }}>Drop files here or click to browse</p>
 <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>PDF, Word, Excel, Images — up to 50 files at once</p>
 <input
 ref={fileInputRef}
 type="file"
 multiple
 className="hidden"
 onChange={handleFileSelect}
 accept=".pdf,.doc,.docx,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.webp"
 data-testid="upload-file-input"
 />
 </div>

 {/* Selected Files */}
 {uploadFiles.length > 0 && (
 <div className="space-y-1.5 max-h-48 overflow-y-auto">
 <p className="text-xs font-medium" style={{ color: 'var(--theme-text-muted)' }}>{uploadFiles.length} file{uploadFiles.length !== 1 ? 's' : ''} selected</p>
 {uploadFiles.map((f, i) => (
 <div key={i} className="flex items-center justify-between p-2 rounded-lg text-xs" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
 <div className="flex items-center gap-2 min-w-0">
 <FileText size={14} style={{ color: 'var(--theme-text-muted)' }} />
 <span className="truncate" style={{ color: 'var(--theme-text)' }}>{f.name}</span>
 <span style={{ color: 'var(--theme-text-muted)' }}>({formatSize(f.size)})</span>
 </div>
 <button onClick={() => removeUploadFile(i)} className="ml-2 flex-shrink-0">
 <X size={14} className="text-red-400" />
 </button>
 </div>
 ))}
 </div>
 )}

 {/* Upload Button — Iter 216h35: drawer now owns in-flight UI, so
     this button no longer waits; it kicks off the bulk task and the
     dialog closes immediately. */}
 <Button
 onClick={handleMassUpload}
 disabled={!uploadFiles.length || (!autoDetect && !uploadSupplier.trim())}
 className="w-full"
 data-testid="upload-submit-btn"
 >
 <Upload size={16} className="mr-2" /> Upload {uploadFiles.length} Document{uploadFiles.length !== 1 ? 's' : ''}{autoDetect ? ' (AI Auto-detect)' : ''}
 </Button>

 {/* AI Detection Results */}
 {uploadResult && (
 <div className="space-y-2 p-3 rounded-xl" style={{ background: 'rgba(168,85,247,0.08)', border: '1px solid rgba(168,85,247,0.2)' }} data-testid="detection-results">
 <div className="flex items-center gap-2 mb-2">
 <CheckCircle size={16} className="text-emerald-400" />
 <p className="text-sm font-medium" style={{ color: 'var(--theme-text)' }}>
 {uploadResult.uploaded} files uploaded — AI detected suppliers:
 </p>
 </div>
 <div className="space-y-1 max-h-40 overflow-y-auto">
 {Object.entries(uploadResult.detected_suppliers).map(([filename, supplier]) => (
 <div key={filename} className="flex items-center justify-between text-xs p-2 rounded-lg" style={{ background: 'var(--theme-bg)' }}>
 <span className="truncate mr-2" style={{ color: 'var(--theme-text-muted)' }}>{filename}</span>
 <Badge className="bg-purple-500/15 text-purple-300 whitespace-nowrap flex-shrink-0">{supplier}</Badge>
 </div>
 ))}
 </div>
 <Button
 size="sm"
 variant="outline"
 className="w-full mt-2"
 onClick={() => { setShowUploadDialog(false); setUploadFiles([]); setUploadResult(null); setAutoDetect(false); }}
 data-testid="close-results-btn"
 >
 Done
 </Button>
 </div>
 )}
 </div>
 </DialogContent>
 </Dialog>

 {/* Assign to Org Dialog */}
 <Dialog open={!!assignDialog} onOpenChange={(open) => !open && setAssignDialog(null)}>
 <DialogContent style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="assign-org-dialog">
 <DialogHeader>
 <DialogTitle style={{ color: 'var(--theme-text)' }}>Assign to Organisation</DialogTitle>
 </DialogHeader>
 <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
 Assign"<span style={{ color: 'var(--theme-text)' }}>{assignDialog?.original_filename}</span>" to:
 </p>
 <div className="space-y-1.5 max-h-60 overflow-y-auto mt-2">
 {organizations.map(org => (
 <button
 key={org.id}
 onClick={() => handleAssignOrg(assignDialog.id, org.id)}
 className="w-full flex items-center justify-between p-3 rounded-lg text-sm transition-colors hover:bg-[rgb(var(--rgb-brand-blue)/0.1)]"
 style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}
 data-testid={`assign-org-${org.id}`}
 >
 <div className="flex items-center gap-2">
 <Building2 size={14} style={{ color: 'var(--theme-text-muted)' }} />
 <span style={{ color: 'var(--theme-text)' }}>{org.name}</span>
 </div>
 {assignDialog?.organization_id === org.id && <CheckCircle size={14} className="text-emerald-400" />}
 </button>
 ))}
 </div>
 </DialogContent>
 </Dialog>

 {/* Document Viewer Dialog */}
 <Dialog open={!!viewDoc} onOpenChange={(open) => {
 if (!open) {
 if (viewBlobUrl) URL.revokeObjectURL(viewBlobUrl);
 setViewBlobUrl(null);
 setViewDoc(null);
 }
 }}>
 <DialogContent className="max-w-4xl w-[95vw] max-h-[90vh]" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="doc-viewer-dialog">
 <DialogHeader>
 <DialogTitle className="truncate pr-4" style={{ color: 'var(--theme-text)' }}>{viewDoc?.original_filename}</DialogTitle>
 </DialogHeader>
 <div className="w-full h-[70vh] rounded-lg overflow-hidden" style={{ background: 'var(--theme-bg)' }}>
 {viewLoading && (
 <div className="w-full h-full flex items-center justify-center">
 <Loader2 size={32} className="text-[var(--color-brand-blue)] animate-spin" />
 </div>
 )}
 {!viewLoading && viewDoc && viewBlobUrl && isImage(viewDoc) && (
 <div className="w-full h-full flex items-center justify-center p-4">
 <img src={viewBlobUrl} alt={viewDoc.original_filename} className="max-w-full max-h-full object-contain rounded" />
 </div>
 )}
 {!viewLoading && viewDoc && viewBlobUrl && isPDF(viewDoc) && (
 <iframe src={viewBlobUrl} title={viewDoc.original_filename} className="w-full h-full border-0" />
 )}
 </div>
 <div className="flex justify-end pt-2">
 {viewDoc && (
 <Button size="sm" className="bg-[var(--color-brand-blue)] text-white" onClick={() => handleDownload(viewDoc)}>
 <Download size={14} className="mr-1" /> Download
 </Button>
 )}
 </div>
 </DialogContent>
 </Dialog>
 </div>
 );
};

export default GlobalDocumentsTab;
