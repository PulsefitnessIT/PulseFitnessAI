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
export async function uploadInvoiceSmart(file, { API, headers = {}, onProgress } = {}) {
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
    // Poll up to ~5 min; extraction of big multi-page PDFs can be slow.
    while (Date.now() - started < 5 * 60 * 1000) {
      await new Promise((r) => setTimeout(r, 2500));
      const s = await axios.get(`${API}/equipment-import/parse-invoice/status/${jobId}`, { headers: { ...headers } });
      if (s.data?.status === 'done') {
        if (onProgress) onProgress(100);
        return s.data.result;
      }
      if (s.data?.status === 'error') {
        throw new Error(s.data.error || 'Invoice extraction failed');
      }
    }
    throw new Error('Invoice is taking unusually long to process. Please try again or split the PDF.');
  }
  if (onProgress) onProgress(100);
  return fin.data;
}

export default uploadInvoiceSmart;
