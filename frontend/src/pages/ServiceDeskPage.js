import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  LayoutDashboard, Users, ScrollText, Upload, LogOut,
  Search, Eye, ArrowLeft, UserCog, Archive as ArchiveIcon, Wrench,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';

import DeskSummary from './ServiceDesk/DeskSummary';
import DeskCustomers from './ServiceDesk/DeskCustomers';
import DeskCustomerDetail from './ServiceDesk/DeskCustomerDetail';
import DeskAuditLog from './ServiceDesk/DeskAuditLog';
import DeskEquipment from './ServiceDesk/DeskEquipment';
import AdminArchive from './MasterAdmin/AdminArchive';

const TABS = [
  { id: 'summary', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'customers', label: 'Customers', icon: Users },
  { id: 'equipment', label: 'Equipment', icon: Wrench },
  { id: 'archive', label: 'Archive', icon: ArchiveIcon },
  { id: 'imports', label: 'Imports', icon: Upload, disabled: true, note: 'Coming soon' },
  { id: 'audit', label: 'Audit Log', icon: ScrollText },
];

export default function ServiceDeskPage() {
  const { user, logout, API } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('summary');
  const [selectedOrgId, setSelectedOrgId] = useState(null);

  useEffect(() => {
    if (!user?.is_service_desk && !user?.is_master_admin) {
      navigate('/login', { replace: true });
    }
  }, [user, navigate]);

  const handleSelectCustomer = (id) => {
    setSelectedOrgId(id);
    setTab('customers');
  };

  return (
    <div className="min-h-screen bg-[var(--gx-bg)] flex theme-gymaxis" data-testid="service-desk-page" data-theme="light">
      <aside className="fixed inset-y-0 left-0 z-40 w-60 bg-white border-r border-slate-200 flex flex-col">
        <div className="p-5 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white flex items-center justify-center overflow-hidden gx-grad-ring shadow-sm">
              <img src="/brand/gymaxis-mark-tight.png" alt="GymAxis" className="w-6 h-6 object-contain" draggable={false} />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-900 tracking-tight">Service Desk</div>
              <div className="text-[10px] text-slate-400 uppercase tracking-[0.16em] font-semibold">GymAxis Operations</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {TABS.map(({ id, label, icon: Icon, disabled, note }) => (
            <button
              key={id}
              onClick={() => { if (!disabled) { setTab(id); setSelectedOrgId(null); } }}
              disabled={disabled}
              data-testid={`desk-tab-${id}`}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-all ${
                tab === id
                  ? 'bg-gradient-to-r from-[var(--gx-brand-from)]/10 to-[var(--gx-brand-to)]/10 text-[var(--gx-brand-from)] font-semibold ring-1 ring-[var(--gx-brand-from)]/15'
                  : disabled
                  ? 'text-slate-400 cursor-not-allowed'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="flex-1">{label}</span>
              {note && <span className="text-[9px] uppercase tracking-wide text-slate-400">{note}</span>}
            </button>
          ))}
        </nav>

        <div className="border-t border-slate-100 p-3 space-y-2">
          <div className="text-xs text-slate-500 px-1">
            <div className="font-medium text-slate-700 truncate">{user?.full_name || user?.email}</div>
            <div className="truncate">{user?.email}</div>
            {user?.is_master_admin && (
              <Badge variant="outline" className="mt-1 text-[9px] border-slate-200">Master Admin</Badge>
            )}
          </div>
          {user?.is_master_admin && (
            <Button
              variant="ghost" size="sm"
              onClick={() => navigate('/master-admin')}
              className="w-full justify-start text-slate-600 hover:text-slate-900"
              data-testid="desk-back-to-master-admin"
            >
              <ArrowLeft className="w-4 h-4 mr-2" /> Back to Master Admin
            </Button>
          )}
          <Button
            variant="ghost" size="sm"
            onClick={() => { logout(); navigate('/login'); }}
            className="w-full justify-start text-slate-600 hover:text-slate-900"
            data-testid="desk-logout"
          >
            <LogOut className="w-4 h-4 mr-2" /> Log out
          </Button>
        </div>
      </aside>

      <main className="flex-1 ml-60 p-8 max-w-6xl">
        {tab === 'summary' && <DeskSummary API={API} onJumpToCustomers={() => setTab('customers')} />}
        {tab === 'customers' && !selectedOrgId && (
          <DeskCustomers API={API} onSelect={handleSelectCustomer} />
        )}
        {tab === 'customers' && selectedOrgId && (
          <DeskCustomerDetail
            API={API}
            orgId={selectedOrgId}
            onBack={() => setSelectedOrgId(null)}
          />
        )}
        {tab === 'archive' && <AdminArchive />}
        {tab === 'equipment' && <DeskEquipment API={API} />}
        {tab === 'audit' && <DeskAuditLog API={API} />}
      </main>
    </div>
  );
}
