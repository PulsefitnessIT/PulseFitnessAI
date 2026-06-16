import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import axios from 'axios';
import EquipmentPlaceholder from '@/components/equipment/EquipmentPlaceholder';
import {
 AlertTriangle, CheckCircle, MapPin, Wrench, ArrowLeft, Send,
 ClipboardCheck, Camera, X, Loader2, Shield, Clock, FileText, ScanLine
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * QRPhotoUploader — compact photo upload triggered from the QR scan screen.
 * Reuses the same client-side compression (1920 px, JPEG q=0.82) and the
 * authenticated POST /api/equipment/{id}/photo endpoint that the equipment
 * detail dialog uses, but with a mobile-first UX: huge Take-Photo button,
 * progress indicator, toast feedback, auto-close on success.
 */
const QRPhotoUploader = ({ equipmentId, currentPhotoUrl, onUploaded }) => {
 const cameraRef = useRef(null);
 const fileRef = useRef(null);
 const [uploading, setUploading] = useState(false);
 const [progress, setProgress] = useState(0);

 const doUpload = async (file) => {
 if (!file || !file.type.startsWith('image/')) return;
 if (file.size > 20 * 1024 * 1024) { alert('Max 20 MB'); return; }
 setUploading(true);
 setProgress(0);
 try {
 // Client-side compression — same parameters as EquipmentPhotoUpload.
 let compressed = file;
 if (['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
 compressed = await new Promise((resolve, reject) => {
 const reader = new FileReader();
 reader.onload = () => {
 const img = new Image();
 img.onload = () => {
 const MAX = 1920;
 const scale = Math.min(1, MAX / Math.max(img.width, img.height));
 const w = Math.round(img.width * scale);
 const h = Math.round(img.height * scale);
 const canvas = document.createElement('canvas');
 canvas.width = w; canvas.height = h;
 canvas.getContext('2d').drawImage(img, 0, 0, w, h);
 canvas.toBlob(
 (blob) => resolve(new File([blob], 'scan-upload.jpg', { type: 'image/jpeg' })),
 'image/jpeg',
 0.82,
 );
 };
 img.onerror = reject;
 img.src = reader.result;
 };
 reader.onerror = reject;
 reader.readAsDataURL(file);
 });
 }
 const fd = new FormData();
 fd.append('file', compressed);
 const token = localStorage.getItem('token');
 const res = await axios.post(`${API}/equipment/${equipmentId}/photo`, fd, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
 onUploadProgress: (e) => { if (e.total) setProgress(Math.round((e.loaded / e.total) * 100)); },
 });
 onUploaded?.(res.data?.photo_url);
 } catch (e) {
 alert(e.response?.data?.detail || 'Upload failed');
 }
 setUploading(false);
 setProgress(0);
 };

 if (uploading) {
 return (
 <div className="w-full h-40 bg-[var(--color-ink-alt)] rounded-lg border border-white/10 flex flex-col items-center justify-center gap-3">
 <Loader2 size={28} className="animate-spin text-[var(--color-brand-cyan-hover)]" />
 <div className="w-40 h-1.5 bg-white/10 rounded-full overflow-hidden">
 <div className="h-full bg-[var(--color-brand-cyan-hover)] transition-all" style={{ width: `${progress}%` }} />
 </div>
 <p className="text-xs text-[var(--color-text-muted)]">{progress < 100 ? `Uploading ${progress}%` : 'Saving…'}</p>
 </div>
 );
 }

 return (
 <div className="space-y-3">
 {currentPhotoUrl && (
 <div className="relative w-full h-32 rounded-lg overflow-hidden bg-[var(--color-ink-alt)] border border-white/10">
 <img src={currentPhotoUrl} alt="Current" className="w-full h-full object-contain" />
 <div className="absolute bottom-1.5 left-1.5 px-1.5 py-0.5 rounded-sm bg-black/70 text-[9px] uppercase tracking-wider text-white/70">
 Current photo
 </div>
 </div>
 )}
 <Button
 onClick={() => cameraRef.current?.click()}
 className="w-full bg-[var(--color-brand-cyan-hover)] hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.9)] text-black h-14 text-lg font-semibold"
 data-testid="qr-take-photo-btn"
 >
 <Camera size={20} className="mr-2" /> Take Photo
 </Button>
 <Button
 onClick={() => fileRef.current?.click()}
 variant="outline"
 className="w-full border-white/10 text-white hover:bg-white/5 h-12"
 data-testid="qr-choose-file-btn"
 >
 Choose from Files
 </Button>
 <p className="text-[11px] text-[var(--color-text-faint-alt)] text-center">
 Auto-compressed to &lt;1 MB before upload. JPG, PNG, WebP, or HEIC.
 </p>
 <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => doUpload(e.target.files?.[0])} />
 <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => doUpload(e.target.files?.[0])} />
 </div>
 );
};

