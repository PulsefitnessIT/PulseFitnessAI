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
  onProgress, onSession, resumeUploadId,
  chunkSize = CHUNK_SIZE_BYTES, threshold = CHUNK_THRESHOLD_BYTES,
}) {
  if (!file || !(file instanceof Blob)) {
    throw new Error('chunkedUpload: a File/Blob is required');
  }

  // Small enough → ride the legacy path. Resume only ever applies
  // to chunked uploads, so if a tiny file is presented for resume
  // the caller almost certainly didn't mean to — fall through to
  // single-shot anyway and let the server re-accept it cleanly.
  if (file.size <= threshold && !resumeUploadId) {
    return singleShotUpload({ baseURL, file, category, authHeaders, onProgress });
  }

  const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize));
  let uploadId = resumeUploadId || null;
  const alreadyHave = new Set();

  if (resumeUploadId) {
    // Iter 220ea·4 — Resume path. Ask the server which chunks
    // landed in the previous attempt and skip those entirely. The
    // session TTL on the backend is 60 min so anything older has
    // already been collected and the resume will 404 — surface that
    // clearly so the caller can drop it from the local stash.
    try {
      const statusRes = await axios.get(
        `${baseURL}/files/upload/chunks/${resumeUploadId}/status`,
        { headers: authHeaders },
      );
      const data = statusRes.data || {};
      if (data.status !== 'in_progress') {
        throw new Error(`chunkedUpload: cannot resume — session is ${data.status}`);
      }
      if (Number(data.total_chunks) !== totalChunks) {
        throw new Error(
          `chunkedUpload: cannot resume — chunk count mismatch ` +
          `(server expected ${data.total_chunks}, file produces ${totalChunks})`,
        );
      }
      const missing = new Set((data.missing || []).map(Number));
      for (let i = 0; i < totalChunks; i += 1) {
        if (!missing.has(i)) alreadyHave.add(i);
      }
    } catch (err) {
      // Bubble a clearer error so the resume sheet can offer the
      // engineer a "discard" option when the session has expired.
      if (err?.response?.status === 404) {
        const e = new Error('chunkedUpload: session expired (404 from /status)');
        e.code = 'session_expired';
        throw e;
      }
      throw err;
    }
  } else {
    // 1. Reserve a fresh session.
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
    uploadId = initRes.data?.upload_id;
    if (!uploadId) throw new Error('chunkedUpload: init returned no upload_id');
    // Surface the session straight away so the caller can stash it
    // BEFORE we start pushing chunks. That way even if the very
    // first PUT fails, the engineer can come back and pick up
    // where they left off.
    if (typeof onSession === 'function') {
      try {
        await onSession({ uploadId, totalChunks });
      } catch { /* don't let stashing errors block the upload */ }
    }
  }

  // 2. Drive chunks with a small parallel pool — 2 in-flight is a
  // good 4G compromise (faster than serial, won't oversaturate).
  const completed = new Array(totalChunks).fill(false);
  alreadyHave.forEach(idx => { completed[idx] = true; });
  let cursor = 0;

  const reportProgress = () => {
    if (!onProgress) return;
    const done = completed.filter(Boolean).length;
    onProgress(Math.round((done / totalChunks) * 100));
  };
  reportProgress();  // reflect the head-start when resuming.

  async function worker() {
    while (true) {
      let idx = -1;
      while (cursor < totalChunks) {
        const candidate = cursor;
        cursor += 1;
        if (!alreadyHave.has(candidate)) { idx = candidate; break; }
      }
      if (idx < 0) break;
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
    // Iter 220ea·4 — Do NOT auto-abort on resumable uploads. The
    // server-side session is still live for the next attempt. For
    // a non-resume run, abort opportunistically so the TTL doesn't
    // have to wait an hour.
    if (!resumeUploadId) {
      try {
        await axios.delete(`${baseURL}/files/upload/chunks/${uploadId}`, { headers: authHeaders });
      } catch { /* swallow — TTL will collect it */ }
    }
    err.uploadId = uploadId;
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
