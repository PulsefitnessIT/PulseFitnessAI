/**
 * Hosted email archive — routed at /c/view/:id (no auth).
 * Renders a previously-sent campaign email as a standalone web page
 * (the {{view_in_browser_link}} target).
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Loader2, MailX } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function PublicEmailViewPage() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    axios.get(`${API}/comms/public/view/${id}`)
      .then(res => { setData(res.data); document.title = res.data.subject || 'Email'; })
      .catch(() => setError(true));
  }, [id]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0A0C12' }} data-testid="view-error">
        <div className="text-center">
          <MailX className="w-10 h-10 mx-auto mb-4 text-rose-400" />
          <p className="text-slate-300">This email is no longer available.</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0A0C12' }} data-testid="view-loading">
        <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: '#F3F4F6' }} data-testid="email-view-page">
      <div className="text-center py-3 text-xs text-slate-500 bg-white border-b border-slate-200">
        Viewing in browser · {data.subject}
      </div>
      {/* eslint-disable-next-line react/no-danger */}
      <div dangerouslySetInnerHTML={{ __html: data.html }} />
    </div>
  );
}
