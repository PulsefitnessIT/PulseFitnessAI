import { useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Bookmark, BookmarkCheck } from 'lucide-react';

import { notify } from '@/components/notifications';
/**
 * Inline "Save as template" affordance for the fault form.
 * Expands into a name input + scope toggle (Site / Personal) on click.
 */
const SaveAsTemplateButton = ({ API, issueForm, privileged = false, onSaved }) => {
  const [expanded, setExpanded] = useState(false);
  const [name, setName] = useState('');
  const [scope, setScope] = useState('personal');
  const [saving, setSaving] = useState(false);

  const canSave = Boolean(issueForm?.machine_type && issueForm?.issue_description);

  const handleSave = async () => {
    if (!name.trim()) {
      notify.error('Template name is required');
      return;
    }
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      const payload = {
        name: name.trim(),
        scope,
        machine_type: issueForm.machine_type,
        issue_description: issueForm.issue_description,
        severity: issueForm.severity || 'operational_minor',
        supplier: issueForm.supplier || '',
        steps_taken: issueForm.steps_taken || '',
        fault_code: issueForm.fault_code || null,
      };
      await axios.post(`${API}/fault-templates`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      });
      notify.success('Template saved', { duration: 3000 });
      setName('');
      setExpanded(false);
      onSaved?.();
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Failed to save template';
      notify.error(msg);
    } finally {
      setSaving(false);
    }
  };

  if (!canSave) return null;

  return (
    <div className="mt-2" data-testid="save-template-wrapper">
      {!expanded ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setExpanded(true)}
          className="text-xs h-7 gap-1"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
          data-testid="save-template-btn"
        >
          <Bookmark size={12} /> Save as template
        </Button>
      ) : (
        <div
          className="rounded-md border p-2 space-y-2"
          style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}
          data-testid="save-template-inline"
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Template name (e.g. 'Treadmill belt slip')"
            className="h-8 text-xs"
            data-testid="save-template-name"
          />
          {privileged && (
            <div className="flex gap-1.5">
              {[
                { id: 'personal', label: 'Personal' },
                { id: 'org',      label: 'Site-wide' },
              ].map(opt => {
                const active = scope === opt.id;
                return (
                  <Button
                    key={opt.id}
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setScope(opt.id)}
                    className="h-7 text-xs flex-1"
                    style={active
                      ? { background: 'var(--color-brand-blue)', color: 'var(--color-white)', borderColor: 'transparent' }
                      : { color: 'var(--theme-text-muted)', borderColor: 'var(--theme-border)' }}
                    data-testid={`save-scope-${opt.id}`}
                  >
                    {opt.label}
                  </Button>
                );
              })}
            </div>
          )}
          <div className="flex gap-1.5">
            <Button
              type="button"
              size="sm"
              onClick={handleSave}
              disabled={saving}
              className="h-7 text-xs flex-1 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
              data-testid="save-template-confirm"
            >
              <BookmarkCheck size={12} className="mr-1" /> {saving ? 'Saving…' : 'Save'}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => { setExpanded(false); setName(''); }}
              className="h-7 text-xs"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
              data-testid="save-template-cancel"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SaveAsTemplateButton;
