import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

const PageBuilderDialog = ({ API, headers, page, forms, onClose, onSaved }) => {
  const [title, setTitle] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [body, setBody] = useState('');
  const [heroImageUrl, setHeroImageUrl] = useState('');
  const [ctaLabel, setCtaLabel] = useState('');
  const [ctaUrl, setCtaUrl] = useState('');
  const [formId, setFormId] = useState('');
  const [seoTitle, setSeoTitle] = useState('');
  const [seoDescription, setSeoDescription] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (page) {
      setTitle(page.title || '');
      setSubtitle(page.subtitle || '');
      setBody(page.body_markdown || '');
      setHeroImageUrl(page.hero_image_url || '');
      setCtaLabel(page.cta_label || '');
      setCtaUrl(page.cta_url || '');
      setFormId(page.form_id || '');
      setSeoTitle(page.seo_title || '');
      setSeoDescription(page.seo_description || '');
    }
  }, [page]);

  const onSave = async () => {
    if (!title.trim()) { toast.error('Page needs a title'); return; }
    setSaving(true);
    try {
      const payload = {
        title: title.trim(),
        subtitle: subtitle.trim(),
        body_markdown: body,
        hero_image_url: heroImageUrl.trim() || null,
        cta_label: ctaLabel.trim() || null,
        cta_url: ctaUrl.trim() || null,
        form_id: formId || null,
        seo_title: seoTitle.trim() || null,
        seo_description: seoDescription.trim() || null,
      };
      if (page) {
        await axios.put(`${API}/api/marketing/pages/${page.id}`, payload, { headers });
      } else {
        await axios.post(`${API}/api/marketing/pages`, payload, { headers });
      }
      toast.success(page ? 'Page updated' : 'Page created (saved as draft)');
      onSaved && onSaved();
    } catch (e) {
      toast.error('Save failed', { description: e.response?.data?.detail });
    }
    setSaving(false);
  };

  return (
    <Dialog open={true} onOpenChange={(v) => !v && onClose && onClose()}>
      <DialogContent className="bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="page-builder-dialog">
        <DialogHeader>
          <DialogTitle>{page ? 'Edit landing page' : 'New landing page'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Title *</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Become a Site Manager" className="mt-1" data-testid="page-builder-title" />
          </div>
          <div>
            <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Subtitle</Label>
            <Input value={subtitle} onChange={(e) => setSubtitle(e.target.value)} className="mt-1" data-testid="page-builder-subtitle" />
          </div>
          <div>
            <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Hero image URL</Label>
            <Input value={heroImageUrl} onChange={(e) => setHeroImageUrl(e.target.value)} placeholder="https://…/hero.jpg" className="mt-1" />
          </div>
          <div>
            <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Body (Markdown supported)</Label>
            <Textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write your story…" className="mt-1 font-mono text-sm" data-testid="page-builder-body" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">CTA label</Label>
              <Input value={ctaLabel} onChange={(e) => setCtaLabel(e.target.value)} placeholder="Book a demo" className="mt-1" />
            </div>
            <div>
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">CTA link</Label>
              <Input value={ctaUrl} onChange={(e) => setCtaUrl(e.target.value)} placeholder="https://…" className="mt-1" />
            </div>
          </div>
          <div>
            <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Embedded form</Label>
            <select
              value={formId}
              onChange={(e) => setFormId(e.target.value)}
              className="mt-1 w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 rounded-md px-2 py-1.5 text-sm"
              data-testid="page-builder-form-select"
            >
              <option value="">— None —</option>
              {(forms || []).map((f) => (
                <option key={f.id} value={f.id}>{f.name}</option>
              ))}
            </select>
          </div>
          <div className="border-t border-zinc-100 dark:border-zinc-800 pt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">SEO title</Label>
              <Input value={seoTitle} onChange={(e) => setSeoTitle(e.target.value)} className="mt-1 text-sm" />
            </div>
            <div>
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">SEO description</Label>
              <Input value={seoDescription} onChange={(e) => setSeoDescription(e.target.value)} className="mt-1 text-sm" />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={onSave} disabled={saving} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="page-builder-save">
              {saving ? 'Saving…' : (page ? 'Save changes' : 'Create page')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default PageBuilderDialog;