/* ── In-browser QR Scanner ── */
const QRCamera = ({ onScan, onClose }) => {
 const videoRef = useRef(null);
 const streamRef = useRef(null);
 const scanningRef = useRef(true);
 const [error, setError] = useState(null);

 const stopCamera = useCallback(() => {
 scanningRef.current = false;
 if (streamRef.current) {
 streamRef.current.getTracks().forEach(t => t.stop());
 streamRef.current = null;
 }
 }, []);

 useEffect(() => {
 let raf;
 const start = async () => {
 try {
 const stream = await navigator.mediaDevices.getUserMedia({
 video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
 });
 streamRef.current = stream;
 if (videoRef.current) {
 videoRef.current.srcObject = stream;
 await videoRef.current.play();
 }
 // Use BarcodeDetector if available, else canvas fallback
 if ('BarcodeDetector' in window) {
 const detector = new window.BarcodeDetector({ formats: ['qr_code'] });
 const tick = async () => {
 if (!scanningRef.current || !videoRef.current) return;
 try {
 const codes = await detector.detect(videoRef.current);
 if (codes.length > 0) {
 stopCamera();
 onScan(codes[0].rawValue);
 return;
 }
 } catch { /* ignore frame errors */ }
 raf = requestAnimationFrame(tick);
 };
 raf = requestAnimationFrame(tick);
 } else {
 setError('native');
 }
 } catch {
 setError('camera');
 }
 };
 start();
 return () => { cancelAnimationFrame(raf); stopCamera(); };
 }, [onScan, stopCamera]);

 if (error === 'camera') {
 return (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6 text-center" data-testid="qr-camera-error">
 <Camera size={40} className="mx-auto mb-3 text-red-400" />
 <p className="text-white font-medium mb-1">Camera Access Required</p>
 <p className="text-[var(--color-text-muted)] text-sm mb-4">Please allow camera access in your browser settings to scan QR codes.</p>
 <Button onClick={onClose} variant="outline" className="border-white/10 text-white">Close</Button>
 </Card>
 );
 }

 return (
 <div className="relative rounded-xl overflow-hidden border border-white/10" data-testid="qr-camera-scanner">
 <video ref={videoRef} className="w-full rounded-xl" playsInline muted style={{ maxHeight: '60vh' }} />
 {/* Scan overlay */}
 <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
 <div className="w-56 h-56 border-2 border-[var(--color-brand-blue)] rounded-2xl relative">
 <div className="absolute top-0 left-0 w-8 h-8 border-t-4 border-l-4 border-[var(--color-brand-blue)] rounded-tl-xl" />
 <div className="absolute top-0 right-0 w-8 h-8 border-t-4 border-r-4 border-[var(--color-brand-blue)] rounded-tr-xl" />
 <div className="absolute bottom-0 left-0 w-8 h-8 border-b-4 border-l-4 border-[var(--color-brand-blue)] rounded-bl-xl" />
 <div className="absolute bottom-0 right-0 w-8 h-8 border-b-4 border-r-4 border-[var(--color-brand-blue)] rounded-br-xl" />
 <div className="absolute left-2 right-2 top-1/2 h-0.5 bg-[rgb(var(--rgb-brand-blue)/0.6)] animate-pulse" />
 </div>
 </div>
 <div className="absolute top-3 left-0 right-0 text-center">
 <span className="bg-black/60 text-white text-xs px-3 py-1 rounded-full">Point at QR code on next machine</span>
 </div>
 {error === 'native' && (
 <div className="absolute bottom-16 left-0 right-0 text-center">
 <span className="bg-amber-600/90 text-white text-xs px-3 py-1 rounded-full">QR detection not supported — try Chrome or Safari</span>
 </div>
 )}
 <div className="absolute bottom-3 left-0 right-0 text-center">
 <Button onClick={() => { stopCamera(); onClose(); }} size="sm" variant="outline" className="border-white/30 text-white bg-black/50" data-testid="qr-camera-close">
 <X size={14} className="mr-1" /> Cancel
 </Button>
 </div>
 </div>
 );
};

