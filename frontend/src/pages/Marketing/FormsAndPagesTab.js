import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus, Trash2, ExternalLink, Settings, Send, Globe, FileText, BarChart3, Star } from 'lucide-react';
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
  const { t } = useTranslation();
  const [forms, setForms] = useState([]);
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingForm, setEditingForm] = useState(null); // form obj or 'new'
  const [editingPage, setEditingPage] = useState(null);
  const [submissionsForm, setSubmissionsForm] = useState(null);
  const [resultsForm, setResultsForm] = useState(null);

  const refresh = async () => {
    try {
      const [fRes, pRes] = await Promise.all([
        axios.get(`${API}/api/marketing/forms`, { headers }),
        axios.get(`${API}/api/marketing/pages`, { headers }),
      ]);
      setForms(fRes.data?.forms || []);
      setPages(pRes.data?.pages || []);
    } catch (e) {
      toast.error(t('mkt.fp_load_err', 'Could not load forms & pages'), { description: e.response?.data?.detail });
    }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — runs on the listed trigger deps; omitted refs are stable identities or read live state at call time.

  const baseUrl = useMemo(() => window.location.origin, []);

  const onDeleteForm = async (form) => {
    if (!window.confirm(t('mkt.fp_archive_form_confirm', 'Archive form "{{name}}"? Submissions will be retained.', { name: form.name }))) return;
    try {
      await axios.delete(`${API}/api/marketing/forms/${form.id}`, { headers });
      toast.success(t('mkt.fp_form_archived', 'Form archived'));
      refresh();
    } catch (e) {
      toast.error(t('mkt.fp_archive_failed', 'Archive failed'), { description: e.response?.data?.detail });
    }
  };

  const onDeletePage = async (page) => {
    if (!window.confirm(t('mkt.fp_archive_page_confirm', 'Archive page "{{title}}"?', { title: page.title }))) return;
    try {
      await axios.delete(`${API}/api/marketing/pages/${page.id}`, { headers });
      toast.success(t('mkt.fp_page_archived', 'Page archived'));
      refresh();
    } catch (e) {
      toast.error(t('mkt.fp_archive_failed', 'Archive failed'), { description: e.response?.data?.detail });
    }
  };

  const onTogglePublish = async (page) => {
    const next = page.status === 'published' ? 'draft' : 'published';
    try {
      await axios.put(`${API}/api/marketing/pages/${page.id}`, { status: next }, { headers });
      toast.success(next === 'published' ? t('mkt.fp_page_published', 'Page published') : t('mkt.fp_page_unpublished', 'Page unpublished'));
      refresh();
    } catch (e) {
      toast.error(t('mkt.fp_update_failed', 'Update failed'), { description: e.response?.data?.detail });
    }
  };

  return (
    <div className="space-y-6" data-testid="forms-pages-tab">
      {/* Forms */}
      <Card className="p-5 bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800" data-testid="forms-section">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <FileText size={18} className="text-zinc-700 dark:text-zinc-300" />
            <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t('mkt.fp_forms', 'Forms')}</h3>
            <Badge className="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700">{forms.length}</Badge>
          </div>
          <Button
            size="sm"
            onClick={() => setEditingForm('new')}
            className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
            data-testid="forms-new-btn"
          >
            <Plus size={14} className="mr-1" /> {t('mkt.fp_new_form', 'New form')}
          </Button>
        </div>
        <p className="text-zinc-500 dark:text-zinc-400 text-xs mb-3">
          {t('mkt.fp_forms_desc', 'Capture leads with hosted forms. Each form gets a public URL — link from emails, socials, or QR codes. Submissions auto-create CRM contacts (lifecycle = Lead).')}
        </p>
        <table className="w-full text-sm">
          <thead className="text-xs text-zinc-500 dark:text-zinc-400 uppercase tracking-wide border-b border-zinc-100 dark:border-zinc-800">
            <tr>
              <th className="text-left py-2 font-medium">{t('mkt.fp_th_name', 'Name')}</th>
              <th className="text-right py-2 font-medium">{t('mkt.fsd_kicker', 'Submissions')}</th>
              <th className="text-left py-2 pl-3 font-medium">{t('mkt.fp_th_public_url', 'Public URL')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={4} className="text-center py-6 text-zinc-400">{t('mkt.fp_loading', 'Loading…')}</td></tr>}
            {!loading && forms.length === 0 && (
              <tr><td colSpan={4} className="text-center py-6 text-zinc-400 text-sm">
                {t('mkt.fp_no_forms', 'No forms yet — create your first to start capturing leads.')}
              </td></tr>
            )}
            {forms.map((f) => (
              <tr key={f.id} className="border-b border-zinc-100 dark:border-zinc-800" data-testid={`form-row-${f.id}`}>
                <td className="py-2">
                  <p className="text-zinc-900 dark:text-zinc-100 font-medium flex items-center gap-2">
                    {f.name}
                    {f.kind === 'survey' && <Badge className="bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-800 text-[10px]">{t('mkt.fp_survey', 'Survey')}</Badge>}
                  </p>
                  <p className="text-zinc-500 dark:text-zinc-400 text-xs">{t('mkt.fp_fields_count', '{{n}} fields', { n: f.fields?.length || 0 })}</p>
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
                    {f.kind === 'survey' && (
                      <Button size="sm" variant="ghost" onClick={() => setResultsForm(f)} className="h-7 px-2 text-violet-600" data-testid={`form-results-${f.id}`} title={t('mkt.fp_view_results', 'View survey results')}>
                        <BarChart3 size={12} />
                      </Button>
                    )}
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
            <Plus size={14} className="mr-1" /> {t('mkt.fp_new_page', 'New page')}
          </Button>
        </div>
        <p className="text-zinc-500 dark:text-zinc-400 text-xs mb-3">
          {t('mkt.fp_pages_desc', 'Build hero + body + embedded form pages. Each page gets a public URL at /p/{slug}. Pageviews and UTM parameters are tracked automatically.')}
        </p>
        <table className="w-full text-sm">
          <thead className="text-xs text-zinc-500 dark:text-zinc-400 uppercase tracking-wide border-b border-zinc-100 dark:border-zinc-800">
            <tr>
              <th className="text-left py-2 font-medium">{t('mkt.fp_th_title', 'Title')}</th>
              <th className="text-left py-2 font-medium">{t('mkt.fp_th_status', 'Status')}</th>
              <th className="text-right py-2 font-medium">{t('mkt.fp_th_views', 'Views')}</th>
              <th className="text-left py-2 pl-3 font-medium">{t('mkt.fp_th_public_url', 'Public URL')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="text-center py-6 text-zinc-400">{t('mkt.fp_loading', 'Loading…')}</td></tr>}
            {!loading && pages.length === 0 && (
              <tr><td colSpan={5} className="text-center py-6 text-zinc-400 text-sm">
                {t('mkt.fp_no_pages', 'No pages yet — create your first landing page.')}
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
                    : <span className="text-zinc-400 text-xs">/p/{p.slug} {t('mkt.fp_draft_suffix', '(draft)')}</span>}
                </td>
                <td className="py-2 text-right">
                  <div className="inline-flex gap-1">
                    <Button
                      size="sm" variant="ghost"
                      onClick={() => onTogglePublish(p)}
                      className="h-7 px-2 text-zinc-600 dark:text-zinc-400"
                      data-testid={`page-publish-${p.id}`}
                      title={p.status === 'published' ? t('mkt.fp_unpublish', 'Unpublish') : t('mkt.fp_publish', 'Publish')}
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
      {resultsForm && (
        <SurveyResultsDialog API={API} headers={headers} form={resultsForm} onClose={() => setResultsForm(null)} />
      )}
    </div>
  );
};

function SurveyResultsDialog({ API, headers, form, onClose }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${API}/api/marketing/forms/${form.id}/results`, { headers })
      .then((r) => setData(r.data))
      .catch(() => toast.error(t('mkt.fp_results_err', 'Could not load results')));
  }, [API, headers, form.id, t]);

  return (
    <div className="fixed inset-0 z-[200] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white dark:bg-zinc-900 rounded-2xl p-6 w-full max-w-2xl max-h-[88vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="survey-results-dialog">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2"><BarChart3 size={18} className="text-violet-600" />{t('mkt.fp_results_title', '{{name}} — results', { name: form.name })}</h3>
          <Button variant="ghost" size="sm" onClick={onClose}>{t('mkt.fp_close', 'Close')}</Button>
        </div>
        {!data ? (
          <p className="text-sm text-zinc-400 py-8 text-center">{t('mkt.fp_loading', 'Loading…')}</p>
        ) : (
          <>
            <p className="text-sm text-zinc-500 mb-4" data-testid="survey-total">{data.total_submissions === 1 ? t('mkt.fp_responses_one', '1 response') : t('mkt.fp_responses_many', '{{n}} responses', { n: data.total_submissions })}</p>
            <div className="space-y-5">
              {data.results.map((r) => (
                <div key={r.id} className="border border-zinc-100 dark:border-zinc-800 rounded-xl p-4" data-testid={`survey-result-${r.id}`}>
                  <p className="font-semibold text-sm text-zinc-900 dark:text-zinc-100 mb-2">{r.label} <span className="text-zinc-400 font-normal">· {t('mkt.fp_answered', '{{n}} answered', { n: r.responses })}</span></p>
                  {r.breakdown && (
                    <div className="space-y-1.5">
                      {r.breakdown.map((b) => {
                        const pct = r.responses ? Math.round((b.count / r.responses) * 100) : 0;
                        return (
                          <div key={b.value}>
                            <div className="flex justify-between text-xs text-zinc-600 dark:text-zinc-300 mb-0.5"><span>{b.value}</span><span>{b.count} ({pct}%)</span></div>
                            <div className="h-2 rounded-full bg-zinc-100 dark:bg-zinc-800"><div className="h-2 rounded-full bg-violet-500" style={{ width: `${pct}%` }} /></div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {r.field_type === 'rating' && (
                    <div className="flex items-center gap-2 text-sm">
                      <span className="flex items-center gap-1 font-bold text-amber-500"><Star size={15} fill="currentColor" />{r.average}</span>
                      <span className="text-zinc-400 text-xs">{t('mkt.fp_average', 'average')}</span>
                    </div>
                  )}
                  {r.samples && (
                    <ul className="text-xs text-zinc-600 dark:text-zinc-300 space-y-1 list-disc pl-4">
                      {r.samples.length === 0 && <li className="list-none text-zinc-400">{t('mkt.fp_no_answers', 'No answers yet.')}</li>}
                      {r.samples.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default FormsAndPagesTab;
