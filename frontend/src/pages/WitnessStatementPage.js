/**
 * WitnessStatementPage — Iter 220t
 *
 * Public, no-auth page reached via the email link
 *   /witness-statement/{token}
 * Renders minimal incident context + a textarea + signature pad and
 * POSTs the statement to the public backend endpoint.
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, Shield, CheckCircle2, AlertTriangle } from 'lucide-react';
import IncidentSignaturePad from './IncidentSignaturePad';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function WitnessStatementPage() {
  const { token } = useParams();
  const [state, setState] = useState({ loading: true, error: null, context: null, done: false });
  const [statement, setStatement] = useState('');
  const [signature, setSignature] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    axios.get(`${API}/incidents/witness-statement/${token}`)
      .then((r) => active && setState({ loading: false, error: null, context: r.data, done: false }))
      .catch((e) => active && setState({
        loading: false,
        error: e.response?.data?.detail || 'Link not recognised.',
        context: null, done: false,
      }));
    return () => { active = false; };
  }, [token]);

  const submit = async () => {
    if (statement.trim().length < 20) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/incidents/witness-statement/${token}`, {
        statement, signature_b64: signature.startsWith('data:') ? signature.split(',', 2)[1] : signature,
      });
      setState((s) => ({ ...s, done: true }));
    } catch (e) {
      setState((s) => ({ ...s, error: e.response?.data?.detail || 'Could not save your statement.' }));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-indigo-50 py-10 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-2 mb-6 text-slate-700">
          <Shield className="text-blue-600" size={18} />
          <span className="font-extrabold tracking-tight">Pulse Fitness · Witness statement</span>
        </div>
        <Card className="p-6 rounded-2xl bg-white border border-slate-200 shadow-sm">
          {state.loading ? (
            <div className="py-10 text-center text-slate-500">
              <Loader2 className="animate-spin inline mr-2" size={14} /> Loading your statement form…
            </div>
          ) : state.error ? (
            <div className="py-6 text-center" data-testid="witness-error">
              <AlertTriangle className="text-amber-500 mx-auto mb-3" size={32} />
              <p className="font-bold text-slate-800">{state.error}</p>
              <p className="text-sm text-slate-500 mt-2">
                If you think this link should still work, please reply to the email and ask the manager to re-send it.
              </p>
            </div>
          ) : state.done ? (
            <div className="py-6 text-center" data-testid="witness-done">
              <CheckCircle2 className="text-emerald-500 mx-auto mb-3" size={32} />
              <p className="font-bold text-slate-800">Statement received. Thank you.</p>
              <p className="text-sm text-slate-500 mt-2">
                Your statement has been added to incident <strong>{state.context?.incident_reference}</strong>{' '}
                at <strong>{state.context?.org_name}</strong>. The manager handling the incident has been notified.
              </p>
            </div>
          ) : (
            <div className="space-y-5" data-testid="witness-form">
              <header>
                <p className="text-xs uppercase tracking-wider font-bold text-slate-500">Hi {state.context?.name},</p>
                <h1 className="text-2xl font-extrabold text-slate-900 mt-1">
                  Please record what you saw.
                </h1>
                <p className="text-sm text-slate-600 mt-2">
                  Incident reference <strong>{state.context?.incident_reference}</strong>{' '}
                  at <strong>{state.context?.org_name}</strong>
                  {state.context?.incident_location ? <>, location <strong>{state.context.incident_location}</strong></> : null}.
                  Your statement will be attached directly to the incident record and used as part of any
                  investigation.
                </p>
              </header>
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-slate-600">Your statement</label>
                <Textarea
                  rows={8}
                  value={statement}
                  onChange={(e) => setStatement(e.target.value)}
                  placeholder="What did you see and hear? Where were you standing? Approximate time? Please stick to facts you can confirm — opinions can be noted separately."
                  className="mt-1"
                  data-testid="witness-statement"
                />
                <p className="text-xs text-slate-400 mt-1">
                  Minimum 20 characters. {statement.trim().length}/20.
                </p>
              </div>
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-slate-600">Signature (optional)</label>
                <div className="mt-1">
                  <IncidentSignaturePad onChange={setSignature} testId="witness-signature" />
                </div>
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button
                  onClick={submit}
                  disabled={submitting || statement.trim().length < 20}
                  className="bg-blue-600 hover:bg-blue-700 text-white"
                  data-testid="witness-submit"
                >
                  {submitting ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
                  Submit statement
                </Button>
              </div>
              <p className="text-xs text-slate-400">
                Link expires {state.context?.expires_at ? new Date(state.context.expires_at).toLocaleDateString() : 'soon'}.
                One-time use. Your IP and timestamp are recorded as part of the audit trail.
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
