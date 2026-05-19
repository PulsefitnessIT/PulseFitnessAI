/**
 * Journey Canvas — vertical visual editor (Iter 233).
 *
 * Adds omni-channel leaf nodes alongside the existing send_email /
 * send_sms / branch / wait / tag / notify_staff / goal types:
 *   • send_push     — title + body + optional link (web-push)
 *   • send_in_app   — title + body + optional link (always deliverable)
 *
 * The send_email / send_sms editors gain proper subject + body inputs
 * — the previous "template" name was a placeholder. Old journeys with
 * `template` still load (we surface it as a body fallback).
 */
import { useState } from 'react';
import {
  Sparkles, Clock, Mail, MessageSquare, Bell, BellRing, Smartphone,
  GitBranch, Tag, Target, Trash2, Plus,
} from 'lucide-react';

const NODE_DEFS = {
  wait:           { label: 'Wait',           icon: Clock,         colour: 'bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-800',     defaults: { duration_h: 24 } },
  send_email:     { label: 'Send email',     icon: Mail,          colour: 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800',       defaults: { subject: '', body: '' } },
  send_sms:       { label: 'Send SMS',       icon: MessageSquare, colour: 'bg-violet-50 dark:bg-violet-950/40 text-violet-700 dark:text-violet-300 border-violet-200 dark:border-violet-800', defaults: { body: '' } },
  send_push:      { label: 'Send push',      icon: Smartphone,    colour: 'bg-fuchsia-50 dark:bg-fuchsia-950/40 text-fuchsia-700 dark:text-fuchsia-300 border-fuchsia-200 dark:border-fuchsia-800', defaults: { title: '', body: '', link: '' } },
  send_in_app:    { label: 'Send in-app',    icon: BellRing,      colour: 'bg-cyan-50 dark:bg-cyan-950/40 text-cyan-700 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800',       defaults: { title: '', body: '', link: '' } },
  branch:         { label: 'If / else',      icon: GitBranch,     colour: 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',    defaults: { condition: 'opened' } },
  tag_contact:    { label: 'Tag contact',    icon: Tag,           colour: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800', defaults: { tag: 'engaged' } },
  notify_staff:   { label: 'Notify staff',   icon: Bell,          colour: 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',       defaults: { role: 'manager' } },
  goal:           { label: 'Goal',           icon: Target,        colour: 'bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800', defaults: { metric: 'booking' } },
};

const TRIGGERS = [
  { id: 'member_signed_up', label: 'New member signed up' },
  { id: 'missed_class', label: 'Missed a class' },
  { id: 'failed_payment', label: 'Failed payment' },
  { id: 'churn_risk_high', label: 'Churn risk passed 70' },
  { id: 'class_booking', label: 'Class booking' },
];

const JourneyCanvas = ({ trigger, setTrigger, nodes, setNodes }) => {
  const [editing, setEditing] = useState(null);

  const addNode = (type) => {
    const def = NODE_DEFS[type];
    const id = `n${Date.now()}`;
    setNodes((ns) => [...ns, { id, type, ...def.defaults }]);
    setEditing(id);
  };
  const updateNode = (id, patch) => setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, ...patch } : n)));
  const removeNode = (id) => setNodes((ns) => ns.filter((n) => n.id !== id));

  return (
    <div className="space-y-3" data-testid="journey-canvas">
      {/* Trigger node */}
      <div className="flex flex-col items-center">
        <div className="w-full max-w-md rounded-xl border-2 border-[var(--color-brand-blue)] bg-gradient-to-r from-[rgb(var(--rgb-brand-blue)/0.1)] to-[rgb(var(--rgb-brand-cyan-hover)/0.1)] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles size={14} className="text-[var(--color-brand-blue)]" />
            <p className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-brand-blue)]">Trigger</p>
          </div>
          <select
            value={trigger}
            onChange={(e) => setTrigger(e.target.value)}
            className="w-full px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm bg-white dark:bg-zinc-900"
            data-testid="journey-canvas-trigger-select"
          >
            {TRIGGERS.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </div>
      </div>

      {/* Connector + nodes */}
      {nodes.map((n, i) => {
        const def = NODE_DEFS[n.type];
        const Icon = def?.icon || Mail;
        const isEditing = editing === n.id;
        return (
          <div key={n.id} className="flex flex-col items-center">
            <div className="w-px h-4 bg-zinc-300 dark:bg-zinc-700" />
            <div className={`w-full max-w-md rounded-xl border-2 ${def?.colour} p-3`} data-testid={`journey-node-${n.id}`}>
              <div className="flex items-center justify-between gap-2 mb-1">
                <div className="flex items-center gap-2">
                  <Icon size={13} />
                  <p className="text-xs font-semibold">{def?.label || n.type}</p>
                  <span className="text-[9px] uppercase tracking-wider opacity-60">step {i + 1}</span>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => setEditing(isEditing ? null : n.id)} className="text-[10px] font-semibold opacity-70 hover:opacity-100" data-testid={`journey-node-edit-${n.id}`}>
                    {isEditing ? 'Done' : 'Edit'}
                  </button>
                  <button onClick={() => removeNode(n.id)} className="text-rose-500 hover:text-rose-700" data-testid={`journey-node-delete-${n.id}`}>
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>
              {isEditing && (
                <div className="mt-2 space-y-1.5">
                  {n.type === 'wait' && (
                    <label className="block text-[10px] font-semibold opacity-80">Duration (hours)
                      <input
                        type="number" value={n.duration_h}
                        onChange={(e) => updateNode(n.id, { duration_h: parseInt(e.target.value, 10) || 1 })}
                        className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                        data-testid={`journey-node-${n.id}-duration`}
                      />
                    </label>
                  )}
                  {n.type === 'send_email' && (
                    <>
                      <label className="block text-[10px] font-semibold opacity-80">Subject
                        <input
                          value={n.subject || n.template || ''}
                          onChange={(e) => updateNode(n.id, { subject: e.target.value, template: undefined })}
                          placeholder="We've missed you, {{first_name}}"
                          className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                          data-testid={`journey-node-${n.id}-subject`}
                        />
                      </label>
                      <label className="block text-[10px] font-semibold opacity-80">Body (HTML)
                        <textarea
                          value={n.body || ''} rows={3}
                          onChange={(e) => updateNode(n.id, { body: e.target.value })}
                          placeholder="<p>Hi {{first_name}}, …</p>"
                          className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs font-mono bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                          data-testid={`journey-node-${n.id}-body`}
                        />
                      </label>
                    </>
                  )}
                  {n.type === 'send_sms' && (
                    <label className="block text-[10px] font-semibold opacity-80">Message (160 chars)
                      <textarea
                        value={n.body || n.template || ''} rows={2} maxLength={320}
                        onChange={(e) => updateNode(n.id, { body: e.target.value, template: undefined })}
                        placeholder="Hey {{first_name}}, your class is tomorrow at 7pm — text Y to confirm."
                        className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                        data-testid={`journey-node-${n.id}-body`}
                      />
                      <span className="text-[9px] opacity-60">{(n.body || n.template || '').length}/320</span>
                    </label>
                  )}
                  {(n.type === 'send_push' || n.type === 'send_in_app') && (
                    <>
                      <label className="block text-[10px] font-semibold opacity-80">Title
                        <input
                          value={n.title || ''}
                          onChange={(e) => updateNode(n.id, { title: e.target.value })}
                          placeholder="See you Saturday, {{first_name}}!"
                          className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                          data-testid={`journey-node-${n.id}-title`}
                        />
                      </label>
                      <label className="block text-[10px] font-semibold opacity-80">Body
                        <textarea
                          value={n.body || ''} rows={2}
                          onChange={(e) => updateNode(n.id, { body: e.target.value })}
                          placeholder="Your 9am Spin class with Sam is locked in."
                          className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                          data-testid={`journey-node-${n.id}-body`}
                        />
                      </label>
                      <label className="block text-[10px] font-semibold opacity-80">Link (optional)
                        <input
                          value={n.link || ''}
                          onChange={(e) => updateNode(n.id, { link: e.target.value })}
                          placeholder="/memberships/classes"
                          className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                          data-testid={`journey-node-${n.id}-link`}
                        />
                      </label>
                    </>
                  )}
                  {n.type === 'branch' && (
                    <label className="block text-[10px] font-semibold opacity-80">Condition
                      <select
                        value={n.condition}
                        onChange={(e) => updateNode(n.id, { condition: e.target.value })}
                        className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                        data-testid={`journey-node-${n.id}-condition`}
                      >
                        <option value="opened">Opened email</option>
                        <option value="clicked">Clicked link</option>
                        <option value="booked">Booked a class</option>
                      </select>
                    </label>
                  )}
                  {n.type === 'tag_contact' && (
                    <label className="block text-[10px] font-semibold opacity-80">Tag
                      <input
                        value={n.tag}
                        onChange={(e) => updateNode(n.id, { tag: e.target.value })}
                        className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                        data-testid={`journey-node-${n.id}-tag`}
                      />
                    </label>
                  )}
                  {n.type === 'notify_staff' && (
                    <label className="block text-[10px] font-semibold opacity-80">Role
                      <select
                        value={n.role}
                        onChange={(e) => updateNode(n.id, { role: e.target.value })}
                        className="w-full mt-1 px-2 py-1 border border-zinc-200 dark:border-zinc-800 rounded text-xs bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                        data-testid={`journey-node-${n.id}-role`}
                      >
                        <option value="manager">Manager</option>
                        <option value="trainer">Trainer</option>
                        <option value="admin">Admin</option>
                      </select>
                    </label>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}

      {/* Add node menu */}
      <div className="flex flex-col items-center">
        {nodes.length > 0 && <div className="w-px h-4 bg-zinc-300 dark:bg-zinc-700" />}
        <div className="w-full max-w-md rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/50 p-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 font-semibold mb-2 flex items-center gap-1">
            <Plus size={11} /> Add a step
          </p>
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5">
            {Object.entries(NODE_DEFS).map(([type, def]) => {
              const Icon = def.icon;
              return (
                <button
                  key={type}
                  onClick={() => addNode(type)}
                  className="flex flex-col items-center gap-0.5 p-2 rounded-md hover:bg-white dark:bg-zinc-900 dark:hover:bg-zinc-800 hover:shadow-sm transition border border-transparent hover:border-zinc-200 dark:border-transparent dark:hover:border-zinc-700"
                  data-testid={`journey-add-${type}`}
                >
                  <Icon size={13} className="text-zinc-600 dark:text-zinc-300" />
                  <span className="text-[9px] text-zinc-600 dark:text-zinc-400 font-medium leading-tight text-center">{def.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export default JourneyCanvas;
