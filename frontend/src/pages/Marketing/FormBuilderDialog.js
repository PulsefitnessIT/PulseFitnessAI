import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Plus, Trash2, GripVertical, ChevronUp, ChevronDown } from 'lucide-react';
import { useAuth } from '@/App';

const FIELD_TYPES = [
  { value: 'text', label: 'Single-line text' },
  { value: 'email', label: 'Email' },
  { value: 'phone', label: 'Phone' },
  { value: 'textarea', label: 'Multi-line text' },
  { value: 'select', label: 'Dropdown' },
  { value: 'checkbox', label: 'Checkbox' },
  { value: 'number', label: 'Number' },
];

const CRM_PROPERTIES = [
  { value: '', label: '— Don\'t map to CRM —' },
  { value: 'first_name', label: 'First name' },
  { value: 'last_name', label: 'Last name' },
  { value: 'email', label: 'Email' },
  { value: 'phone', label: 'Phone' },
  { value: 'company_name', label: 'Company name' },
  { value: 'notes', label: 'Notes' },
];

const blankField = () => ({
  id: `f-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  label: 'New field',
  field_type: 'text',
  required: false,
  placeholder: '',
  options: [],
  crm_property: null,
});

const FormBuilderDialog = ({ API, headers, form, onClose, onSaved }) => {
  const { user } = useAuth();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [fields, setFields] = useState([]);
  const [submitButtonLabel, setSubmitButtonLabel] = useState('Submit');
  const [successMessage, setSuccessMessage] = useState("Thanks — we've received your details.");
  const [requireConsent, setRequireConsent] = useState(true);
  // Iter 238h — pull the org's brand name into the default consent
  // copy so Pulse Fitness operators don't see "Pulse Fitness" by default.
  // Falls back to "us" when nothing is available so the sentence still
  // reads naturally during seed/preview states.
  const orgName = (
    user?.company_name
    || user?.organization_name
    || (user?.account_type === 'pulse_pro' || user?.account_type === 'lite' ? 'Pulse Fitness' : null)
    || 'us'
  );
  // Brand-neutral placeholder hint — never leak the other brand into
  // an operator's form-builder placeholder ghost-text.
  const defaultBrand = user?.organization_name || user?.company_name || 'Your Gym';
  const [consentText, setConsentText] = useState(
    `I agree to be contacted by ${orgName} and consent to my data being processed in line with the privacy policy.`,
  );
  const [sendConfirmation, setSendConfirmation] = useState(false);
  const [confirmationSubject, setConfirmationSubject] = useState('Thanks for getting in touch');
  const [confirmationBody, setConfirmationBody] = useState("We'll be in touch shortly.");
  const [notifyEmails, setNotifyEmails] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (form) {
      setName(form.name || '');
      setDescription(form.description || '');
      setFields(form.fields?.length ? form.fields : [blankField()]);
      setSubmitButtonLabel(form.submit_button_label || 'Submit');
      setSuccessMessage(form.success_message || '');
      setRequireConsent(form.require_consent !== false);
      setConsentText(form.consent_text || '');
      setSendConfirmation(!!form.send_confirmation);
      setConfirmationSubject(form.confirmation_subject || 'Thanks for getting in touch');
      setConfirmationBody(form.confirmation_body || '');
      setNotifyEmails((form.notify_emails || []).join(', '));
    } else {
      setFields([
        { ...blankField(), label: 'First name', crm_property: 'first_name', required: true },
        { ...blankField(), label: 'Email', field_type: 'email', crm_property: 'email', required: true },
      ]);
    }
  }, [form]);

  // Iter 232 — pull custom contact properties so the CRM mapping select
  // can route form fields directly into custom_fields.<key>.
  const [customCrmProps, setCustomCrmProps] = useState([]);
  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/api/custom-properties?entity_type=contact`, { headers })
      .then((r) => {
        if (cancelled) return;
        setCustomCrmProps((r.data.properties || []).map((p) => ({
          value: `custom.${p.key}`,
          label: `${p.label} (custom)`,
        })));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [API, headers]);
  const fullCrmOptions = React.useMemo(() => [...CRM_PROPERTIES, ...customCrmProps], [customCrmProps]);

  const updateField = (idx, patch) => {
    setFields((arr) => arr.map((f, i) => (i === idx ? { ...f, ...patch } : f)));
  };
  const moveField = (idx, dir) => {
    setFields((arr) => {
      const next = [...arr];
      const j = idx + dir;
      if (j < 0 || j >= next.length) return arr;
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  };
  const removeField = (idx) => setFields((arr) => arr.filter((_, i) => i !== idx));
  const addField = () => setFields((arr) => [...arr, blankField()]);

  const onSave = async () => {
    if (!name.trim()) { toast.error('Form needs a name'); return; }
    if (fields.length === 0) { toast.error('Add at least one field'); return; }
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        fields: fields.map((f) => ({
          ...f,
          options: f.field_type === 'select'
            ? (typeof f.options === 'string' ? f.options.split(',').map((s) => s.trim()).filter(Boolean) : f.options || [])
            : [],
          crm_property: f.crm_property || null,
        })),
        submit_button_label: submitButtonLabel,
        success_message: successMessage,
        require_consent: requireConsent,
        consent_text: consentText,
        send_confirmation: sendConfirmation,
        confirmation_subject: confirmationSubject,
        confirmation_body: confirmationBody,
        notify_emails: notifyEmails
          .split(',').map((s) => s.trim()).filter((s) => s.includes('@')),
      };
      if (form) {
        await axios.put(`${API}/api/marketing/forms/${form.id}`, payload, { headers });
      } else {
        await axios.post(`${API}/api/marketing/forms`, payload, { headers });
      }
      toast.success(form ? 'Form updated' : 'Form created');
      onSaved && onSaved();
    } catch (e) {
      toast.error('Save failed', { description: e.response?.data?.detail });
    }
    setSaving(false);
  };

  return (
    <Dialog open={true} onOpenChange={(v) => !v && onClose && onClose()}>
      <DialogContent className="bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="form-builder-dialog">
        <DialogHeader>
          <DialogTitle>{form ? 'Edit form' : 'New form'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Name *</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={`e.g. ${defaultBrand} Demo Request`} className="mt-1" data-testid="form-builder-name" />
            </div>
            <div>
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Submit button label</Label>
              <Input value={submitButtonLabel} onChange={(e) => setSubmitButtonLabel(e.target.value)} className="mt-1" data-testid="form-builder-submit-label" />
            </div>
          </div>
          <div>
            <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Description (shown above the form)</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="mt-1" data-testid="form-builder-description" />
          </div>

          {/* Fields */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Fields</Label>
              <Button size="sm" variant="outline" onClick={addField} className="border-zinc-200 dark:border-zinc-700" data-testid="form-builder-add-field">
                <Plus size={12} className="mr-1" /> Add field
              </Button>
            </div>
            <div className="space-y-2">
              {fields.map((f, idx) => (
                <div key={f.id} className="border border-zinc-200 rounded-md p-3 bg-zinc-50 dark:bg-zinc-950/40 dark:border-zinc-800" data-testid={`form-builder-field-${idx}`}>
                  <div className="flex items-start gap-2">
                    <GripVertical size={14} className="text-zinc-400 mt-2" />
                    <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-2">
                      <div>
                        <Label className="text-zinc-600 text-xs">Label</Label>
                        <Input value={f.label} onChange={(e) => updateField(idx, { label: e.target.value })} className="mt-1 text-sm" />
                      </div>
                      <div>
                        <Label className="text-zinc-600 text-xs">Type</Label>
                        <select
                          value={f.field_type}
                          onChange={(e) => updateField(idx, { field_type: e.target.value })}
                          className="mt-1 w-full bg-white dark:bg-zinc-900 border border-zinc-200 rounded-md px-2 py-1 text-sm dark:border-zinc-800"
                        >
                          {FIELD_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                      </div>
                      <div>
                        <Label className="text-zinc-600 text-xs">CRM mapping</Label>
                        <select
                          value={f.crm_property || ''}
                          onChange={(e) => updateField(idx, { crm_property: e.target.value || null })}
                          className="mt-1 w-full bg-white dark:bg-zinc-900 border border-zinc-200 rounded-md px-2 py-1 text-sm dark:border-zinc-800"
                        >
                          {fullCrmOptions.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                        </select>
                      </div>
                      <div>
                        <Label className="text-zinc-600 text-xs">Placeholder</Label>
                        <Input value={f.placeholder || ''} onChange={(e) => updateField(idx, { placeholder: e.target.value })} className="mt-1 text-sm" />
                      </div>
                      {f.field_type === 'select' && (
                        <div className="md:col-span-2">
                          <Label className="text-zinc-600 text-xs">Options (comma-separated)</Label>
                          <Input
                            value={Array.isArray(f.options) ? f.options.join(', ') : (f.options || '')}
                            onChange={(e) => updateField(idx, { options: e.target.value })}
                            placeholder="Small, Medium, Large"
                            className="mt-1 text-sm"
                          />
                        </div>
                      )}
                      <div className="md:col-span-2 flex items-center gap-3">
                        <label className="flex items-center gap-2 text-sm text-zinc-700">
                          <input
                            type="checkbox"
                            checked={!!f.required}
                            onChange={(e) => updateField(idx, { required: e.target.checked })}
                          />
                          Required
                        </label>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <Button size="sm" variant="ghost" onClick={() => moveField(idx, -1)} disabled={idx === 0} className="h-7 w-7 p-0">
                        <ChevronUp size={12} />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => moveField(idx, 1)} disabled={idx === fields.length - 1} className="h-7 w-7 p-0">
                        <ChevronDown size={12} />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => removeField(idx)} className="h-7 w-7 p-0 text-rose-600">
                        <Trash2 size={12} />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Behaviour */}
          <div className="border-t border-zinc-100 dark:border-zinc-800 pt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Success message</Label>
              <Textarea rows={2} value={successMessage} onChange={(e) => setSuccessMessage(e.target.value)} className="mt-1 text-sm" />
            </div>
            <div>
              <Label className="text-zinc-700 dark:text-zinc-300 text-sm">Notify emails (comma-separated)</Label>
              <Input value={notifyEmails} onChange={(e) => setNotifyEmails(e.target.value)} placeholder="leader@pulsefitness.ai" className="mt-1 text-sm" data-testid="form-builder-notify" />
              <p className="text-zinc-400 text-xs mt-1">Your email is added automatically.</p>
            </div>
            <div className="md:col-span-2">
              <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input type="checkbox" checked={requireConsent} onChange={(e) => setRequireConsent(e.target.checked)} />
                Require GDPR consent checkbox
              </label>
              {requireConsent && (
                <Textarea rows={2} value={consentText} onChange={(e) => setConsentText(e.target.value)} className="mt-2 text-sm" />
              )}
            </div>
            <div className="md:col-span-2">
              <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input type="checkbox" checked={sendConfirmation} onChange={(e) => setSendConfirmation(e.target.checked)} />
                Send a confirmation email to the submitter
              </label>
              {sendConfirmation && (
                <div className="mt-2 grid grid-cols-1 gap-2">
                  <Input value={confirmationSubject} onChange={(e) => setConfirmationSubject(e.target.value)} placeholder="Subject" className="text-sm" />
                  <Textarea rows={3} value={confirmationBody} onChange={(e) => setConfirmationBody(e.target.value)} placeholder="Body" className="text-sm" />
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={onSave} disabled={saving} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="form-builder-save">
              {saving ? 'Saving…' : (form ? 'Save changes' : 'Create form')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default FormBuilderDialog;
