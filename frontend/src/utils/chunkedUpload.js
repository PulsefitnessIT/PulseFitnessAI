/**
 * Iter 220e9 — Chunked upload helper for engineer media on flaky 4G.
 *
 * Strategy:
 *   - Small files (< THRESHOLD bytes) ride the legacy single-shot
 *     `/files/upload` endpoint to keep the happy path simple.
 *   - Large files are split into ~1 MB chunks. Each chunk has its
 *     own retry budget (exponential backoff). A failed chunk does
 *     NOT throw away progress — the resumed `complete` will succeed
 *     as long as every index has been received at least once.
 *   - Aggregate progress callback so the existing UI progress bar
 *     just plugs in. The shape returned is identical to the
 *     single-shot response so callers don't branch.
 *
 * Usage:
 *   const fileDoc = await chunkedUpload({
 *     baseURL: API,
 *     file,
 *     category: 'service-media',
 *     authHeaders: auth().headers,
 *     onProgress: (pct) => setUploadPct(pct),
 *   });
 *
 * Why not `tus-js-client`? We don't need server-side resumption
 * after a tab close, just retry-per-chunk over a single session.
 * Keeping the helper in-house avoids 30 KB of npm bloat in the PWA
 * and matches the existing zero-extra-dep posture (cf. the vanilla
 * IndexedDB outbox).
 */
import axios from 'axios';

export const CHUNK_THRESHOLD_BYTES = 4 * 1024 * 1024;  // 4 MB
export const CHUNK_SIZE_BYTES      = 1 * 1024 * 1024;  // 1 MB
export const CHUNK_MAX_RETRIES     = 4;
export const CHUNK_PARALLEL        = 2;

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function singleShotUpload({ baseURL, file, category, authHeaders, onProgress }) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await axios.post(
    `${baseURL}/files/upload?category=${encodeURIComponent(category)}`,
    fd,
    {
      headers: { ...authHeaders, 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (e.total && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    },
  );
  return res.data;
}

async function uploadOneChunk({ baseURL, uploadId, index, blob, authHeaders }) {
  let attempt = 0;
  let lastErr;
  while (attempt <= CHUNK_MAX_RETRIES) {
    try {
      const res = await axios.put(
        `${baseURL}/files/upload/chunks/${uploadId}/${index}`,
        blob,
        {
          headers: { ...authHeaders, 'Content-Type': 'application/octet-stream' },
          // 60s per chunk gives 4G plenty of headroom for 1 MB.
          timeout: 60_000,
        },
      );
      return res.data;
    } catch (err) {
      lastErr = err;
      attempt += 1;
      if (attempt > CHUNK_MAX_RETRIES) break;
      // Exponential backoff with a small jitter — 300 / 600 / 1200 / 2400 ms.
      const delay = 300 * 2 ** (attempt - 1) + Math.floor(Math.random() * 150);
      await sleep(delay);
    }
  }
  throw lastErr || new Error(`Chunk ${index} failed after ${CHUNK_MAX_RETRIES} retries`);
}

export async function chunkedUpload({
  baseURL, file, category = 'general', authHeaders = {},
  onProgress, chunkSize = CHUNK_SIZE_BYTES, threshold = CHUNK_THRESHOLD_BYTES,
}) {
  if (!file || !(file instanceof Blob)) {
    throw new Error('chunkedUpload: a File/Blob is required');
  }

  // Small enough → ride the legacy path.
  if (file.size <= threshold) {
    return singleShotUpload({ baseURL, file, category, authHeaders, onProgress });
  }

  const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize));

  // 1. Reserve a session.
  const initRes = await axios.post(
    `${baseURL}/files/upload/chunks/init`,
    {
      filename: file.name || 'upload.bin',
      size: file.size,
      content_type: file.type || 'application/octet-stream',
      category,
      total_chunks: totalChunks,
    },
    { headers: authHeaders },
  );
  const uploadId = initRes.data?.upload_id;
  if (!uploadId) throw new Error('chunkedUpload: init returned no upload_id');

  // 2. Drive chunks with a small parallel pool — 2 in-flight is a
  // good 4G compromise (faster than serial, won't oversaturate).
  const completed = new Array(totalChunks).fill(false);
  let cursor = 0;

  const reportProgress = () => {
    if (!onProgress) return;
    const done = completed.filter(Boolean).length;
    onProgress(Math.round((done / totalChunks) * 100));
  };

  async function worker() {
    while (true) {
      const idx = cursor;
      if (idx >= totalChunks) break;
      cursor += 1;
      const start = idx * chunkSize;
      const blob = file.slice(start, Math.min(start + chunkSize, file.size));
      await uploadOneChunk({ baseURL, uploadId, index: idx, blob, authHeaders });
      completed[idx] = true;
      reportProgress();
    }
  }

  try {
    await Promise.all(
      Array.from({ length: Math.min(CHUNK_PARALLEL, totalChunks) }, () => worker()),
    );
  } catch (err) {
    // Best-effort abort so server-side TTL doesn't have to wait an hour.
    try {
      await axios.delete(`${baseURL}/files/upload/chunks/${uploadId}`, { headers: authHeaders });
    } catch { /* swallow — TTL will collect it */ }
    throw err;
  }

  // 3. Tell the server to assemble + persist the file.
  const finishRes = await axios.post(
    `${baseURL}/files/upload/chunks/${uploadId}/complete`,
    {},
    { headers: authHeaders },
  );
  if (onProgress) onProgress(100);
  return finishRes.data;
}

export default chunkedUpload;
