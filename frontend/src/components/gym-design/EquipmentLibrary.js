import { Card } from '@/components/ui/card';

const GymIcon = ({ type, size = 24, color = 'var(--color-brand-blue)' }) => {
 const s = size;
 switch (type) {
 case 'treadmill':
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <rect x="3" y="8" width="18" height="3" rx="1" />
 <line x1="3" y1="14" x2="21" y2="14" />
 <line x1="5" y1="14" x2="4" y2="20" />
 <line x1="19" y1="14" x2="20" y2="20" />
 <line x1="6" y1="8" x2="5" y2="5" />
 <circle cx="5" cy="4" r="1" fill={color} />
 <line x1="8" y1="11" x2="16" y2="11" strokeDasharray="2 1" />
 </svg>
 );
 case 'bike':
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <circle cx="7" cy="17" r="3" />
 <circle cx="17" cy="17" r="3" />
 <path d="M7 17L12 7L17 17" />
 <line x1="12" y1="7" x2="12" y2="4" />
 <line x1="10" y1="4" x2="14" y2="4" />
 <path d="M9 12L15 12" />
 </svg>
 );
 case 'crosstrainer':
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <ellipse cx="12" cy="18" rx="6" ry="2" />
 <line x1="12" y1="18" x2="12" y2="6" />
 <line x1="8" y1="8" x2="16" y2="8" />
 <line x1="8" y1="8" x2="6" y2="14" />
 <line x1="16" y1="8" x2="18" y2="14" />
 <circle cx="12" cy="5" r="1.5" fill={color} />
 </svg>
 );
 case 'rower':
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <rect x="2" y="14" width="20" height="2" rx="1" />
 <rect x="8" y="11" width="4" height="3" rx="0.5" />
 <line x1="12" y1="14" x2="20" y2="14" />
 <line x1="3" y1="16" x2="5" y2="20" />
 <line x1="21" y1="16" x2="19" y2="20" />
 <path d="M10 11L10 8L14 8" />
 <circle cx="10" cy="7" r="1" fill={color} />
 </svg>
 );
 case 'bench':
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <rect x="4" y="10" width="16" height="3" rx="1" />
 <line x1="6" y1="13" x2="5" y2="19" />
 <line x1="18" y1="13" x2="19" y2="19" />
 <line x1="4" y1="10" x2="3" y2="7" />
 <line x1="20" y1="10" x2="21" y2="7" />
 <line x1="2" y1="7" x2="4" y2="7" />
 <line x1="20" y1="7" x2="22" y2="7" />
 </svg>
 );
 case 'rack':
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <rect x="4" y="3" width="2" height="18" />
 <rect x="18" y="3" width="2" height="18" />
 <line x1="4" y1="8" x2="20" y2="8" strokeWidth="2" />
 <line x1="4" y1="16" x2="20" y2="16" />
 <circle cx="3" cy="8" r="1.5" fill={color} />
 <circle cx="21" cy="8" r="1.5" fill={color} />
 </svg>
 );
 case 'smith':
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <rect x="5" y="2" width="2" height="20" />
 <rect x="17" y="2" width="2" height="20" />
 <line x1="5" y1="10" x2="19" y2="10" strokeWidth="2" />
 <circle cx="4" cy="10" r="1.5" fill={color} />
 <circle cx="20" cy="10" r="1.5" fill={color} />
 <line x1="7" y1="10" x2="7" y2="14" strokeDasharray="2 1" />
 <line x1="17" y1="10" x2="17" y2="14" strokeDasharray="2 1" />
 </svg>
 );
 case 'cable':
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <rect x="10" y="2" width="4" height="20" rx="1" />
 <line x1="10" y1="6" x2="4" y2="10" />
 <line x1="14" y1="6" x2="20" y2="10" />
 <rect x="2" y="10" width="4" height="2" rx="0.5" fill={color} fillOpacity="0.3" />
 <rect x="18" y="10" width="4" height="2" rx="0.5" fill={color} fillOpacity="0.3" />
 <line x1="10" y1="14" x2="6" y2="18" strokeDasharray="2 1" />
 <line x1="14" y1="14" x2="18" y2="18" strokeDasharray="2 1" />
 </svg>
 );
 default:
 return (
 <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5">
 <rect x="4" y="4" width="16" height="16" rx="2" />
 <line x1="8" y1="12" x2="16" y2="12" />
 <line x1="12" y1="8" x2="12" y2="16" />
 </svg>
 );
 }
};

const EQUIPMENT_TYPES = [
 { id: 'treadmill', name: 'Treadmill', defaultWidth: 2, defaultHeight: 1.5, color: 'var(--color-brand-blue)' },
 { id: 'bike', name: 'Exercise Bike', defaultWidth: 1, defaultHeight: 1.5, color: 'var(--color-brand-blue-alt)' },
 { id: 'crosstrainer', name: 'Cross Trainer', defaultWidth: 1.5, defaultHeight: 1.5, color: 'var(--color-blue-500)' },
 { id: 'rower', name: 'Rowing Machine', defaultWidth: 2.5, defaultHeight: 1, color: '#00AAFF' },
 { id: 'bench', name: 'Weight Bench', defaultWidth: 1.5, defaultHeight: 1, color: '#5599FF' },
 { id: 'rack', name: 'Power Rack', defaultWidth: 2, defaultHeight: 2, color: '#0066CC' },
 { id: 'smith', name: 'Smith Machine', defaultWidth: 1.5, defaultHeight: 2, color: '#0055AA' },
 { id: 'cable', name: 'Cable Machine', defaultWidth: 1.5, defaultHeight: 2, color: '#0077DD' },
];

const EquipmentLibrary = ({ onSelectEquipment }) => {
 return (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid="equipment-library">
 <h3 className="text-lg font-semibold text-white mb-4">Equipment Library</h3>
 <div className="grid grid-cols-2 gap-3">
 {EQUIPMENT_TYPES.map(equip => (
 <button
 key={equip.id}
 onClick={() => onSelectEquipment(equip)}
 className="flex flex-col items-center p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg hover:border-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.1)] transition-all duration-300 cursor-pointer"
 data-testid={`equipment-type-${equip.id}`}
 >
 <div 
 className="w-12 h-12 rounded-lg flex items-center justify-center mb-2"
 style={{ backgroundColor: `${equip.color}20` }}
 >
 <GymIcon type={equip.id} size={28} color={equip.color} />
 </div>
 <span className="text-white text-sm text-center">{equip.name}</span>
 </button>
 ))}
 </div>
 <div className="mt-4 p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <p className="text-[var(--color-text-muted)] text-xs">Click equipment to add to your gym floor plan</p>
 </div>
 </Card>
 );
};

export default EquipmentLibrary;
export { EQUIPMENT_TYPES, GymIcon };
