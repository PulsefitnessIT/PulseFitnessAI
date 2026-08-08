import { useRef, useState } from 'react';
import axios from 'axios';
import { Camera, Image as ImageIcon, Film, Trash2, ShieldAlert, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useAuth } from '@/App';
import { StepTitle, compressToWebP } from './WizardPrimitives';

export function StepAttachments({ urls, onAdd, onRemove, machineName }) {
  const { API } = useAuth();
  const cameraRef = useRef(null);
  const galleryRef = useRef(null);
  const videoRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const MAX_IMAGES = 4;
  const MAX_VIDEOS = 2;
  const imageCount = urls.filter((u) => u.kind === 'image').length;
  const videoCount = urls.filter((u) => u.kind === 'video').length;

  const uploadOne = async (file) => {
    if (!file) return;
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');
    if (!isImage && !isVideo) { notify.error('Pick a photo or short video'); return; }
    if (isImage && imageCount >= MAX_IMAGES) { notify.error(`Max ${MAX_IMAGES} photos`); return; }
    if (isVideo && videoCount >= MAX_VIDEOS) { notify.error(`Max ${MAX_VIDEOS} videos`); return; }
    if (isVideo && file.size > 50 * 1024 * 1024) { notify.error('Video too large (max 50 MB)'); return; }

    setUploading(true);
    setProgress(0);
    try {
      const payload = isImage ? await compressToWebP(file) : file;

      if (!navigator.onLine) {
        onAdd({ offline: true, blob: payload, content_type: payload.type, filename: payload.name || file.name, kind: isImage ? 'image' : 'video', size: payload.size });
        notify.info('Captured offline — will upload when back online');
        return;
      }

      const fd = new FormData();
      fd.append('file', payload, payload.name || file.name);
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/mod/site/attachments`, fd, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => { if (e.total) setProgress(Math.round((e.loaded / e.total) * 100)); },
      });
      const viewerUrl = `${API}/mod/site/attachments/serve?path=${encodeURIComponent(res.data.path)}&token=${encodeURIComponent(token)}`;
      onAdd({ path: res.data.path, url: viewerUrl, kind: res.data.kind, size: res.data.size });
      notify.success(`${isImage ? 'Photo' : 'Video'} added`);
    } catch (err) {
      const networkish = !err.response || err.code === 'ERR_NETWORK';
      if (networkish && file) {
        onAdd({ offline: true, blob: isImage ? await compressToWebP(file) : file, content_type: isImage ? 'image/webp' : file.type, filename: file.name, kind: isImage ? 'image' : 'video', size: file.size });
        notify.info('Network unavailable — saved offline');
      } else {
        notifyApiError(notify, err, 'Upload failed');
      }
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div data-testid="mod-step-attachments">
      <StepTitle eyebrow="Optional" title="Photo or video?" subtitle={machineName ? `${machineName} · a picture saves 10 minutes on site` : 'A picture saves 10 minutes on site'} />

      <div className="mb-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-[12px] text-amber-700 dark:text-amber-200 flex items-start gap-2" data-testid="mod-attach-classification-warning">
        <ShieldAlert size={15} className="shrink-0 mt-0.5 text-amber-500 dark:text-amber-300" />
        <span>
          <strong className="font-bold">OFFICIAL-SENSITIVE ceiling.</strong> Photograph the machine and fault only.
          Do NOT capture documents, screens, whiteboards, NSN/asset labels of other kit, personnel, vehicles,
          or anything that reveals location or operations. Attachments are shared with our service provider.
        </span>
      </div>

      {uploading ? (
        <div className="rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.4)] bg-[rgb(var(--rgb-brand-cyan)/0.06)] p-5 text-center">
          <Loader2 size={22} className="animate-spin text-[var(--color-brand-cyan)] mx-auto mb-2" />
          <div className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Uploading… {progress}%</div>
          <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--theme-surface-3)' }}>
            <div className="h-full bg-[var(--color-brand-cyan)] transition-all" style={{ width: `${progress}%` }} />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <button type="button" onClick={() => cameraRef.current?.click()} disabled={imageCount >= MAX_IMAGES}
            className="rounded-xl border border-dashed border-[rgb(var(--rgb-brand-cyan)/0.5)] bg-[rgb(var(--rgb-brand-cyan)/0.06)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.12)] py-5 text-center text-[var(--color-brand-cyan)] disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="mod-attach-take-photo">
            <Camera size={22} className="mx-auto mb-1.5" />
            <div className="text-xs font-bold">Take Photo</div>
            <div className="text-[10px] opacity-70">{imageCount}/{MAX_IMAGES}</div>
          </button>
          <button type="button" onClick={() => galleryRef.current?.click()} disabled={imageCount >= MAX_IMAGES}
            className="rounded-xl border border-dashed py-5 text-center disabled:opacity-40 disabled:cursor-not-allowed hover:bg-black/5"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
            data-testid="mod-attach-gallery">
            <ImageIcon size={22} className="mx-auto mb-1.5" />
            <div className="text-xs font-bold">From Gallery</div>
          </button>
          <button type="button" onClick={() => videoRef.current?.click()} disabled={videoCount >= MAX_VIDEOS}
            className="col-span-2 rounded-xl border border-dashed py-3.5 text-center disabled:opacity-40 disabled:cursor-not-allowed hover:bg-black/5"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
            data-testid="mod-attach-video">
            <Film size={18} className="inline mr-1.5 -mt-0.5" />
            <span className="text-xs font-bold">Video (up to 50 MB)</span>
            <span className="text-[10px] opacity-70 ml-2">{videoCount}/{MAX_VIDEOS}</span>
          </button>
        </div>
      )}

      <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => uploadOne(e.target.files?.[0])} />
      <input ref={galleryRef} type="file" accept="image/*" className="hidden" onChange={(e) => uploadOne(e.target.files?.[0])} />
      <input ref={videoRef} type="file" accept="video/*" capture="environment" className="hidden" onChange={(e) => uploadOne(e.target.files?.[0])} />

      {urls.length > 0 && (
        <div className="mt-3 grid grid-cols-3 sm:grid-cols-4 gap-2">
          {urls.map((a, i) => {
            const previewSrc = a.url || (a.blob ? URL.createObjectURL(a.blob) : null);
            return (
              <div key={i} className="relative aspect-square rounded-lg overflow-hidden border bg-black/40 group" style={{ borderColor: 'var(--theme-border)' }} data-testid={`mod-attachment-${i}`}>
                {a.kind === 'video'
                  ? <video src={previewSrc} className="w-full h-full object-cover" muted />
                  : <img src={previewSrc} alt="" className="w-full h-full object-cover" />}
                <button type="button" onClick={() => onRemove(i)} className="absolute top-1 right-1 rounded-full bg-black/70 hover:bg-red-500/90 text-white p-1" data-testid={`mod-attachment-remove-${i}`} aria-label="Remove">
                  <Trash2 size={11} />
                </button>
                {a.kind === 'video' && (
                  <div className="absolute bottom-1 left-1 rounded bg-black/70 text-white text-[9px] px-1 py-0.5 font-bold">
                    <Film size={8} className="inline mr-0.5 -mt-0.5" /> VIDEO
                  </div>
                )}
                {a.offline && (
                  <div className="absolute bottom-1 right-1 rounded bg-amber-500/90 text-black text-[9px] px-1 py-0.5 font-extrabold uppercase tracking-wider">Offline</div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <div className="text-center text-[10px] mt-3" style={{ color: 'var(--theme-text-muted)' }}>You can skip this step.</div>
    </div>
  );
}
