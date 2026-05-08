import React from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Mail } from 'lucide-react';

const AdminEmails = ({ emails }) => (
  <div className="space-y-4">
    <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
      <div className="p-4 border-b border-zinc-100">
        <h3 className="font-medium text-zinc-900">Email Log</h3>
        <p className="text-xs text-zinc-400 mt-1">All outbound emails (supplier cases, purchase orders)</p>
      </div>
      <div className="divide-y divide-zinc-50 max-h-[600px] overflow-y-auto" data-testid="email-log-list">
        {emails.map((e, i) => (
          <div key={i} className="p-3 flex items-center gap-3 hover:bg-zinc-50">
            <div className="w-7 h-7 rounded-full bg-blue-50 flex items-center justify-center flex-shrink-0">
              <Mail size={12} className="text-blue-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-zinc-900 truncate">{e.subject}</p>
              <p className="text-xs text-zinc-400">To: {e.to || '—'} · {e.created_at ? new Date(e.created_at).toLocaleString() : ''}</p>
            </div>
            <Badge className={e.type === 'purchase_order' ? 'bg-emerald-50 text-emerald-700' : 'bg-blue-50 text-blue-700'}>
              {e.type === 'purchase_order' ? 'PO' : 'Case'}
            </Badge>
          </div>
        ))}
        {emails.length === 0 && <p className="text-center text-zinc-400 py-12 text-sm">No emails sent yet</p>}
      </div>
    </Card>
  </div>
);

export default AdminEmails;
