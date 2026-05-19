import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Calendar, CheckCircle, X, ChevronDown, ChevronUp,
} from 'lucide-react';

/** History sub-tab — collapsible list of completed check-sheets. */
const HistoryList = ({ history }) => {
  const [expanded, setExpanded] = useState(null);

  if (!history.length) {
    return <p className="text-center text-zinc-400 py-8 text-sm">No check sheets completed yet</p>;
  }

  return (
    <div className="space-y-3">
      {history.map((entry, idx) => {
        const total = entry.items?.length || 0;
        const checked = (entry.items || []).filter(i => i.checked).length;
        const isOpen = expanded === idx;
        return (
          <Card
            key={idx}
            className="bg-white border-zinc-200 shadow-sm p-5 cursor-pointer dark:bg-zinc-900 dark:border-zinc-800"
            onClick={() => setExpanded(isOpen ? null : idx)}
            data-testid={`pulse-history-${idx}`}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-zinc-900 text-sm dark:text-zinc-100">
                  {entry.template_name}
                </p>
                <p className="text-xs text-zinc-400">
                  <Calendar size={11} className="inline mr-1" />
                  {entry.completed_date} · By: {entry.completed_by}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge className={checked === total ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}>
                  {checked}/{total}
                </Badge>
                {isOpen
                  ? <ChevronUp size={14} className="text-zinc-400" />
                  : <ChevronDown size={14} className="text-zinc-400" />}
              </div>
            </div>
            {isOpen && (
              <div className="mt-3 pt-3 border-t border-zinc-100 space-y-1 dark:border-zinc-800">
                {(entry.items || []).map((item, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm py-0.5">
                    {item.checked
                      ? <CheckCircle size={13} className="text-emerald-500" />
                      : <X size={13} className="text-red-400" />}
                    <span className={item.checked ? 'text-zinc-900 dark:text-zinc-100' : 'text-zinc-400'}>
                      {item.name}
                    </span>
                  </div>
                ))}
                {entry.notes && (
                  <p className="text-xs text-zinc-400 mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
                    Notes: {entry.notes}
                  </p>
                )}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
};

export default HistoryList;
