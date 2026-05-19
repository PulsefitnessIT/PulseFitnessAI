import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus, Trash2, ExternalLink, Settings, Send, Globe, FileText } from 'lucide-react';
import FormBuilderDialog from './FormBuilderDialog';
import PageBuilderDialog from './PageBuilderDialog';
import FormSubmissionsDrawer from './FormSubmissionsDrawer';

/**
 * Iter 228 — Forms & Pages tab in the Marketing Suite.
 *
 * Two stacked sections:
 *  1. Forms — list of forms with submission counts; click → open builder
 *  2. Pages — list of landing pages with view counts; click → open builder
 *
 * Each row links to its public URL (`/forms/{slug}` and `/p/{slug}`).
 */
const FormsAndPagesTab = ({ API, headers }) => {
  const [forms, setForms] = useState([]);
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingForm, setEditingForm] = useState(null); // form obj or 'new'
  const [editingPage, setEditingPage] = useState(null);
  const [submissionsForm, setSubmissionsForm] = useState(null);

  const refresh = async () => {
    try {
      const [fRes, pRes] = await Promise.all([
        axios.get(`${API}/api/marketing/forms`, { headers }),
        axios.get(`${API}/api/marketing/pages`, { headers }),
      ]);
      setForms(fRes.data?.forms || []);
      setPages(pRes.data?.pages || []);
    } catch (e) {
      toast.error('Could not load forms & pages', { description: e.response?.data?.detail });
    }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — runs on the listed trigger deps; omitted refs are stable identities or read live state at call time.

  const baseUrl = useMemo(() => window.location.origin, []);

  const onDeleteForm = async (form) => {
    if (!window.confirm(`Archive form "${form.name}"? Submissions will be retained.`)) return;
    try {
      await axios.delete(`${API}/api/marketing/forms/${form.id}`, { headers });
      toast.success('Form archived');
      refresh();
    } catch (e) {
      toast.error('Archive failed', { description: e.response?.data?.detail });
    }
  };

  const onDeletePage = async (page) => {
    if (!window.confirm(`Archive page "${page.title}"?`)) return;
    try {
      await axios.delete(`${API}/api/marketing/pages/${page.id}`, { headers });
      toast.success('Page archived');
      refresh();
    } catch (e) {
      toast.error('Archive failed', { description: e.response?.data?.detail });
    }
  };

  const onTogglePublish = async (page) => {
    const next = page.status === 'published' ? 'draft' : 'published';
    try {
      await axios.put(`${API}/api/marketing/pages/${page.id}`, { status: next }, { headers });
      toast.success(next === 'published' ? 'Page published' : 'Page unpublished');
      refresh();
    } catch (e) {
      toast.error('Update failed', { description: e.response?.data?.detail });
    }
  };

  return (
    <div className="space-y-6" data-testid="forms-pages-tab">
      {/* Forms */}
      <Card className="p-5 bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800" data-testid="forms-section">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <FileText size={18} className="text-zinc-700 dark:text-zinc-300" />
            <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">Forms</h3>
            <Badge className="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700">{forms.length}</Badge>
          </div>
          <Button
            size="sm"
            onClick={() => setEditingForm('new')}
            className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
            data-testid="forms-new-btn"
          >
            <Plus size={14} className="mr-1" /> New form
          </Button>
        </div>
        <p className="text-zinc-500 dark:text-zinc-400 text-xs mb-3">
          Capture leads with hosted forms. Each form gets a public URL — link from emails, socials, or QR codes.
          Submissions auto-create CRM contacts (lifecycle = Lead).
        </p>
        <table className="w-full text-sm">
          <thead className="text-xs text-zinc-500 dark:text-zinc-400 uppercase tracking-wide border-b border-zinc-100 dark:border-zinc-800">
            <tr>
              <th className="text-left py-2 font-medium">Name</th>
              <th className="text-right py-2 font-medium">Submissions</th>
              <th className="text-left py-2 pl-3 font-medium">Public URL</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={4} className="text-center py-6 text-zinc-400">Loading…</td></tr>}
            {!loading && forms.length === 0 && (
              <tr><td colSpan={4} className="text-center py-6 text-zinc-400 text-sm">
                No forms yet — create your first to start capturing leads.
              </td></tr>
            )}
            {forms.map((f) => (
              <tr key={f.id} className="border-b border-zinc-100 dark:border-zinc-800" data-testid={`form-row-${f.id}`}>
                <td className="py-2">
                  <p className="text-zinc-900 dark:text-zinc-100 font-medium">{f.name}</p>
                  <p className="text-zinc-500 dark:text-zinc-400 text-xs">{f.fields?.length || 0} fields</p>
                </td>
                <td className="py-2 text-right">
                  <button
                    type="button"
                    onClick={() => setSubmissionsForm(f)}
                    className="text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 underline text-xs"
                    data-testid={`form-submissions-${f.id}`}
                  >
                    {f.submission_count || 0}
                  </button>
                </td>
                <td className="py-2 pl-3">
                  <a
                    href={`${baseUrl}/forms/${f.slug}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-600 dark:text-blue-400 hover:underline text-xs flex items-center gap-1"
                    data-testid={`form-public-url-${f.id}`}
                  >
                    /forms/{f.slug} <ExternalLink size={10} />
                  </a>
                </td>
                <td className="py-2 text-right">
                  <div className="inline-flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setEditingForm(f)} className="h-7 px-2 text-zinc-600 dark:text-zinc-400" data-testid={`form-edit-${f.id}`}>
                      <Settings size={12} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => onDeleteForm(f)} className="h-7 px-2 text-rose-600" data-testid={`form-delete-${f.id}`}>
                      <Trash2 size={12} />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Landing Pages */}
      <Card className="p-5 bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800" data-testid="pages-section">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Globe size={18} className="text-zinc-700 dark:text-zinc-300" />
            <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">Landing Pages</h3>
            <Badge className="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700">{pages.length}</Badge>
          </div>
          <Button
            size="sm"
            onClick={() => setEditingPage('new')}
            className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
            data-testid="pages-new-btn"
          >
            <Plus size={14} className="mr-1" /> New page
          </Button>
        </div>
        <p className="text-zinc-500 dark:text-zinc-400 text-xs mb-3">
          Build hero + body + embedded form pages. Each page gets a public URL at <code>/p/{'{slug}'}</code>.
          Pageviews and UTM parameters are tracked automatically.
        </p>
        <table className="w-full text-sm">
          <thead className="text-xs text-zinc-500 dark:text-zinc-400 uppercase tracking-wide border-b border-zinc-100 dark:border-zinc-800">
            <tr>
              <th className="text-left py-2 font-medium">Title</th>
              <th className="text-left py-2 font-medium">Status</th>
              <th className="text-right py-2 font-medium">Views</th>
              <th className="text-left py-2 pl-3 font-medium">Public URL</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="text-center py-6 text-zinc-400">Loading…</td></tr>}
            {!loading && pages.length === 0 && (
              <tr><td colSpan={5} className="text-center py-6 text-zinc-400 text-sm">
                No pages yet — create your first landing page.
              </td></tr>
            )}
            {pages.map((p) => (
              <tr key={p.id} className="border-b border-zinc-100 dark:border-zinc-800" data-testid={`page-row-${p.id}`}>
                <td className="py-2 font-medium text-zinc-900 dark:text-zinc-100">{p.title}</td>
                <td className="py-2">
                  <Badge className={p.status === 'published'
                    ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                    : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700'}>
                    {p.status}
                  </Badge>
                </td>
                <td className="py-2 text-right text-zinc-700 dark:text-zinc-300">{p.view_count || 0}</td>
                <td className="py-2 pl-3">
                  {p.status === 'published'
                    ? <a href={`${baseUrl}/p/${p.slug}`} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline text-xs flex items-center gap-1">
                        /p/{p.slug} <ExternalLink size={10} />
                      </a>
                    : <span className="text-zinc-400 text-xs">/p/{p.slug} (draft)</span>}
                </td>
                <td className="py-2 text-right">
                  <div className="inline-flex gap-1">
                    <Button
                      size="sm" variant="ghost"
                      onClick={() => onTogglePublish(p)}
                      className="h-7 px-2 text-zinc-600 dark:text-zinc-400"
                      data-testid={`page-publish-${p.id}`}
                      title={p.status === 'published' ? 'Unpublish' : 'Publish'}
                    >
                      <Send size={12} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditingPage(p)} className="h-7 px-2 text-zinc-600 dark:text-zinc-400" data-testid={`page-edit-${p.id}`}>
                      <Settings size={12} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => onDeletePage(p)} className="h-7 px-2 text-rose-600" data-testid={`page-delete-${p.id}`}>
                      <Trash2 size={12} />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {editingForm && (
        <FormBuilderDialog
          API={API}
          headers={headers}
          form={editingForm === 'new' ? null : editingForm}
          onClose={() => setEditingForm(null)}
          onSaved={() => { setEditingForm(null); refresh(); }}
        />
      )}
      {editingPage && (
        <PageBuilderDialog
          API={API}
          headers={headers}
          page={editingPage === 'new' ? null : editingPage}
          forms={forms}
          onClose={() => setEditingPage(null)}
          onSaved={() => { setEditingPage(null); refresh(); }}
        />
      )}
      {submissionsForm && (
        <FormSubmissionsDrawer
          API={API}
          headers={headers}
          form={submissionsForm}
          onClose={() => setSubmissionsForm(null)}
        />
      )}
    </div>
  );
};

export default FormsAndPagesTab;
