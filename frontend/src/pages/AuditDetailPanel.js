import { useState } from 'react';
import { useAuth } from '@/App';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { FileText, Upload, Download, Calendar, Clipboard, ExternalLink } from 'lucide-react';

const AuditDetailPanel = ({ audit, onClose }) => {
 const { API } = useAuth();
 const [uploading, setUploading] = useState(false);
 const [attachedFiles, setAttachedFiles] = useState(audit.attached_files || []);
 const displayName = audit.equipment_name || audit.equipment_type;

 const handleUploadToAudit = async (e) => {
 const file = e.target.files[0];
 if (!file) return;
 setUploading(true);
 const token = localStorage.getItem('token');
 try {
 const formData = new FormData();
 formData.append('file', file);
 const res = await axios.post(`${API}/files/upload?category=audits`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
 });
 setAttachedFiles([...attachedFiles, res.data]);
 notify.success('File attached to audit');
 } catch {
 notify.error('Upload failed');
 } finally {
 setUploading(false);
 e.target.value = '';
 }
 };

 const handlePrintAudit = () => {
 const printWindow = window.open('', '_blank');
 if (!printWindow) return;
 printWindow.document.write(`
 <!DOCTYPE html><html><head><title>Audit Report - ${displayName}</title>
 <style>body{font-family:Arial;padding:30px;color:#333;max-width:800px;margin:0 auto;}
 h1{color:var(--color-brand-blue);border-bottom:2px solid var(--color-brand-blue);padding-bottom:10px;}
 .meta{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:20px 0;background:var(--color-neutral-10);padding:15px;border-radius:8px;}
 .meta div{font-size:14px;}.meta strong{display:block;color:#666;font-size:12px;margin-bottom:2px;}
 .report{white-space:pre-wrap;line-height:1.8;font-size:14px;background:#fff;padding:20px;border:1px solid #eee;border-radius:8px;}
 @media print{body{padding:0;}}</style></head><body>
 <h1>Audit Report: ${displayName}</h1>
 <div class="meta">
 <div><strong>Date</strong>${new Date(audit.created_at).toLocaleDateString()}</div>
 <div><strong>Equipment Type</strong>${audit.equipment_type || 'N/A'}</div>
 <div><strong>Usage Frequency</strong>${audit.usage_frequency || 'N/A'}</div>
 <div><strong>Last Maintenance</strong>${audit.last_maintenance || 'N/A'}</div>
 ${audit.equipment_serial ? `<div><strong>Serial Number</strong>${audit.equipment_serial}</div>` : ''}
 <div><strong>Notes</strong>${audit.notes || 'None'}</div>
 </div>
 <h2>Report</h2>
 <div class="report">${audit.report}</div>
 </body></html>
 `);
 printWindow.document.close();
 printWindow.print();
 };

 return (
 <Dialog open={true} onOpenChange={onClose}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="audit-detail-dialog">
 <DialogHeader>
 <DialogTitle className="text-white flex items-center gap-2">
 <Clipboard size={20} className="text-[var(--color-brand-blue)]" />
 Audit Report: {displayName}
 </DialogTitle>
 </DialogHeader>

 {/* Meta Info */}
 <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
 <div className="p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <span className="text-[var(--color-text-muted)] text-xs block">Date</span>
 <p className="text-white font-medium flex items-center gap-1"><Calendar size={12} /> {new Date(audit.created_at).toLocaleDateString()}</p>
 </div>
 <div className="p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <span className="text-[var(--color-text-muted)] text-xs block">Usage</span>
 <p className="text-white font-medium capitalize">{audit.usage_frequency || 'N/A'}</p>
 </div>
 <div className="p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <span className="text-[var(--color-text-muted)] text-xs block">Last Maintenance</span>
 <p className="text-white font-medium">{audit.last_maintenance || 'N/A'}</p>
 </div>
 <div className="p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <span className="text-[var(--color-text-muted)] text-xs block">Status</span>
 <Badge className="bg-green-500/20 text-green-400">Completed</Badge>
 </div>
 </div>

 {audit.notes && (
 <div className="p-3 bg-[rgb(var(--rgb-brand-blue)/0.1)] border border-[rgb(var(--rgb-brand-blue)/0.3)] rounded-lg">
 <span className="text-[var(--color-brand-blue)] text-sm font-medium">Additional Notes:</span>
 <p className="text-white text-sm mt-1">{audit.notes}</p>
 </div>
 )}

 {/* Full Report */}
 <div>
 <h3 className="text-white font-semibold mb-2">Full Report</h3>
 <div className="p-4 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg text-[var(--color-text-muted)] text-sm whitespace-pre-wrap leading-relaxed max-h-[300px] overflow-y-auto" data-testid="audit-full-report">
 {audit.report}
 </div>
 </div>

 {/* File Attachments */}
 <div className="p-4 bg-[var(--theme-surface)] border border-white/10 rounded-lg">
 <div className="flex items-center justify-between mb-3">
 <h4 className="text-white font-medium flex items-center gap-2">
 <FileText size={16} /> Attached Files ({attachedFiles.length})
 </h4>
 <label className="cursor-pointer">
 <input type="file" className="hidden" onChange={handleUploadToAudit} accept="image/*,.pdf,.doc,.docx" data-testid="audit-file-upload" />
 <span className="flex items-center gap-1 text-sm text-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue-alt)]">
 <Upload size={14} /> {uploading ? 'Uploading...' : 'Attach File'}
 </span>
 </label>
 </div>
 {attachedFiles.length > 0 ? (
 <div className="space-y-2">
 {attachedFiles.map(f => (
 <div key={f.id} className="flex items-center justify-between p-2 bg-[var(--color-ink-alt)] border border-white/10 rounded">
 <div className="flex items-center gap-2">
 <FileText size={14} className="text-[var(--color-brand-blue)]" />
 <span className="text-white text-sm">{f.original_filename || f.filename}</span>
 </div>
 {f.download_url && (
 <a href={f.download_url} target="_blank" rel="noreferrer" className="text-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue-alt)]">
 <ExternalLink size={14} />
 </a>
 )}
 </div>
 ))}
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-sm">No files attached. Upload photos, PDFs, or documents.</p>
 )}
 </div>

 {/* Actions */}
 <div className="flex gap-3">
 <Button onClick={handlePrintAudit} className="flex-1" data-testid="print-audit-btn">
 <Download size={16} className="mr-2" /> Download / Print PDF
 </Button>
 </div>
 </DialogContent>
 </Dialog>
 );
};

export default AuditDetailPanel;
