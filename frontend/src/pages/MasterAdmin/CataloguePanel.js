import React, { useState } from 'react';
import { useAuth } from '@/App';
import { Image as ImageIcon, FileText, Camera, Megaphone, Share2 } from 'lucide-react';
import AdminSpecSheets from './AdminSpecSheets';
import AdminEquipmentImages from './AdminEquipmentImages';
import ManufacturerDomainsPanel from './ManufacturerDomainsPanel';
import MarketingImageLibraryPanel from './MarketingImageLibraryPanel';
import SocialMediaLibraryPanel from './SocialMediaLibraryPanel';

/**
 * Iter 215b — Equipment Image Catalogue (combined surface).
 *
 * "Catalogue" and "Crawl Domains" were previously two separate sub-tabs
 * showing essentially the same domain list. They have been merged into
 * a single Catalogue view that owns both the manufacturer crawl list
 * (with Add / Edit / Delete / Sync Now) and the per-domain product /
 * last-ingested stats.
 */
const CataloguePanel = () => {
  const { API } = useAuth();
  const [tab, setTab] = useState('catalogue');

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  return (
    <div className="space-y-4" data-testid="catalogue-panel">
      <div className="flex gap-1 border-b border-zinc-200 overflow-x-auto" data-testid="catalogue-tabs">
        {[
          { id: 'catalogue', label: 'Catalogue', icon: ImageIcon },
          { id: 'spec-sheets', label: 'Spec Sheets', icon: FileText },
          { id: 'equipment-images', label: 'Equipment Images', icon: Camera },
          { id: 'marketing', label: 'Marketing', icon: Megaphone },
          { id: 'social-media', label: 'Social Media', icon: Share2 },
        ].map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${tab === t.id ? 'border-zinc-900 text-zinc-900' : 'border-transparent text-zinc-500 hover:text-zinc-700'}`}
              data-testid={`catalogue-tab-${t.id}`}
            >
              <Icon size={14} className="inline mr-1.5 -mt-0.5" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'catalogue' && <ManufacturerDomainsPanel />}
      {tab === 'spec-sheets' && <AdminSpecSheets headers={headers()} />}
      {tab === 'equipment-images' && <AdminEquipmentImages API={API} />}
      {tab === 'marketing' && <MarketingImageLibraryPanel />}
      {tab === 'social-media' && <SocialMediaLibraryPanel />}
    </div>
  );
};

export default CataloguePanel;
