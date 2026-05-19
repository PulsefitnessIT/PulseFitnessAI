import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { X, ChevronLeft, ChevronRight } from 'lucide-react';

const FormSubmissionsDrawer = ({ API, headers, form, onClose }) => {
  const [submissions, setSubmissions] = useState([]);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    axios.get(`${API}/api/marketing/forms/${form.id}/submissions`, {
      headers, params: { page, page_size: pageSize },
    }).then((r) => {
      if (cancelled) return;
      setSubmissions(r.data?.submissions || []);
      setTotal(r.data?.total || 0);
    }).catch((e) => {
      if (!cancelled) toast.error('Could not load submissions', { description: e.response?.data?.detail });
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [API, form.id, page, pageSize]); // eslint-disable-line react-hooks/exhaustive-deps

  const fieldsById = {};
  for (const f of form.fields || []) fieldsById[f.id] = f;

  const pages = total === 0 ? 0 : Math.ceil(total / pageSize);

  return (
    <div
      className="fixed inset-0 bg-black/30 z-40 flex justify-end"
      onClick={onClose}
      data-testid="form-submissions-drawer-backdrop"
    >
      <div
        className="bg-white dark:bg-zinc-900 w-full max-w-2xl h-full overflow-y-auto p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="form-submissions-drawer"
      >
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-zinc-500 dark:text-zinc-400 text-xs uppercase tracking-wide">Submissions</p>
            <h3 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{form.name}</h3>
            <Badge className="bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700 mt-1">{total} total</Badge>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose} className="h-7 px-2 text-zinc-500 dark:text-zinc-400" data-testid="form-submissions-close">
            <X size={14} />
          </Button>
        </div>

        {loading && <p className="text-zinc-400 text-sm py-6 text-center">Loading…</p>}
        {!loading && submissions.length === 0 && (
          <p className="text-zinc-400 text-sm py-6 text-center">No submissions yet.</p>
        )}

        <div className="space-y-2">
          {submissions.map((s) => (
            <div key={s.id} className="border border-zinc-200 dark:border-zinc-700 rounded-md p-3 bg-zinc-50 dark:bg-zinc-800/50" data-testid={`form-submission-${s.id}`}>
              <div className="flex items-center justify-between mb-2">
                <p className="text-zinc-500 dark:text-zinc-400 text-xs">{new Date(s.submitted_at).toLocaleString('en-GB')}</p>
                {s.crm_contact_id && (
                  <Badge className="bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 text-[10px]">CRM contact created</Badge>
                )}
              </div>
              <dl className="space-y-1">
                {Object.entries(s.values || {}).map(([fid, val]) => {
                  const f = fieldsById[fid];
                  return (
                    <div key={fid} className="flex gap-2 text-sm">
                      <dt className="text-zinc-500 dark:text-zinc-400 min-w-[120px]">{f?.label || fid}:</dt>
                      <dd className="text-zinc-900 dark:text-zinc-100 break-all">{String(val)}</dd>
                    </div>
                  );
                })}
              </dl>
            </div>
          ))}
        </div>

        {pages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-zinc-500 text-xs">Page {page} of {pages}</p>
            <div className="flex gap-1">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="h-7 px-2">
                <ChevronLeft size={12} />
              </Button>
              <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage((p) => p + 1)} className="h-7 px-2">
                <ChevronRight size={12} />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default FormSubmissionsDrawer;
