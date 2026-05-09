import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import DocumentQA from '../components/shared/DocumentQA';
import {
 FileText, Upload, FolderOpen, Book, Award, Search,
 Trash2, Download, Eye, Image, FileSpreadsheet, X, Brain, Loader2, Printer
} from 'lucide-react';
import PageHeader from '@/components/shared/PageHeader';

const DocumentsTab = () => {
 const { t } = useTranslation();
 const { API } = useAuth();
 const [documents, setDocuments] = useState([]);
 const [subTab, setSubTab] = useState('manuals');
 const [uploading, setUploading] = useState(false);
 const [searchQuery, setSearchQuery] = useState('');
 const [viewDoc, setViewDoc] = useState(null);
 const [viewBlobUrl, setViewBlobUrl] = useState(null);
 const [viewLoading, setViewLoading] = useState(false);
 const [aiExtracting, setAiExtracting] = useState(null);

 useEffect(() => { loadDocuments(); }, []);

 const loadDocuments = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/files/list`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setDocuments(res.data.files || []);
 } catch {
 setDocuments([]);
 }
 };

 const handleUpload = async (e) => {
 const file = e.target.files[0];
 if (!file) return;
 setUploading(true);
 const token = localStorage.getItem('token');
 try {
 const formData = new FormData();
 formData.append('file', file);
 const res = await axios.post(`${API}/files/upload?category=${subTab}`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
 });
 notify.success(`${file.name} uploaded to ${subTab}`);

 if (res.data?.id) {
 triggerAIExtraction(res.data.id, file.name, token);
 }

 loadDocuments();
 } catch {
 notify.error('Upload failed');
 } finally {
 setUploading(false);
 e.target.value = '';
 }
 };

 const triggerAIExtraction = async (fileId, filename, token) => {
 try {
 setAiExtracting(fileId);
 await axios.post(`${API}/files/${fileId}/extract`, {}, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success(`AI extracted information from ${filename}`);
 loadDocuments();
 } catch {
 // Silently fail - extraction is a bonus feature
 } finally {
 setAiExtracting(null);
 }
 };

 const handleDelete = async (fileId) => {
 const token = localStorage.getItem('token');
 try {
 await axios.delete(`${API}/files/${fileId}`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setDocuments(documents.filter(d => d.id !== fileId));
 notify.success('Document deleted');
 } catch {
 notify.error('Failed to delete');
 }
 };

 const handleViewDoc = async (doc) => {
 setViewDoc(doc);
 setViewLoading(true);
 if (viewBlobUrl) URL.revokeObjectURL(viewBlobUrl);
 setViewBlobUrl(null);
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/files/${doc.id}`, {
 headers: { Authorization: `Bearer ${token}` },
 responseType: 'arraybuffer'
 });
 const ct = res.headers['content-type'] || doc.content_type || 'application/octet-stream';
 const blob = new Blob([res.data], { type: ct });
 const url = URL.createObjectURL(blob);
 setViewBlobUrl(url);
 } catch (err) {
 console.error('Document view error:', err);
 notify.error('Failed to load document');
 setViewDoc(null);
 } finally {
 setViewLoading(false);
 }
 };

 const handleDownloadDoc = async (doc) => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/files/${doc.id}`, {
 headers: { Authorization: `Bearer ${token}` },
 responseType: 'arraybuffer'
 });
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

 const handlePrintDoc = async (doc) => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/files/${doc.id}`, {
 headers: { Authorization: `Bearer ${token}` },
 responseType: 'arraybuffer'
 });
 const ct = res.headers['content-type'] || doc.content_type || 'application/octet-stream';
 const blob = new Blob([res.data], { type: ct });
 const url = URL.createObjectURL(blob);

 const printWindow = window.open('', '_blank');
 if (!printWindow) {
 notify.error('Pop-up blocked — please allow pop-ups to print');
 URL.revokeObjectURL(url);
 return;
 }

 const fname = doc.original_filename || 'Service Certificate';
 if (ct.startsWith('image/')) {
 printWindow.document.write(`
 <html><head><title>Print — ${fname}</title>
 <style>@media print{@page{margin:0.5in}body{margin:0;display:flex;justify-content:center;align-items:center;min-height:100vh}}
 body{margin:0;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#fff}
 img{max-width:100%;max-height:95vh;object-fit:contain}</style></head>
 <body><img src="${url}" onload="window.print();window.close();" /></body></html>`);
 } else if (ct === 'application/pdf') {
 printWindow.document.write(`
 <html><head><title>Print — ${fname}</title></head>
 <body style="margin:0"><iframe src="${url}" style="width:100%;height:100vh;border:none" onload="setTimeout(()=>{window.print();window.close()},500)"></iframe></body></html>`);
 } else {
 printWindow.document.write(`
 <html><head><title>Print — ${fname}</title></head>
 <body style="margin:0"><iframe src="${url}" style="width:100%;height:100vh;border:none" onload="setTimeout(()=>{window.print();window.close()},500)"></iframe></body></html>`);
 }
 printWindow.document.close();
 } catch {
 notify.error('Failed to load document for printing');
 }
 };

 const isImage = (doc) => {
 const ct = (doc.content_type || '').toLowerCase();
 return ct.startsWith('image/');
 };

 const isPDF = (doc) => {
 const ct = (doc.content_type || '').toLowerCase();
 const fn = (doc.original_filename || '').toLowerCase();
 return ct === 'application/pdf' || fn.endsWith('.pdf');
 };

 const isViewable = (doc) => isImage(doc) || isPDF(doc);

 const filtered = documents
 .filter(d => (d.category || 'manuals') === subTab)
 .filter(d => !searchQuery || d.original_filename?.toLowerCase().includes(searchQuery.toLowerCase()));

 const tabs = [
 { key: 'manuals', label: 'Manuals', icon: Book, desc: 'Equipment manuals, user guides, and technical documentation' },
 { key: 'certificates', label: 'Service Certificates', icon: Award, desc: 'Service records, PAT test certificates, and compliance documents' },
 { key: 'contracts', label: 'Contracts', icon: FileText, desc: 'Maintenance agreements, aftersales contracts, and service level agreements' },
 ];

 const activeTabInfo = tabs.find(t => t.key === subTab);

 const getFileIcon = (doc) => {
 if (isImage(doc)) return <Image size={20} className="text-[var(--color-brand-blue)]" />;
 if (isPDF(doc)) return <FileText size={20} className="text-red-400" />;
 const fn = (doc.original_filename || '').toLowerCase();
 if (fn.endsWith('.xlsx') || fn.endsWith('.xls') || fn.endsWith('.csv')) return <FileSpreadsheet size={20} className="text-green-400" />;
 return <FileText size={20} className="text-[var(--color-brand-blue)]" />;
 };

 const formatSize = (bytes) => {
 if (!bytes) return '';
 if (bytes < 1024) return `${bytes} B`;
 if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
 return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
 };

 return (
 <div className="space-y-6" data-testid="documents-tab">
 <PageHeader
   title="Documents"
   subtitle="Manage equipment manuals, service certificates and compliance docs"
   icon={FileText}
   testId="documents-header"
   actions={
     <label className="cursor-pointer">
       <input type="file" className="hidden" onChange={handleUpload} accept=".pdf,.doc,.docx,.xlsx,.jpg,.jpeg,.png,.webp" data-testid="doc-upload-input" />
       <Button className="pointer-events-none" data-testid="doc-upload-btn">
         <Upload size={16} className="mr-2" /> {uploading ? 'Uploading...' : `Upload to ${activeTabInfo?.label}`}
       </Button>
     </label>
   }
 />

 {/* Document Q&A */}
 <DocumentQA compact />

 <div className="flex gap-3 flex-wrap">
 {tabs.map(tab => (
 <button
 key={tab.key}
 onClick={() => setSubTab(tab.key)}
 className={`flex items-center gap-2 px-5 py-3 rounded-lg border text-sm font-medium transition-all ${
 subTab === tab.key
 ? 'bg-[rgb(var(--rgb-brand-blue)/0.1)] border-[rgb(var(--rgb-brand-blue)/0.5)] text-[var(--color-brand-blue)]'
 : 'bg-[var(--theme-surface)] border-white/10 text-[var(--color-text-muted)] hover:border-white/20'
 }`}
 data-testid={`doc-tab-${tab.key}`}
 >
 <tab.icon size={16} /> {tab.label}
 <Badge className="bg-white/10 text-[var(--color-text-muted)] text-xs ml-1">
 {documents.filter(d => (d.category || 'manuals') === tab.key).length}
 </Badge>
 </button>
 ))}
 </div>

 <p className="text-[var(--color-text-muted)] text-sm">{activeTabInfo?.desc}</p>

 <div className="relative">
 <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" size={18} />
 <Input
 value={searchQuery}
 onChange={e => setSearchQuery(e.target.value)}
 placeholder={`Search ${activeTabInfo?.label?.toLowerCase()}...`}
 className="bg-[var(--theme-surface)] border-white/10 text-white pl-10"
 data-testid="doc-search-input"
 />
 </div>

 <div className="space-y-3">
 {filtered.length > 0 ? (
 filtered.map(doc => (
 <Card key={doc.id} className="bg-[var(--theme-surface)] border-white/10 p-5 flex items-center justify-between" data-testid={`doc-card-${doc.id}`}>
 <div className="flex items-center gap-3 min-w-0 flex-1">
 <div className="w-10 h-10 bg-[rgb(var(--rgb-brand-blue)/0.1)] rounded-lg flex items-center justify-center flex-shrink-0">
 {getFileIcon(doc)}
 </div>
 <div className="min-w-0 flex-1">
 <p className="text-white font-medium truncate">{doc.original_filename}</p>
 <p className="text-[var(--color-text-muted)] text-xs">
 {formatSize(doc.size)} | {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : 'Unknown date'}
 </p>
 </div>
 </div>
 <div className="flex items-center gap-2 flex-shrink-0 ml-3">
 {aiExtracting === doc.id && (
 <Loader2 size={16} className="text-[var(--color-brand-blue)] animate-spin" />
 )}
 {isViewable(doc) && (
 <Button
 size="sm"
 variant="outline"
 className="border-[rgb(var(--rgb-brand-blue)/0.3)] text-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.1)]"
 onClick={() => handleViewDoc(doc)}
 data-testid={`doc-view-${doc.id}`}
 >
 <Eye size={14} />
 </Button>
 )}
 <Button size="sm" variant="outline" className="border-green-500/30 text-green-400 hover:bg-green-500/10" onClick={() => handlePrintDoc(doc)} data-testid={`doc-print-${doc.id}`}>
 <Printer size={14} />
 </Button>
 <Button size="sm" variant="outline" className="border-white/10 text-white" onClick={() => handleDownloadDoc(doc)} data-testid={`doc-download-${doc.id}`}>
 <Download size={14} />
 </Button>
 <Button size="sm" variant="outline" className="border-red-500/30 text-red-400 hover:bg-red-500/10" onClick={() => handleDelete(doc.id)} data-testid={`doc-delete-${doc.id}`}>
 <Trash2 size={14} />
 </Button>
 </div>
 </Card>
 ))
 ) : (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-12 text-center">
 <FolderOpen size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">No {activeTabInfo?.label?.toLowerCase()} uploaded yet</p>
 <p className="text-[var(--color-text-muted)] text-sm mt-1">Upload PDF, Word, or image files to keep your records organised</p>
 <label className="cursor-pointer inline-block mt-4">
 <input type="file" className="hidden" onChange={handleUpload} accept=".pdf,.doc,.docx,.xlsx,.jpg,.jpeg,.png,.webp" />
 <Button className="pointer-events-none" data-testid="doc-upload-empty-btn">
 <Upload size={16} className="mr-2" /> Upload {activeTabInfo?.label}
 </Button>
 </label>
 </Card>
 )}
 </div>

 {/* Document Viewer Dialog */}
 <Dialog open={!!viewDoc} onOpenChange={(open) => {
 if (!open) {
 if (viewBlobUrl) URL.revokeObjectURL(viewBlobUrl);
 setViewBlobUrl(null);
 setViewDoc(null);
 }
 }}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white max-w-4xl w-[95vw] max-h-[90vh]" data-testid="doc-viewer-dialog">
 <DialogHeader>
 <div className="flex items-center justify-between">
 <DialogTitle className="text-white truncate pr-4">{viewDoc?.original_filename}</DialogTitle>
 </div>
 </DialogHeader>
 <div className="w-full h-[70vh] bg-[var(--color-ink-alt)] rounded-lg overflow-hidden">
 {viewLoading && (
 <div className="w-full h-full flex items-center justify-center">
 <Loader2 size={32} className="text-[var(--color-brand-blue)] animate-spin" />
 <span className="text-[var(--color-text-muted)] ml-3">Loading document...</span>
 </div>
 )}
 {!viewLoading && viewDoc && viewBlobUrl && isImage(viewDoc) && (
 <div className="w-full h-full flex items-center justify-center p-4">
 <img
 src={viewBlobUrl}
 alt={viewDoc.original_filename}
 className="max-w-full max-h-full object-contain rounded"
 data-testid="doc-viewer-image"
 />
 </div>
 )}
 {!viewLoading && viewDoc && viewBlobUrl && isPDF(viewDoc) && (
 <iframe
 src={viewBlobUrl}
 title={viewDoc.original_filename}
 className="w-full h-full border-0"
 data-testid="doc-viewer-pdf"
 />
 )}
 </div>
 <div className="flex justify-between items-center pt-2">
 <p className="text-[var(--color-text-muted)] text-sm">
 {viewDoc && formatSize(viewDoc.size)}
 {viewDoc?.ai_extracted && (
 <Badge className="bg-purple-500/20 text-purple-400 text-xs ml-2 inline-flex items-center gap-1">
 <Brain size={10} /> AI has indexed this document
 </Badge>
 )}
 </p>
 {viewDoc && (
 <div className="flex items-center gap-2">
 <Button size="sm" variant="outline" className="border-green-500/30 text-green-400 hover:bg-green-500/10" onClick={() => handlePrintDoc(viewDoc)} data-testid="doc-viewer-print-btn">
 <Printer size={14} className="mr-1" /> Print
 </Button>
 <Button size="sm" className="bg-[var(--color-brand-blue)] text-white" onClick={() => handleDownloadDoc(viewDoc)}>
 <Download size={14} className="mr-1" /> Download
 </Button>
 </div>
 )}
 </div>
 </DialogContent>
 </Dialog>
 </div>
 );
};

export default DocumentsTab;
