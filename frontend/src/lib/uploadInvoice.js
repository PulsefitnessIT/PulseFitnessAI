import axios from 'axios';

// Files at/under this size go straight through; larger ones are chunked
// to stay under the platform ingress 2MB body limit (which otherwise
// surfaces as a browser "Network Error" on large invoices).
const CHUNK_SIZE = 1.5 * 1024 * 1024; // 1.5MB per request

/**
 * Upload a supplier invoice for AI extraction. Transparently chunks large
 * files (>1.5MB) so they bypass the 2MB proxy body limit, then finalises.
 * Returns the same response body as POST /equipment-import/parse-invoice.
 *
 * @param {File} file
 * @param {{ API: string, headers?: object, onProgress?: (pct:number)=>void }} opts
 */
export async function uploadInvoiceSmart(file, { API, headers = {}, onProgress, onStatus } = {}) {
  // Small file → single request (unchanged behaviour).
  if (file.size <= CHUNK_SIZE) {
    const fd = new FormData();
    fd.append('file', file);
    const res = await axios.post(`${API}/equipment-import/parse-invoice`, fd, {
      headers: { ...headers },
      timeout: 120000,
      onUploadProgress: (e) => { if (e.total && onProgress) onProgress((e.loaded / e.total) * 100); },
    });
    return res.data;
  }

  // Large file → chunked upload.
  const uploadId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  for (let i = 0; i < totalChunks; i++) {
    const blob = file.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
    const fd = new FormData();
    fd.append('upload_id', uploadId);
    fd.append('chunk_index', String(i));
    fd.append('total_chunks', String(totalChunks));
    fd.append('file', blob, `${file.name}.part${i}`);
    await axios.post(`${API}/equipment-import/parse-invoice/chunk`, fd, {
      headers: { ...headers }, timeout: 120000,
    });
    // Upload accounts for ~80% of the bar; extraction fills the rest.
    if (onProgress) onProgress(Math.min(80, ((i + 1) / totalChunks) * 80));
  }

  if (onProgress) onProgress(85);
  const ff = new FormData();
  ff.append('upload_id', uploadId);
  ff.append('filename', file.name);
  ff.append('content_type', file.type || 'application/pdf');
  const fin = await axios.post(`${API}/equipment-import/parse-invoice/finalize`, ff, {
    headers: { ...headers }, timeout: 60000,
  });
  // Large invoices extract in a decoupled background job — poll for it.
  if (fin.data?.job_id) {
    const jobId = fin.data.job_id;
    const started = Date.now();
    const MAX_MS = 5 * 60 * 1000;
    // Typical extraction ~90s; ramp the bar 85→97 over that window so it
    // never looks stuck, then snap to 100 on completion.
    while (Date.now() - started < MAX_MS) {
      await new Promise((r) => setTimeout(r, 2500));
      const s = await axios.get(`${API}/equipment-import/parse-invoice/status/${jobId}`, { headers: { ...headers } });
      const job = s.data || {};
      if (onStatus) onStatus(job);
      if (job.status === 'done') {
        if (onProgress) onProgress(100);
        return job.result;
      }
      if (job.status === 'error') {
        throw new Error(job.error || 'Invoice extraction failed');
      }
      if (onProgress) {
        const elapsed = Date.now() - started;
        const ramp = 85 + Math.min(12, (elapsed / 90000) * 12);
        onProgress(Math.round(ramp));
      }
    }
    throw new Error('Invoice is taking unusually long to process. Please try again or split the PDF.');
  }
  if (onProgress) onProgress(100);
  return fin.data;
}

export default uploadInvoiceSmart;
