import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Activity, RefreshCw } from 'lucide-react';

const AdminActivity = ({ activityLog, onRefresh }) => (
  <div className="space-y-4">
    <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
      <div className="p-4 border-b border-zinc-100 flex items-center justify-between">
        <h3 className="font-medium text-zinc-900">System Activity</h3>
        <Button size="sm" variant="outline" className="h-7 border-zinc-200 text-zinc-600" onClick={onRefresh} data-testid="refresh-activity">
          <RefreshCw size={12} className="mr-1" /> Refresh
        </Button>
      </div>
      <div className="divide-y divide-zinc-50 max-h-[600px] overflow-y-auto" data-testid="activity-log-list">
        {activityLog.map((log, i) => (
          <div key={i} className="p-3 flex items-start gap-3 hover:bg-zinc-50">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
              log.action === 'user_login' ? 'bg-blue-50' :
              log.action?.includes('disable') ? 'bg-red-50' :
              log.action === 'impersonate' ? 'bg-violet-50' :
              'bg-zinc-100'
            }`}>
              <Activity size={12} className={
                log.action === 'user_login' ? 'text-blue-600' :
                log.action?.includes('disable') ? 'text-red-600' :
                log.action === 'impersonate' ? 'text-violet-600' :
                'text-zinc-500'
              } />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-zinc-900">{log.details}</p>
              <p className="text-xs text-zinc-400 mt-0.5">{log.admin_email} {log.timestamp ? `· ${new Date(log.timestamp).toLocaleString()}` : ''}</p>
            </div>
            {log.action && <Badge className="bg-zinc-100 text-zinc-500 text-[10px] flex-shrink-0">{log.action.replace(/_/g, ' ')}</Badge>}
          </div>
        ))}
        {activityLog.length === 0 && <p className="text-center text-zinc-400 py-12 text-sm">No activity recorded yet</p>}
      </div>
    </Card>
  </div>
);

export default AdminActivity;