const QRScanPage = () => {
 const { equipmentId } = useParams();
 const { t } = useTranslation();
 const navigate = useNavigate();
 const [equipment, setEquipment] = useState(null);
 const [loading, setLoading] = useState(true);
 const [error, setError] = useState(null);
 const [mode, setMode] = useState(null);
 const [showScanner, setShowScanner] = useState(false);

 // Fault report
 const [faultSubmitted, setFaultSubmitted] = useState(false);
 const [submitting, setSubmitting] = useState(false);
 const [formData, setFormData] = useState({
 description: '', severity: 'medium', reporter_name: '', reporter_email: '',
 });
 const [photo, setPhoto] = useState(null);
 const [photoPreview, setPhotoPreview] = useState(null);
 const fileInputRef = useRef(null);
 const [aiTriage, setAiTriage] = useState(null);

 // Maintenance check
 const [checkItems, setCheckItems] = useState([]);
 const [checkedItems, setCheckedItems] = useState({});
 const [checkNotes, setCheckNotes] = useState('');
 const [checkerName, setCheckerName] = useState('');
 const [checkSubmitted, setCheckSubmitted] = useState(false);
 const [checkLoading, setCheckLoading] = useState(false);

 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
 useEffect(() => { loadEquipment(); }, [equipmentId]);

 const loadEquipment = async () => {
 try {
 const res = await axios.get(`${API}/public/equipment/${equipmentId}`);
 setEquipment(res.data);
 } catch (err) {
 setError(err.response?.status === 404 ? 'Equipment not found' : 'Failed to load equipment');
 } finally {
 setLoading(false);
 }
 };

 const loadCheckItems = async () => {
 setCheckLoading(true);
 try {
 const res = await axios.get(`${API}/public/equipment/${equipmentId}/check-items`);
 setCheckItems(res.data.check_items || []);
 setCheckedItems({});
 } catch { setCheckItems([]); }
 finally { setCheckLoading(false); }
 };

 const handleSelectMode = (m) => {
 setMode(m);
 if (m === 'check') loadCheckItems();
 };

 const handlePhotoChange = (e) => {
 const file = e.target.files?.[0];
 if (!file) return;
 setPhoto(file);
 setPhotoPreview(URL.createObjectURL(file));
 };

 const removePhoto = () => {
 setPhoto(null);
 if (photoPreview) URL.revokeObjectURL(photoPreview);
 setPhotoPreview(null);
 if (fileInputRef.current) fileInputRef.current.value = '';
 };

 const handleFaultSubmit = async (e) => {
 e.preventDefault();
 if (!formData.description.trim()) return;
 setSubmitting(true);
 try {
 const fd = new FormData();
 fd.append('description', formData.description);
 fd.append('severity', formData.severity);
 fd.append('reporter_name', formData.reporter_name);
 fd.append('reporter_email', formData.reporter_email);
 if (photo) fd.append('photo', photo);
 const res = await axios.post(`${API}/public/equipment/${equipmentId}/report-fault`, fd);
 setAiTriage(res.data.ai_triage);
 setFaultSubmitted(true);
 } catch {
 alert('Failed to submit report. Please try again.');
 } finally {
 setSubmitting(false);
 }
 };

 const toggleCheckItem = (item) => {
 setCheckedItems(prev => ({ ...prev, [item]: !prev[item] }));
 };

 const handleCheckAll = () => {
 const allChecked = checkItems.every(item => checkedItems[item]);
 if (allChecked) setCheckedItems({});
 else {
 const all = {};
 checkItems.forEach(item => { all[item] = true; });
 setCheckedItems(all);
 }
 };

 const handleCheckSubmit = async () => {
 if (!checkerName.trim()) { alert('Please enter your name'); return; }
 const items = checkItems.map(item => ({ name: item, checked: !!checkedItems[item] }));
 setSubmitting(true);
 try {
 await axios.post(`${API}/public/equipment/${equipmentId}/complete-check`, {
 items, completed_by: checkerName.trim(), notes: checkNotes,
 });
 setCheckSubmitted(true);
 } catch { alert('Failed to submit check. Please try again.'); }
 finally { setSubmitting(false); }
 };

 const resetAll = () => {
 setMode(null);
 setFaultSubmitted(false);
 setCheckSubmitted(false);
 setShowScanner(false);
 setAiTriage(null);
 setFormData({ description: '', severity: 'medium', reporter_name: '', reporter_email: '' });
 removePhoto();
 setCheckedItems({});
 setCheckNotes('');
 };

 const handleScanResult = (url) => {
 setShowScanner(false);
 // Extract equipment ID from scanned URL (format: .../scan/{id})
 const match = url.match(/\/scan\/([a-f0-9-]+)/i);
 if (match) {
 navigate(`/scan/${match[1]}`);
 window.location.reload();
 } else if (url.includes('/scan/')) {
 // Fallback: navigate to the full URL
 window.location.href = url;
 } else {
 alert('Invalid QR code — please scan a Pulse Fitness equipment QR code.');
 }
 };

 const checkedCount = Object.values(checkedItems).filter(Boolean).length;

 if (loading) {
 return (
 <div className="min-h-screen bg-[var(--color-ink-alt)] flex items-center justify-center">
 <div className="animate-pulse text-[var(--color-brand-blue)] text-lg">Loading equipment...</div>
 </div>
 );
 }

 if (error) {
 return (
 <div className="min-h-screen bg-[var(--color-ink-alt)] flex items-center justify-center p-4">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-8 text-center max-w-md w-full">
 <AlertTriangle size={48} className="mx-auto mb-4 text-red-400" />
 <h2 className="text-xl font-bold text-white mb-2">{t('qr.equipment_not_found')}</h2>
 <p className="text-[var(--color-text-muted)] mb-4">{error}</p>
 <p className="text-[var(--color-text-muted)] text-xs mb-6 border-l-2 border-yellow-500/50 pl-3 text-left">
 This usually means the QR code was printed against a different environment. Re-generate the QR from the equipment page on <strong>this site</strong> and print the new sticker.
 </p>
 <Link to="/"><Button className="bg-[var(--color-brand-blue)] text-white"><ArrowLeft size={16} className="mr-2" /> Back to Home</Button></Link>
 </Card>
 </div>
 );
 }

 // ── Fault Submitted + AI Triage Result ──
 if (faultSubmitted) {
 return (
 <div className="min-h-screen bg-[var(--color-ink-alt)] p-4" data-testid="fault-submitted-page">
 <div className="max-w-lg mx-auto">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6 text-center mb-4" data-testid="fault-submitted-card">
 <CheckCircle size={48} className="mx-auto mb-3 text-green-400" />
 <h2 className="text-xl font-bold text-white mb-1">Fault Reported</h2>
 <p className="text-[var(--color-text-muted)] text-sm">
 The maintenance team has been notified and will address this as soon as possible.
 </p>
 </Card>

 {/* AI Triage Result */}
 {aiTriage ? (
 <Card className="bg-[var(--theme-surface)] border-[rgb(var(--rgb-brand-blue)/0.3)] p-5 mb-4" data-testid="ai-triage-card">
 <div className="flex items-center gap-2 mb-4">
 <div className="w-8 h-8 rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center">
 <Wrench size={16} className="text-[var(--color-brand-blue)]" />
 </div>
 <div>
 <h3 className="text-white font-semibold text-sm">AI Triage Assessment</h3>
 <p className="text-[var(--color-text-muted)] text-xs">Automated analysis of the reported fault</p>
 </div>
 </div>

 {/* Severity */}
 <div className="flex items-center gap-2 mb-3">
 <Shield size={14} className={
 aiTriage.severity_assessment === 'critical' ? 'text-red-400' :
 aiTriage.severity_assessment === 'medium' ? 'text-yellow-400' : 'text-green-400'
 } />
 <Badge className={
 aiTriage.severity_assessment === 'critical' ? 'bg-red-500/20 text-red-400' :
 aiTriage.severity_assessment === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
 'bg-green-500/20 text-green-400'
 } data-testid="triage-severity">
 {(aiTriage.severity_assessment || 'unknown').toUpperCase()}
 </Badge>
 {aiTriage.can_fix_onsite !== undefined && (
 <Badge className={aiTriage.can_fix_onsite ? 'bg-green-500/20 text-green-400' : 'bg-orange-500/20 text-orange-400'} data-testid="triage-onsite">
 {aiTriage.can_fix_onsite ? 'Can Fix On-Site' : 'Needs Engineer'}
 </Badge>
 )}
 </div>

 {/* Diagnosis */}
 {aiTriage.diagnosis && (
 <div className="mb-3">
 <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider mb-1">Diagnosis</p>
 <p className="text-white text-sm" data-testid="triage-diagnosis">{aiTriage.diagnosis}</p>
 </div>
 )}

 {/* Likely Cause */}
 {aiTriage.likely_cause && (
 <div className="mb-3">
 <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider mb-1">Likely Cause</p>
 <p className="text-white text-sm" data-testid="triage-cause">{aiTriage.likely_cause}</p>
 </div>
 )}

 {/* Recommended Action */}
 {aiTriage.recommended_action && (
 <div className="mb-3">
 <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider mb-1">Recommended Action</p>
 <p className="text-white text-sm" data-testid="triage-action">{aiTriage.recommended_action}</p>
 </div>
 )}

 {/* Est. Time */}
 {aiTriage.estimated_repair_time && (
 <div className="flex items-center gap-2 mb-3">
 <Clock size={14} className="text-[var(--color-brand-blue)]" />
 <span className="text-[var(--color-text-muted)] text-sm">Est. repair time: <span className="text-white" data-testid="triage-time">{aiTriage.estimated_repair_time}</span></span>
 </div>
 )}

 {/* Safety Note */}
 {aiTriage.safety_note && aiTriage.safety_note !== 'null' && (
 <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg mb-3" data-testid="triage-safety">
 <p className="text-red-400 text-sm font-medium">
 <AlertTriangle size={14} className="inline mr-1" /> {aiTriage.safety_note}
 </p>
 </div>
 )}

 {/* Repair Steps */}
 {aiTriage.repair_steps && aiTriage.repair_steps.length > 0 && (
 <div>
 <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider mb-2">{t('triage.repair_steps')}</p>
 <div className="space-y-2" data-testid="triage-steps">
 {aiTriage.repair_steps.map((s, idx) => (
 <div key={s.step || s.instruction} className="flex gap-3 p-2 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <div className="w-6 h-6 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center flex-shrink-0">
 <span className="text-[var(--color-brand-blue)] text-xs font-bold">{s.step || idx + 1}</span>
 </div>
 <p className="text-white text-sm flex-1">{s.instruction}</p>
 </div>
 ))}
 </div>
 </div>
 )}
 </Card>
 ) : submitting ? null : (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5 mb-4 text-center" data-testid="no-triage-card">
 <p className="text-[var(--color-text-muted)] text-sm">AI triage was not available for this report.</p>
 </Card>
 )}

 {showScanner ? (
 <QRCamera onScan={handleScanResult} onClose={() => setShowScanner(false)} />
 ) : (
 <div className="space-y-3">
 <Button onClick={() => setShowScanner(true)} className="w-full h-12 text-base font-semibold" data-testid="scan-next-machine-fault-btn">
 <ScanLine size={18} className="mr-2" /> Scan Next Machine
 </Button>
 <Button onClick={resetAll} variant="outline" className="w-full border-white/10 text-white" data-testid="back-to-options-btn">
 Back to This Machine
 </Button>
 </div>
 )}
 </div>
 </div>
 );
 }

 // ── Check Submitted ──
 if (checkSubmitted) {
 return (
 <div className="min-h-screen bg-[var(--color-ink-alt)] flex items-center justify-center p-4">
 <div className="max-w-md w-full space-y-4">
 {showScanner ? (
 <QRCamera onScan={handleScanResult} onClose={() => setShowScanner(false)} />
 ) : (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-8 text-center" data-testid="check-submitted-card">
 <CheckCircle size={56} className="mx-auto mb-4 text-green-400" />
 <h2 className="text-2xl font-bold text-white mb-2">Maintenance Check Complete</h2>
 <p className="text-[var(--color-text-muted)] mb-2">
 {checkedCount}/{checkItems.length} items checked for <span className="text-white font-medium">{equipment.name}</span>
 </p>
 <p className="text-[var(--color-text-muted)] text-sm mb-6">This check is now recorded and visible on the dashboard.</p>
 <div className="space-y-3">
 <Button onClick={() => setShowScanner(true)} className="w-full h-12 text-base font-semibold" data-testid="scan-next-machine-btn">
 <ScanLine size={18} className="mr-2" /> Scan Next Machine
 </Button>
 <Button onClick={resetAll} variant="outline" className="w-full border-white/10 text-white" data-testid="back-to-options-btn-check">
 Back to This Machine
 </Button>
 </div>
 </Card>
 )}
 </div>
 </div>
 );
 }

 return (
 <div className="min-h-screen bg-[var(--color-ink-alt)] p-4" data-testid="qr-scan-page">
 <div className="max-w-lg mx-auto">
 {/* Header — Iter 216d: respect org branding (Pulse Fitness vs Pulse Fitness). */}
 <div className="flex items-center justify-between mb-6">
 <div className="flex items-center gap-3">
 <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: equipment.brand_color || 'var(--color-brand-blue)' }}>
 {equipment.brand_logo ? (
   <img src={equipment.brand_logo} alt="" className="w-full h-full object-contain rounded-lg" />
 ) : (
   <Wrench size={20} className="text-white" />
 )}
 </div>
 <div>
 <h1 className="text-white font-bold text-lg leading-tight">{equipment.brand_name || 'Pulse Fitness AI'}</h1>
 {equipment.gym_name && equipment.gym_name !== equipment.brand_name && <p className="text-[var(--color-text-muted)] text-xs">{equipment.gym_name}</p>}
 </div>
 </div>
 <Badge className={equipment.status === 'In Service' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'} data-testid="equipment-status-badge">
 {equipment.status}
 </Badge>
 </div>

 {/* Equipment Card */}
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6 mb-4" data-testid="equipment-info-card">
 {equipment.photo_url ? (
 <div className="mb-4 rounded-lg overflow-hidden">
 <img src={equipment.photo_url} alt={equipment.name} className="w-full h-48 object-cover" />
 </div>
 ) : (
 <div className="mb-4 h-48">
 <EquipmentPlaceholder
 manufacturer={equipment.manufacturer || equipment.supplier}
 equipmentType={equipment.equipment_type}
 model={equipment.model}
 testId="qr-scan-placeholder"
 />
 </div>
 )}
 <h2 className="text-2xl font-bold text-white mb-1" data-testid="equipment-name">{equipment.name}</h2>
 <p className="text-[var(--color-brand-blue)] font-medium mb-4">{equipment.equipment_type}</p>
 <div className="grid grid-cols-2 gap-4">
 {equipment.manufacturer && <div><p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">{t('equipment.manufacturer')}</p><p className="text-white text-sm font-medium">{equipment.manufacturer}</p></div>}
 {equipment.model && <div><p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">{t('equipment.model')}</p><p className="text-white text-sm font-medium">{equipment.model}</p></div>}
 {equipment.serial_number && <div><p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">{t('equipment.serial_number')}</p><p className="text-white text-sm font-mono">{equipment.serial_number}</p></div>}
 {equipment.location && <div><p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">{t('equipment.location')}</p><p className="text-white text-sm font-medium flex items-center gap-1"><MapPin size={12} className="text-[var(--color-brand-blue)]" />{equipment.location}</p></div>}
 {equipment.supplier && <div className="col-span-2" data-testid="qr-equip-supplier"><p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">Supplier</p><p className="text-indigo-400 text-sm font-medium">{equipment.supplier}</p></div>}
 </div>
 {equipment.open_issues > 0 && (
 <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
 <p className="text-red-400 text-sm font-medium"><AlertTriangle size={14} className="inline mr-1" />{equipment.open_issues} open issue{equipment.open_issues > 1 ? 's' : ''}</p>
 </div>
 )}
 {/* Coverage Status */}
 {equipment.coverage && (
 <div className={`mt-4 p-3 rounded-lg border flex items-center gap-2 ${
 equipment.coverage.covered
 ? equipment.coverage.type === 'warranty'
 ? 'bg-green-500/10 border-green-500/20'
 : 'bg-[rgb(var(--rgb-brand-blue)/0.1)] border-[rgb(var(--rgb-brand-blue)/0.2)]'
 : 'bg-amber-500/10 border-amber-500/20'
 }`} data-testid="qr-coverage-badge">
 <Shield size={16} className={
 equipment.coverage.covered
 ? equipment.coverage.type === 'warranty' ? 'text-green-400' : 'text-[var(--color-brand-blue)]'
 : 'text-amber-400'
 } />
 <span className={`text-sm font-medium ${
 equipment.coverage.covered ? 'text-white' : 'text-amber-400'
 }`}>
 {equipment.coverage.label}
 </span>
 </div>
 )}

 {/* Warranty & Contract Details */}
 {(equipment.warranty_expiry || equipment.sla_level || equipment.purchase_date || equipment.warranty_code) && (
 <div className="mt-4 border-t border-white/10 pt-4" data-testid="qr-warranty-details">
 <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider mb-3 flex items-center gap-1.5">
 <FileText size={12} className="text-[var(--color-brand-blue)]" /> Warranty & Contract Details
 </p>
 <div className="grid grid-cols-2 gap-3">
 {equipment.purchase_date && (
 <div>
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wider">Purchase Date</p>
 <p className="text-white text-sm" data-testid="qr-purchase-date">{new Date(equipment.purchase_date).toLocaleDateString()}</p>
 </div>
 )}
 {equipment.warranty_expiry && (
 <div>
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wider">Warranty Expiry</p>
 <p className="text-white text-sm" data-testid="qr-warranty-expiry">{new Date(equipment.warranty_expiry).toLocaleDateString()}</p>
 </div>
 )}
 {equipment.warranty_code && (
 <div>
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wider">Warranty Code</p>
 <p className="text-white text-sm font-mono" data-testid="qr-warranty-code">{equipment.warranty_code}</p>
 </div>
 )}
 {equipment.sla_level && (
 <div>
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wider">SLA Level</p>
 <p className="text-white text-sm" data-testid="qr-sla-level">{equipment.sla_level}</p>
 </div>
 )}
 {equipment.sla_expiry && (
 <div>
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wider">Contract Expiry</p>
 <p className="text-white text-sm" data-testid="qr-sla-expiry">{new Date(equipment.sla_expiry).toLocaleDateString()}</p>
 </div>
 )}
 {equipment.sla_contract_ref && (
 <div>
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wider">Contract Ref</p>
 <p className="text-white text-sm font-mono" data-testid="qr-contract-ref">{equipment.sla_contract_ref}</p>
 </div>
 )}
 </div>
 </div>
 )}
 </Card>

 {/* ── Landing ── */}
 {mode === null && (
 <div className="space-y-3" data-testid="qr-action-buttons">
 <Button onClick={() => handleSelectMode('check')} className="w-full h-14 text-lg font-semibold" data-testid="start-maintenance-check-btn">
 <ClipboardCheck size={20} className="mr-2" /> {t('qr.maintenance_check')}
 </Button>
 <Button onClick={() => handleSelectMode('fault')} className="w-full bg-red-600 hover:bg-red-700 text-white h-14 text-lg font-semibold" data-testid="report-fault-btn">
 <AlertTriangle size={20} className="mr-2" /> {t('qr.log_fault')}
 </Button>
 {/* Photo upload — authenticated staff only. Gives walk-around
 maintainers a 2-tap path: scan QR → snap photo → done.
 Unauthenticated scanners see just the above two buttons. */}
 {typeof window !== 'undefined' && localStorage.getItem('token') && (
 <Button
 onClick={() => handleSelectMode('photo')}
 className="w-full bg-[var(--color-brand-cyan-hover)] hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.9)] text-black h-14 text-lg font-semibold"
 data-testid="upload-photo-btn"
 >
 <Camera size={20} className="mr-2" /> Update Equipment Photo
 </Button>
 )}
 </div>
 )}

 {/* ── Photo Upload (authenticated only) ── */}
 {mode === 'photo' && (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="qr-photo-upload-form">
 <div className="flex items-center justify-between mb-4">
 <h3 className="text-white font-semibold text-lg">Update Equipment Photo</h3>
 <button onClick={() => setMode(null)} className="text-[var(--color-text-muted)] hover:text-white" data-testid="back-from-photo-btn"><ArrowLeft size={18} /></button>
 </div>
 <p className="text-[var(--color-text-muted)] text-sm mb-4">
 Snap a photo of {equipment?.name || 'this machine'}. It'll replace the current photo and show up on the next fault report.
 </p>
 <QRPhotoUploader
 equipmentId={equipmentId}
 currentPhotoUrl={equipment?.photo_url}
 onUploaded={(url) => {
 setEquipment(prev => prev ? { ...prev, photo_url: url } : prev);
 setMode(null);
 }}
 />
 </Card>
 )}

 {/* ── Fault Report Form ── */}
 {mode === 'fault' && (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="fault-report-form">
 <div className="flex items-center justify-between mb-4">
 <h3 className="text-white font-semibold text-lg">{t('qr.log_fault')}</h3>
 <button onClick={() => { setMode(null); removePhoto(); }} className="text-[var(--color-text-muted)] hover:text-white" data-testid="back-from-fault-btn"><ArrowLeft size={18} /></button>
 </div>
 <form onSubmit={handleFaultSubmit} className="space-y-4">
 <div>
 <label className="text-[var(--color-text-muted)] text-sm block mb-1">{t('qr.description_label')} *</label>
 <Textarea
 value={formData.description}
 onChange={(e) => setFormData({ ...formData, description: e.target.value })}
 placeholder="Describe the fault... e.g. 'Belt is slipping when running at high speed'"
 required rows={3}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white"
 data-testid="fault-description-input"
 />
 </div>

 {/* Photo Capture */}
 <div>
 <label className="text-[var(--color-text-muted)] text-sm block mb-1">Photo of the fault (optional)</label>
 {photoPreview ? (
 <div className="relative rounded-lg overflow-hidden border border-white/10" data-testid="photo-preview">
 <img src={photoPreview} alt="Fault" className="w-full h-48 object-cover" />
 <button
 type="button"
 onClick={removePhoto}
 className="absolute top-2 right-2 w-7 h-7 bg-black/70 rounded-full flex items-center justify-center text-white hover:bg-red-600 transition-colors"
 data-testid="remove-photo-btn"
 >
 <X size={14} />
 </button>
 </div>
 ) : (
 <button
 type="button"
 onClick={() => fileInputRef.current?.click()}
 className="w-full h-28 border-2 border-dashed border-white/20 rounded-lg flex flex-col items-center justify-center gap-2 text-[var(--color-text-muted)] hover:border-[rgb(var(--rgb-brand-blue)/0.5)] hover:text-[var(--color-brand-blue)] transition-colors"
 data-testid="capture-photo-btn"
 >
 <Camera size={28} />
 <span className="text-sm">Take Photo or Upload</span>
 </button>
 )}
 <input
 ref={fileInputRef}
 type="file"
 accept="image/*"
 capture="environment"
 onChange={handlePhotoChange}
 className="hidden"
 data-testid="photo-file-input"
 />
 </div>

 <div>
 <label className="text-[var(--color-text-muted)] text-sm block mb-1">{t('qr.severity_label')}</label>
 <Select value={formData.severity} onValueChange={(v) => setFormData({ ...formData, severity: v })}>
 <SelectTrigger className="bg-[var(--color-ink-alt)] border-white/10 text-white" data-testid="fault-severity-select"><SelectValue /></SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-white/10">
 <SelectItem value="low" className="text-white">Low - Minor issue</SelectItem>
 <SelectItem value="medium" className="text-white">Medium - Needs attention</SelectItem>
 <SelectItem value="critical" className="text-white">Critical - Machine unsafe / out of order</SelectItem>
 </SelectContent>
 </Select>
 </div>

 <div>
 <label className="text-[var(--color-text-muted)] text-sm block mb-1">{t('qr.your_name')}</label>
 <Input value={formData.reporter_name} onChange={(e) => setFormData({ ...formData, reporter_name: e.target.value })} placeholder="e.g. John" className="bg-[var(--color-ink-alt)] border-white/10 text-white" data-testid="reporter-name-input" />
 </div>
 <div>
 <label className="text-[var(--color-text-muted)] text-sm block mb-1">{t('qr.your_email')}</label>
 <Input type="email" value={formData.reporter_email} onChange={(e) => setFormData({ ...formData, reporter_email: e.target.value })} placeholder="e.g. john@email.com" className="bg-[var(--color-ink-alt)] border-white/10 text-white" data-testid="reporter-email-input" />
 </div>

 <div className="flex gap-3">
 <Button type="button" variant="outline" onClick={() => { setMode(null); removePhoto(); }} className="flex-1 border-white/10 text-white" data-testid="cancel-report-btn">{t('common.cancel')}</Button>
 <Button type="submit" disabled={submitting || !formData.description.trim()} className="flex-1 bg-red-600 hover:bg-red-700 text-white" data-testid="submit-fault-btn">
 {submitting ? <><Loader2 size={16} className="mr-2 animate-spin" /> {t('qr.submitting')}</> : <><Send size={16} className="mr-2" /> {t('qr.submit_fault')}</>}
 </Button>
 </div>
 {submitting && (
 <p className="text-[var(--color-brand-blue)] text-xs text-center animate-pulse" data-testid="triage-loading">AI is analysing the fault{photo ? ' and photo' : ''}...</p>
 )}
 </form>
 </Card>
 )}

 {/* ── Maintenance Check Flow ── */}
 {mode === 'check' && (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="maintenance-check-form">
 <div className="flex items-center justify-between mb-4">
 <div>
 <h3 className="text-white font-semibold text-lg">{t('qr.maintenance_check')}</h3>
 <p className="text-[var(--color-text-muted)] text-sm">{equipment.equipment_type} - {equipment.serial_number || equipment.name}</p>
 </div>
 <button onClick={() => setMode(null)} className="text-[var(--color-text-muted)] hover:text-white" data-testid="back-from-check-btn"><ArrowLeft size={18} /></button>
 </div>
 {checkLoading ? (
 <div className="text-center py-8"><div className="animate-pulse text-[var(--color-brand-blue)]">Loading check items...</div></div>
 ) : (
 <div className="space-y-4">
 <div>
 <label className="text-[var(--color-text-muted)] text-sm block mb-1">{t('qr.checker_name')} *</label>
 <Input value={checkerName} onChange={(e) => setCheckerName(e.target.value)} placeholder="e.g. John Smith" className="bg-[var(--color-ink-alt)] border-white/10 text-white" data-testid="checker-name-input" />
 </div>
 <div className="flex items-center justify-between text-sm">
 <span className="text-[var(--color-text-muted)]">{checkedCount}/{checkItems.length} items checked</span>
 <button onClick={handleCheckAll} className="text-[var(--color-brand-blue)] text-sm hover:underline" data-testid="check-all-btn">
 {checkItems.every(item => checkedItems[item]) ? 'Uncheck All' : 'Check All'}
 </button>
 </div>
 <div className="w-full bg-white/10 rounded-full h-2">
 <div className="bg-[var(--color-brand-blue)] h-2 rounded-full transition-all duration-300" style={{ width: `${checkItems.length > 0 ? (checkedCount / checkItems.length) * 100 : 0}%` }} data-testid="check-progress-bar" />
 </div>
 <div className="space-y-2 max-h-[40vh] overflow-y-auto" data-testid="check-items-list">
 {checkItems.map((item) => (
 <label key={item} className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all ${checkedItems[item] ? 'bg-green-500/10 border-green-500/30' : 'bg-[var(--color-ink-alt)] border-white/10 hover:border-[rgb(var(--rgb-brand-blue)/0.3)]'}`} data-testid={`check-item-${item}`}>
 <input type="checkbox" checked={!!checkedItems[item]} onChange={() => toggleCheckItem(item)} className="w-5 h-5 accent-[var(--color-brand-blue)] flex-shrink-0" />
 <span className={`text-sm flex-1 ${checkedItems[item] ? 'text-white' : 'text-[var(--color-text-muted)]'}`}>{item}</span>
 {checkedItems[item] && <CheckCircle size={16} className="text-green-400 flex-shrink-0" />}
 </label>
 ))}
 </div>
 <div>
 <label className="text-[var(--color-text-muted)] text-sm block mb-1">{t('qr.additional_notes')}</label>
 <Textarea value={checkNotes} onChange={(e) => setCheckNotes(e.target.value)} rows={2} placeholder="Any issues noticed during check..." className="bg-[var(--color-ink-alt)] border-white/10 text-white" data-testid="check-notes-input" />
 </div>
 <div className="flex gap-3">
 <Button type="button" variant="outline" onClick={() => setMode(null)} className="flex-1 border-white/10 text-white" data-testid="cancel-check-btn">{t('common.cancel')}</Button>
 <Button onClick={handleCheckSubmit} disabled={submitting || !checkerName.trim()} className="flex-1" data-testid="submit-check-btn">
 {submitting ? t('qr.submitting') : <><ClipboardCheck size={16} className="mr-2" /> {t('qr.submit_check')} ({checkedCount}/{checkItems.length})</>}
 </Button>
 </div>
 </div>
 )}
 </Card>
 )}

 <p className="text-center text-[var(--color-text-muted)] text-xs mt-8">
 {/* Iter 216d — co-branded footer: Pulse Fitness sites show their own
     brand line + powered-by Pulse Fitness (smaller, beneath). */}
 {equipment.brand_name && equipment.brand_name !== 'Pulse Fitness AI' ? (
   <>
     <span className="block text-[var(--color-text)] font-medium">{equipment.brand_name}</span>
     <span className="block mt-0.5 opacity-70">Powered by Pulse Fitness AI — Scan to report faults or complete checks</span>
   </>
 ) : (
   <>Powered by Pulse Fitness AI — Scan QR codes on any machine to report faults or complete checks</>
 )}
 </p>
 </div>
 </div>
 );
};

export default QRScanPage;
