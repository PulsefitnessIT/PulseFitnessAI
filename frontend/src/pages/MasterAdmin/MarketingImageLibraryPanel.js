/**
 * MarketingImageLibraryPanel (Iter 238f)
 *
 * Master admin curates a shared image library that auto-populates for
 * every Pulse Fitness operator with the Marketing bolt-on. Operators
 * see the list inside Marketing Suite's Creative Studio "Brand library".
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Sparkles, Plus, Trash2, Loader2, RefreshCw, Image as ImageIcon, Tag,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { SkeletonCard, SkeletonLine } from '@/components/shared/Skeleton';

const CATEGORIES = ['general', 'campaigns', 'classes', 'wellness', 'lifestyle', 'equipment'];

const MarketingImageLibraryPanel = () => {
  const { API } = useAuth();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ url: '', label: '', tags: '', category: 'general' });
  const [filter, setFilter] = useState('all');

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/marketing-image-library`, { headers: headers() });
      setRows(r.data?.rows || []);
    } catch (e) {
      notify.error('Could not load library', e.response?.data?.detail);
    }
    setLoading(false);
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!draft.url.trim() || !draft.label.trim()) {
      notify.error('Missing fields', 'Image URL and label are required');
      return;
    }
    setAdding(true);
    try {
      await axios.post(
        `${API}/master-admin/marketing-image-library`,
        { ...draft, tags: draft.tags.split(',').map((t) => t.trim()).filter(Boolean) },
        { headers: headers() },
      );
      notify.success('Added to library', `${draft.label} now visible to Marketing Suite tenants.`);
      setDraft({ url: '', label: '', tags: '', category: 'general' });
      await load();
    } catch (e) {
      notify.error('Add failed', e.response?.data?.detail);
    }
    setAdding(false);
  };

  const handleDelete = async (row) => {
    if (!window.confirm(`Remove "${row.label}" from the shared library? Tenants will lose access on next refresh.`)) return;
    try {
      await axios.delete(`${API}/master-admin/marketing-image-library/${row.id}`, { headers: headers() });
      notify.success('Removed', row.label);
      await load();
    } catch (e) {
      notify.error('Delete failed', e.response?.data?.detail);
    }
  };

  const filtered = filter === 'all' ? rows : rows.filter((r) => r.category === filter);

  return (
    <div className="space-y-4" data-testid="marketing-image-library-panel">
      <Card className="p-5 border-zinc-200">
        <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Sparkles size={20} className="text-fuchsia-600" />
            <div>
              <h3 className="text-base font-semibold text-zinc-900">Marketing Suite shared library</h3>
              <p className="text-xs text-zinc-500 mt-0.5">
                Curated images auto-populate for every Pulse Fitness operator with the Marketing bolt-on.
                {' '}<strong>{rows.length}</strong> images live.
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={load} data-testid="library-refresh">
            <RefreshCw size={13} className="mr-1" /> Refresh
          </Button>
        </div>

        {/* Add form */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 p-3 bg-zinc-50 rounded-lg border border-dashed border-zinc-200" data-testid="library-add-row">
          <Input
            value={draft.label}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            placeholder="Label (e.g. Spin class hero)"
            className="md:col-span-3 h-9"
            data-testid="library-add-label"
          />
          <Input
            value={draft.url}
            onChange={(e) => setDraft({ ...draft, url: e.target.value })}
            placeholder="Image URL (https:// or data:image/…)"
            className="md:col-span-4 h-9"
            data-testid="library-add-url"
          />
          <Input
            value={draft.tags}
            onChange={(e) => setDraft({ ...draft, tags: e.target.value })}
            placeholder="tags, comma, separated"
            className="md:col-span-2 h-9"
            data-testid="library-add-tags"
          />
          <select
            value={draft.category}
            onChange={(e) => setDraft({ ...draft, category: e.target.value })}
            className="md:col-span-2 h-9 rounded-md border border-zinc-200 bg-white px-2 text-sm"
            data-testid="library-add-category"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>
            ))}
          </select>
          <Button
            onClick={handleAdd}
            disabled={adding}
            className="md:col-span-1 h-9 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
            data-testid="library-add-btn"
          >
            {adding ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          </Button>
        </div>
      </Card>

      {/* Category filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setFilter('all')}
          className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${filter === 'all' ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'}`}
          data-testid="library-filter-all"
        >
          All ({rows.length})
        </button>
        {CATEGORIES.map((c) => {
          const count = rows.filter((r) => r.category === c).length;
          if (!count) return null;
          return (
            <button
              key={c}
              type="button"
              onClick={() => setFilter(c)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${filter === c ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'}`}
              data-testid={`library-filter-${c}`}
            >
              {c} ({count})
            </button>
          );
        })}
      </div>

      {/* Image grid */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3" data-testid="marketing-images-loading">
          {[0,1,2,3,4,5,6,7].map((i) => (
            <SkeletonCard key={i} className="overflow-hidden">
              <div className="h-32 -mx-4 -mt-4 mb-3 bg-zinc-200/70 dark:bg-white/[0.07] animate-pulse" />
              <SkeletonLine className="mb-2" width="65%" />
              <SkeletonLine width="40%" />
            </SkeletonCard>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="p-10 text-center border-zinc-200">
          <ImageIcon size={32} className="text-zinc-300 mx-auto mb-3" />
          <p className="text-sm text-zinc-500">
            {filter === 'all'
              ? 'No images yet. Add the first one above to seed the library.'
              : `No images in "${filter}" yet.`}
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3" data-testid="library-grid">
          {filtered.map((row) => (
            <Card key={row.id} className="overflow-hidden border-zinc-200 group" data-testid={`library-card-${row.id}`}>
              <div className="aspect-[4/3] bg-zinc-100 relative">
                <img
                  src={row.url}
                  alt={row.label}
                  loading="lazy"
                  className="w-full h-full object-cover"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
                <button
                  type="button"
                  onClick={() => handleDelete(row)}
                  className="absolute top-2 right-2 p-1.5 rounded-md bg-white/90 backdrop-blur text-rose-600 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white"
                  data-testid={`library-delete-${row.id}`}
                >
                  <Trash2 size={13} />
                </button>
              </div>
              <div className="p-3">
                <p className="text-sm font-medium text-zinc-900 truncate">{row.label}</p>
                <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                  <Badge className="bg-fuchsia-50 text-fuchsia-700 border border-fuchsia-200 text-[10px] capitalize">
                    {row.category || 'general'}
                  </Badge>
                  {(row.tags || []).slice(0, 3).map((t) => (
                    <Badge key={t} className="bg-zinc-100 text-zinc-600 border border-zinc-200 text-[10px]">
                      <Tag size={9} className="mr-0.5" /> {t}
                    </Badge>
                  ))}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default MarketingImageLibraryPanel;
