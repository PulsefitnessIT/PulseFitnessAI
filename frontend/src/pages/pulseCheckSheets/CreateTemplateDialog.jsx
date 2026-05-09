import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import { Plus, X } from 'lucide-react';

/** Modal for creating a new ad-hoc check-sheet template (e.g. "Pool checks"). */
const CreateTemplateDialog = ({
  open,
  onOpenChange,
  newTemplate,
  setNewTemplate,
  onSubmit,
}) => {
  const updateItem = (idx, value) => {
    const items = [...newTemplate.items];
    items[idx] = value;
    setNewTemplate({ ...newTemplate, items });
  };
  const removeItem = (idx) => {
    setNewTemplate({ ...newTemplate, items: newTemplate.items.filter((_, i) => i !== idx) });
  };
  const addItem = () => {
    setNewTemplate({ ...newTemplate, items: [...newTemplate.items, ''] });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-lg dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800">
        <DialogHeader><DialogTitle>Create Custom Check Sheet</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="text-zinc-700 text-sm">Template Name</Label>
            <Input
              value={newTemplate.name}
              onChange={e => setNewTemplate({ ...newTemplate, name: e.target.value })}
              placeholder="e.g., Swimming Pool Checks"
              className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
              data-testid="pulse-template-name"
            />
          </div>
          <div>
            <Label className="text-zinc-700 text-sm">Check Items</Label>
            <div className="space-y-2 mt-1">
              {newTemplate.items.map((item, idx) => (
                <div key={idx} className="flex gap-2">
                  <Input
                    value={item}
                    onChange={e => updateItem(idx, e.target.value)}
                    placeholder={`Item ${idx + 1}`}
                    className="bg-white border-zinc-200 text-zinc-900 text-sm dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
                  />
                  {newTemplate.items.length > 1 && (
                    <button
                      onClick={() => removeItem(idx)}
                      className="text-zinc-400 hover:text-red-500"
                    ><X size={14} /></button>
                  )}
                </div>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              className="border-zinc-200 text-zinc-600 mt-2 dark:border-zinc-800"
              onClick={addItem}
            >
              <Plus size={13} className="mr-1" /> Add Item
            </Button>
          </div>
          <Button
            onClick={onSubmit}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white"
            data-testid="pulse-save-template"
          >Create Template</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default CreateTemplateDialog;
