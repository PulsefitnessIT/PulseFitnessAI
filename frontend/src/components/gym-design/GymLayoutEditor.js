import React, { useState, useRef, useEffect } from 'react';
import { Stage, Layer, Rect, Text, Circle, Group, Line, Image as KonvaImage } from 'react-konva';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ZoomIn, ZoomOut, Save, Trash2 } from 'lucide-react';
import { EQUIPMENT_TYPES } from './EquipmentLibrary';

const PIXELS_PER_METER = 40;

const FloorPlanImage = ({ url, width, height }) => {
 const [image, setImage] = useState(null);
 useEffect(() => {
 if (!url) { setImage(null); return; }
 const img = new window.Image();
 // Don't set crossOrigin for blob URLs — they don't need CORS
 if (!url.startsWith('blob:')) {
 img.crossOrigin = 'anonymous';
 }
 img.onload = () => setImage(img);
 img.onerror = () => {
 console.warn('Floor plan image failed to load:', url);
 setImage(null);
 };
 img.src = url;
 }, [url]);
 if (!image) return null;
 return <KonvaImage image={image} x={0} y={0} width={width} height={height} opacity={0.4} />;
};

const GymLayoutEditor = ({ 
 gymLength, 
 gymWidth, 
 equipment, 
 onSave, 
 onEquipmentClick,
 allEquipmentData,
 floorPlanUrl,
 onPositionsChanged,
 equipmentTypes: externalTypes
}) => {
 // Merge external types (from GymDesignTab wizard) with library types for color lookup
 const allTypes = externalTypes || EQUIPMENT_TYPES;
 const [items, setItems] = useState([]);
 const [selectedId, setSelectedId] = useState(null);
 const [scale, setScale] = useState(1);
 const [showEquipmentDialog, setShowEquipmentDialog] = useState(false);
 const [selectedEquipmentData, setSelectedEquipmentData] = useState(null);
 const stageRef = useRef(null);

 useEffect(() => {
 if (equipment && equipment.length > 0) {
 setItems(equipment);
 }
 }, [equipment]);

 const handleDragEnd = (e, id) => {
 const newItems = items.map(item => {
 if (item.id === id) {
 const halfW = (item.width || 2) / 2;
 const halfH = (item.height || 1) / 2;
 return {
 ...item,
 x: e.target.x() / PIXELS_PER_METER - halfW,
 y: e.target.y() / PIXELS_PER_METER - halfH
 };
 }
 return item;
 });
 setItems(newItems);
 if (onPositionsChanged) onPositionsChanged(newItems);
 };

 const handleEquipmentClick = (item) => {
 setSelectedId(item.id);
 if (onEquipmentClick && item.equipment_id) {
 // Find equipment data
 const equipData = allEquipmentData?.find(e => e.id === item.equipment_id);
 if (equipData) {
 setSelectedEquipmentData(equipData);
 setShowEquipmentDialog(true);
 }
 }
 };

 const handleDelete = () => {
 const newItems = items.filter(item => item.id !== selectedId);
 setItems(newItems);
 setSelectedId(null);
 if (onPositionsChanged) onPositionsChanged(newItems);
 };

 const handleSave = () => {
 onSave(items);
 };

 const handleZoomIn = () => {
 setScale(Math.min(scale * 1.2, 3));
 };

 const handleZoomOut = () => {
 setScale(Math.max(scale / 1.2, 0.3));
 };

 const stageWidth = (gymLength || 20) * PIXELS_PER_METER;
 const stageHeight = (gymWidth || 15) * PIXELS_PER_METER;

 return (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid="gym-layout-editor">
 <div className="flex items-center justify-between mb-4">
 <h3 className="text-lg font-semibold text-white">Gym Floor Plan</h3>
 <div className="flex items-center space-x-2">
 <Button 
 size="sm" 
 variant="outline" 
 className="border-white/10 text-white"
 onClick={handleZoomOut}
 data-testid="zoom-out-btn"
 >
 <ZoomOut size={16} />
 </Button>
 <span className="text-white text-sm">{Math.round(scale * 100)}%</span>
 <Button 
 size="sm" 
 variant="outline" 
 className="border-white/10 text-white"
 onClick={handleZoomIn}
 data-testid="zoom-in-btn"
 >
 <ZoomIn size={16} />
 </Button>
 {selectedId && (
 <Button 
 size="sm" 
 variant="outline" 
 className="border-red-500 text-red-500 hover:bg-red-500/10"
 onClick={handleDelete}
 data-testid="delete-equipment-btn"
 >
 <Trash2 size={16} />
 </Button>
 )}
 <Button 
 size="sm" 
 className=""
 onClick={handleSave}
 data-testid="save-layout-btn"
 >
 <Save size={16} className="mr-1" /> Save Layout
 </Button>
 </div>
 </div>

 <div className="bg-[var(--color-ink-alt)] border border-white/10 rounded-lg p-4 overflow-auto" style={{ maxHeight: '600px' }}>
 <Stage
 ref={stageRef}
 width={stageWidth}
 height={stageHeight}
 scaleX={scale}
 scaleY={scale}
 data-testid="gym-canvas"
 >
 <Layer>
 {/* Floor */}
 <Rect
 x={0}
 y={0}
 width={stageWidth}
 height={stageHeight}
 fill="var(--color-surface-dark-2)"
 stroke="#333"
 strokeWidth={2}
 />

 {/* Floor Plan Background */}
 {floorPlanUrl && <FloorPlanImage url={floorPlanUrl} width={stageWidth} height={stageHeight} />}

 {/* Grid */}
 {Array.from({ length: Math.ceil(gymLength || 20) }).map((_, i) => (
 <Line
 key={`v-${i}`}
 points={[i * PIXELS_PER_METER, 0, i * PIXELS_PER_METER, stageHeight]}
 stroke="var(--color-surface-dark-4)"
 strokeWidth={1}
 />
 ))}
 {Array.from({ length: Math.ceil(gymWidth || 15) }).map((_, i) => (
 <Line
 key={`h-${i}`}
 points={[0, i * PIXELS_PER_METER, stageWidth, i * PIXELS_PER_METER]}
 stroke="var(--color-surface-dark-4)"
 strokeWidth={1}
 />
 ))}

 {/* Equipment */}
 {items.map((item, idx) => {
 const equipType = allTypes.find(e => e.id === item.type);
 const isSelected = item.id === selectedId;
 const w = (item.width || equipType?.defaultWidth || 2) * PIXELS_PER_METER;
 const h = (item.height || equipType?.defaultHeight || 1) * PIXELS_PER_METER;
 const halfW = w / 2;
 const halfH = h / 2;
 const label = String(idx + 1);
 const fontSize = Math.min(w, h) > 30 ? 14 : 10;
 return (
 <Group
 key={item.id}
 x={(item.x || 0) * PIXELS_PER_METER + halfW}
 y={(item.y || 0) * PIXELS_PER_METER + halfH}
 rotation={item.rotation || 0}
 offsetX={halfW}
 offsetY={halfH}
 draggable
 onDragEnd={(e) => handleDragEnd(e, item.id)}
 onClick={() => handleEquipmentClick(item)}
 onTap={() => handleEquipmentClick(item)}
 >
 <Rect
 width={w}
 height={h}
 fill={equipType?.color || 'var(--color-brand-blue)'}
 opacity={0.7}
 cornerRadius={4}
 stroke={isSelected ? 'var(--color-white)' : equipType?.color || 'var(--color-brand-blue)'}
 strokeWidth={isSelected ? 3 : 1}
 />
 <Text
 text={label}
 fontSize={fontSize}
 fontStyle="bold"
 fill="white"
 width={w}
 height={h}
 align="center"
 verticalAlign="middle"
 />
 </Group>
 );
 })}
 </Layer>
 </Stage>
 </div>

 {/* Equipment Legend */}
 {items.length > 0 && (
 <div className="mt-3 p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10" data-testid="equipment-legend">
 <p className="text-[var(--color-text-muted)] text-xs font-medium mb-2">Equipment Key</p>
 <div className="flex flex-wrap gap-x-4 gap-y-1">
 {items.map((item, idx) => {
 const equipType = allTypes.find(e => e.id === item.type);
 return (
 <div key={item.id} className="flex items-center gap-1.5 text-xs">
 <div className="w-4 h-4 rounded-sm flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0" style={{ backgroundColor: equipType?.color || 'var(--color-brand-blue)' }}>
 {idx + 1}
 </div>
 <span className="text-white truncate max-w-40">{item.name || equipType?.name || 'Equipment'}</span>
 </div>
 );
 })}
 </div>
 </div>
 )}

 <div className="mt-3 flex items-center justify-between">
 <div className="text-[var(--color-text-muted)] text-sm">
 Gym Size: {gymLength || 20}m x {gymWidth || 15}m | Equipment: {items.length}
 </div>
 </div>

 {/* Equipment Details Dialog */}
 <Dialog open={showEquipmentDialog} onOpenChange={setShowEquipmentDialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white max-w-2xl" data-testid="equipment-details-dialog">
 <DialogHeader>
 <DialogTitle className="text-white">{selectedEquipmentData?.name}</DialogTitle>
 </DialogHeader>
 {selectedEquipmentData && (
 <div className="space-y-4">
 <div className="grid grid-cols-2 gap-4">
 <div>
 <Label className="text-[var(--color-text-muted)]">Type</Label>
 <p className="text-white">{selectedEquipmentData.equipment_type}</p>
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)]">Manufacturer</Label>
 <p className="text-white">{selectedEquipmentData.manufacturer || 'N/A'}</p>
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)]">Model</Label>
 <p className="text-white">{selectedEquipmentData.model || 'N/A'}</p>
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)]">Serial Number</Label>
 <p className="text-white">{selectedEquipmentData.serial_number || 'N/A'}</p>
 </div>
 </div>

 {selectedEquipmentData.stats && (
 <div className="border-t border-white/10 pt-4">
 <h4 className="text-white font-semibold mb-3">Statistics</h4>
 <div className="grid grid-cols-3 gap-4">
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Total Issues</Label>
 <p className="text-white text-lg font-bold">{selectedEquipmentData.stats.total_issues || 0}</p>
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Open Issues</Label>
 <p className="text-white text-lg font-bold">{selectedEquipmentData.stats.open_issues || 0}</p>
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Audits</Label>
 <p className="text-white text-lg font-bold">{selectedEquipmentData.stats.total_audits || 0}</p>
 </div>
 </div>
 </div>
 )}

 <div className="flex space-x-2">
 <Button 
 onClick={() => window.open(`/dashboard?tab=issues&equipment=${selectedEquipmentData.id}`, '_self')}
 className="flex-1"
 data-testid="log-issue-from-layout"
 >
 Log Issue
 </Button>
 <Button 
 onClick={() => window.open(`/dashboard?tab=equipment&id=${selectedEquipmentData.id}`, '_self')}
 variant="outline"
 className="border-white/10 text-white flex-1"
 data-testid="view-details-btn"
 >
 View Full Details
 </Button>
 </div>
 </div>
 )}
 </DialogContent>
 </Dialog>
 </Card>
 );
};

export default GymLayoutEditor;
export { PIXELS_PER_METER };