import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MessageSquare } from 'lucide-react';

const DiagnosisTab = ({
 chatHistory, chatMessage, chatLoading, chatMachineType, chatMachineModel,
 allEquipment, onSubmit, onMessageChange, onMachineTypeChange, onModelChange, t
}) => {
 return (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6 ai-glow" data-testid="diagnosis-card">
 <h2 className="text-2xl font-semibold text-white mb-4" data-testid="diagnosis-title">{t('diagnosis.title')}</h2>
 <p className="text-[var(--color-text-muted)] mb-6">{t('diagnosis.desc')}</p>

 {/* Machine selection fields */}
 <div className="grid grid-cols-2 gap-4 mb-6 p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg">
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">{t('diagnosis.machine_type')}</Label>
 <Select value={chatMachineType} onValueChange={onMachineTypeChange}>
 <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="diagnosis-machine-type">
 <SelectValue placeholder="Select machine type" />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]">
 {[...new Set(allEquipment.map(e => e.equipment_type).filter(Boolean))].map(type => (
 <SelectItem key={type} value={type}>{type}</SelectItem>
 ))}
 {allEquipment.length === 0 && <SelectItem value="_none" disabled>No equipment found — add equipment first</SelectItem>}
 </SelectContent>
 </Select>
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-sm">{t('diagnosis.model_label')}</Label>
 <Input value={chatMachineModel} onChange={e => onModelChange(e.target.value)}
 placeholder={t('diagnosis.model_placeholder')} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="diagnosis-machine-model" />
 </div>
 </div>

 <div className="space-y-4 mb-6 max-h-96 overflow-y-auto" data-testid="chat-history">
 {chatHistory.map((msg, idx) => (
 <div key={idx} className={`p-4 rounded-lg ${msg.role === 'user' ? 'bg-[rgb(var(--rgb-brand-blue)/0.1)] ml-12' : 'bg-[var(--theme-surface)] mr-12'}`} data-testid={`chat-message-${idx}`}>
 <p className="text-white whitespace-pre-wrap">{msg.content}</p>
 </div>
 ))}
 {chatHistory.length === 0 && (
 <div className="text-center text-[var(--color-text-muted)] py-8">
 <MessageSquare size={48} className="mx-auto mb-4 opacity-50" />
 <p>{t('diagnosis.empty_state')}</p>
 </div>
 )}
 </div>

 <form onSubmit={onSubmit} className="flex space-x-3">
 <Input value={chatMessage} onChange={(e) => onMessageChange(e.target.value)}
 placeholder={chatMachineType ? t('diagnosis.placeholder_with_machine', { machine: chatMachineType }) : t('diagnosis.placeholder_default')}
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] flex-1" data-testid="chat-input" />
 <Button type="submit" disabled={chatLoading || !chatMachineType} className="" data-testid="chat-submit-btn">
 {chatLoading ? (
 <span className="flex items-center gap-2">
 <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
 {t('diagnosis.diagnosing')}
 </span>
 ) : t('diagnosis.send')}
 </Button>
 </form>
 </Card>
 );
};

export default DiagnosisTab;
