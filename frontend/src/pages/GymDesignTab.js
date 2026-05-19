import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { Plus, Layout as LayoutIcon, FileImage, Upload, X, Trash2, Loader2, Sparkles, Grid3X3, Image as ImageIcon, MousePointerClick, Pencil, RotateCw, RotateCcw, ZoomIn, ZoomOut, Package } from 'lucide-react';
import GymLayoutEditor from '../components/gym-design/GymLayoutEditor';

const EQUIPMENT_TYPES = [
  { id: 'treadmill', name: 'Treadmill', width: 2.0, height: 0.8, color: '#FF6B6B' },
  { id: 'exercise_bike', name: 'Exercise Bike', width: 1.2, height: 0.6, color: '#4ECDC4' },
  { id: 'cross_trainer', name: 'Cross Trainer', width: 2.0, height: 0.8, color: '#45B7D1' },
  { id: 'rowing_machine', name: 'Rowing Machine', width: 2.5, height: 0.6, color: '#96CEB4' },
  { id: 'cable_machine', name: 'Cable Machine', width: 2.0, height: 1.5, color: '#FFEAA7' },
  { id: 'smith_machine', name: 'Smith Machine', width: 2.0, height: 1.5, color: '#DDA0DD' },
  { id: 'leg_press', name: 'Leg Press', width: 2.0, height: 1.2, color: '#98D8C8' },
  { id: 'lat_pulldown', name: 'Lat Pulldown', width: 1.5, height: 1.2, color: '#F7DC6F' },
  { id: 'bench_press', name: 'Bench Press', width: 2.0, height: 1.2, color: '#BB8FCE' },
  { id: 'squat_rack', name: 'Squat Rack', width: 2.0, height: 1.5, color: '#F1948A' },
  { id: 'dumbbell_rack', name: 'Dumbbell Rack', width: 3.0, height: 0.8, color: '#82E0AA' },
  { id: 'functional_rig', name: 'Functional Training Rig', width: 4.0, height: 2.0, color: '#AED6F1' },
  { id: 'spin_bike', name: 'Spin Bike', width: 1.2, height: 0.6, color: '#F5B041' },
  { id: 'stair_climber', name: 'Stair Climber', width: 1.5, height: 0.8, color: '#D7BDE2' },
  { id: 'free_weights', name: 'Free Weights Area', width: 3.0, height: 3.0, color: '#A3E4D7' },
];

function mapTypeNameToId(name) {
  const lower = name.toLowerCase();
  const match = EQUIPMENT_TYPES.find(e => lower.includes(e.name.toLowerCase()) || e.name.toLowerCase().includes(lower));
  if (match) return match.id;
  if (lower.includes('treadmill')) return 'treadmill';
  if (lower.includes('bike') || lower.includes('cycle')) return 'exercise_bike';
  if (lower.includes('cross') || lower.includes('elliptical')) return 'cross_trainer';
  if (lower.includes('row')) return 'rowing_machine';
  if (lower.includes('cable')) return 'cable_machine';
  if (lower.includes('smith')) return 'smith_machine';
  if (lower.includes('leg')) return 'leg_press';
  if (lower.includes('lat') || lower.includes('pulldown')) return 'lat_pulldown';
  if (lower.includes('bench')) return 'bench_press';
  if (lower.includes('squat') || lower.includes('rack')) return 'squat_rack';
  if (lower.includes('dumbbell')) return 'dumbbell_rack';
  if (lower.includes('functional') || lower.includes('rig')) return 'functional_rig';
  if (lower.includes('spin')) return 'spin_bike';
  if (lower.includes('stair')) return 'stair_climber';
  if (lower.includes('free') || lower.includes('weight')) return 'free_weights';
  return 'treadmill';
}

const GymDesignTab = ({ allEquipment: _onboardedEquipment = [] }) => {
  const { _t } = useTranslation();
  const { API } = useAuth();
  const [layouts, setLayouts] = useState([]);
  const [currentLayout, setCurrentLayout] = useState(null);
  const [equipment, setEquipment] = useState([]);
  const [allEquipment, setAllEquipment] = useState([]);
  const [floorPlanUrl, setFloorPlanUrl] = useState(null);
  const [floorPlanBlobUrl, setFloorPlanBlobUrl] = useState(null);

  // Wizard state
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardMethod, setWizardMethod] = useState(null); // 'upload' or 'scratch'
  const [wizardName, setWizardName] = useState('');
  const [wizardLength, setWizardLength] = useState(20);
  const [wizardWidth, setWizardWidth] = useState(15);
  const [wizardFile, setWizardFile] = useState(null);
  const [wizardUploading, setWizardUploading] = useState(false);
  const [wizardFloorPlanUrl, setWizardFloorPlanUrl] = useState(null);
  const [wizardFloorPlanBlobUrl, setWizardFloorPlanBlobUrl] = useState(null);
  const [wizardDetecting, setWizardDetecting] = useState(false);
  const [wizardDetectedEquipment, setWizardDetectedEquipment] = useState([]);
  const [wizardDetectionNotes, setWizardDetectionNotes] = useState('');
  const [wizardActiveType, setWizardActiveType] = useState(null);
  const [wizardActiveEquipment, setWizardActiveEquipment] = useState(null); // for placing imported equipment
  const [wizardEditingIdx, setWizardEditingIdx] = useState(null);
  const [wizardZoom, setWizardZoom] = useState(1);
  const [wizardSelectedMarker, setWizardSelectedMarker] = useState(null);
  const [wizardPaletteTab, setWizardPaletteTab] = useState('types'); // 'types' or 'inventory'
  const [wizardDragging, setWizardDragging] = useState(null); // { idx, startX, startY }
  const [wizardSnapToGrid, setWizardSnapToGrid] = useState(true);
  const [wizardGridSize, setWizardGridSize] = useState(0.5); // meters
  const wizardImgRef = useRef(null);

  // Equipment dialog
  const [selectedEquipmentType, setSelectedEquipmentType] = useState(null);
  const [showEquipmentDialog, setShowEquipmentDialog] = useState(false);
  const [equipmentForm, setEquipmentForm] = useState({ name: '', manufacturer: '', model: '', serial_number: '', length: 2, width: 0.8 });
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importUploading, setImportUploading] = useState(false);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    const token = localStorage.getItem('token');
    try {
      const [layoutsRes, equipmentRes] = await Promise.all([
        axios.get(`${API}/gym-layouts`, { headers: { Authorization: `Bearer ${token}` } }),
        axios.get(`${API}/equipment`, { headers: { Authorization: `Bearer ${token}` } })
      ]);
      setLayouts(layoutsRes.data.layouts || []);
      setAllEquipment(equipmentRes.data.equipment || []);
      if (layoutsRes.data.layouts && layoutsRes.data.layouts.length > 0) {
        const first = layoutsRes.data.layouts[0];
        setCurrentLayout(first);
        setEquipment(first.equipment_positions || []);
        if (first.floor_plan_url) {
          setFloorPlanUrl(first.floor_plan_url);
          loadFloorPlanBlob(first.floor_plan_url);
        }
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  };

  const loadFloorPlanBlob = async (url) => {
    if (!url) { setFloorPlanBlobUrl(null); return; }
    const token = localStorage.getItem('token');
    try {
      const fileId = url.includes('/files/') ? url.split('/files/').pop()?.split('?')[0] : null;
      let fetchUrl;
      if (fileId) {
        fetchUrl = `${API}/files/${fileId}`;
      } else if (url.startsWith('http') || url.startsWith('blob:')) {
        fetchUrl = url;
      } else {
        // Old-format storage path — look up file by download_url match
        try {
          const listRes = await fetch(`${API}/files/list`, { headers: { Authorization: `Bearer ${token}` } });
          if (listRes.ok) {
            const listData = await listRes.json();
            const match = (listData.files || []).find(f => f.download_url === url || f.storage_path === url);
            if (match) {
              fetchUrl = `${API}/files/${match.id}`;
            }
          }
        } catch {}
        if (!fetchUrl) {
          fetchUrl = url.startsWith('/') ? `${API}${url}` : `${API}/${url}`;
        }
      }

      const response = await fetch(fetchUrl, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) {
        setFloorPlanBlobUrl(null);
        return;
      }
      const blob = await response.blob();
      if (floorPlanBlobUrl) URL.revokeObjectURL(floorPlanBlobUrl);
      setFloorPlanBlobUrl(URL.createObjectURL(blob));
    } catch {
      setFloorPlanBlobUrl(null);
    }
  };

  // === WIZARD HANDLERS ===
  const resetWizard = () => {
    setWizardStep(0);
    setWizardMethod(null);
    setWizardName('');
    setWizardLength(20);
    setWizardWidth(15);
    setWizardFile(null);
    setWizardUploading(false);
    setWizardFloorPlanUrl(null);
    if (wizardFloorPlanBlobUrl) URL.revokeObjectURL(wizardFloorPlanBlobUrl);
    setWizardFloorPlanBlobUrl(null);
    setWizardDetecting(false);
    setWizardDetectedEquipment([]);
    setWizardDetectionNotes('');
    setWizardActiveType(null);
    setWizardActiveEquipment(null);
    setWizardEditingIdx(null);
    setWizardZoom(1);
    setWizardSelectedMarker(null);
    setWizardPaletteTab('types');
    setWizardSnapToGrid(true);
    setWizardGridSize(0.5);
  };

  const handleWizardUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setWizardFile(file);
    setWizardUploading(true);
    const token = localStorage.getItem('token');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post(`${API}/files/upload?category=floor-plans`, formData, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
      });
      const fileId = res.data.id;
      const url = fileId ? `/api/files/${fileId}` : res.data.download_url;
      setWizardFloorPlanUrl(url);
      // Create blob URL using fetch API
      if (fileId) {
        const fileRes = await fetch(`${API}/files/${fileId}`, { headers: { Authorization: `Bearer ${token}` } });
        if (fileRes.ok) {
          const blob = await fileRes.blob();
          setWizardFloorPlanBlobUrl(URL.createObjectURL(blob));
        }
      }
      notify.success('Floor plan uploaded');
    } catch {
      notify.error('Failed to upload floor plan');
      setWizardFile(null);
    } finally {
      setWizardUploading(false);
      e.target.value = '';
    }
  };

  const handleDetectEquipment = async () => {
    if (!wizardFile && !wizardFloorPlanUrl) return;
    setWizardDetecting(true);
    const token = localStorage.getItem('token');
    try {
      let fileToSend = wizardFile;
      if (!fileToSend && wizardFloorPlanBlobUrl) {
        const res = await fetch(wizardFloorPlanBlobUrl);
        const blob = await res.blob();
        fileToSend = new File([blob], 'floorplan.png', { type: blob.type });
      }
      if (!fileToSend) {
        notify.error('No file available for detection');
        setWizardDetecting(false);
        return;
      }
      const formData = new FormData();
      formData.append('file', fileToSend);
      // Include existing placements as hints for AI
      if (wizardDetectedEquipment.length > 0) {
        formData.append('annotations', JSON.stringify(wizardDetectedEquipment.map(a => ({
          name: a.name, type: a.type,
          x_percent: a.x_percent, y_percent: a.y_percent
        }))));
      }
      const res = await axios.post(`${API}/gym-layouts/detect-equipment`, formData, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
        timeout: 60000
      });
      const detected = res.data.equipment || [];
      // Merge: keep existing manual placements + add new AI-detected ones that don't overlap
      const existing = [...wizardDetectedEquipment];
      let added = 0;
      detected.forEach(d => {
        const overlaps = existing.some(e =>
          Math.abs(e.x_percent - d.x_percent) < 6 && Math.abs(e.y_percent - d.y_percent) < 6
        );
        if (!overlaps) {
          existing.push(d);
          added++;
        }
      });
      setWizardDetectedEquipment(existing);
      setWizardDetectionNotes(res.data.notes || '');
      notify.success(`AI found ${added} additional pieces of equipment`);
    } catch {
      notify.error('AI detection failed — continue placing equipment manually');
    } finally {
      setWizardDetecting(false);
    }
  };

  // Gym dimensions used for coordinate mapping (upload = 30×20, scratch = user-defined)
  const gymLengthForCalc = wizardMethod === 'upload' ? 30 : wizardLength;
  const gymWidthForCalc = wizardMethod === 'upload' ? 20 : wizardWidth;

  // Snap a percent value to the nearest grid line (in meters, converted to %)
  const snapPercent = (pct, axis) => {
    if (!wizardSnapToGrid) return pct;
    const totalM = axis === 'x' ? gymLengthForCalc : gymWidthForCalc;
    const meters = (pct / 100) * totalM;
    const snapped = Math.round(meters / wizardGridSize) * wizardGridSize;
    return Math.max(0, Math.min(100, +(snapped / totalM * 100).toFixed(2)));
  };

  // Click handler for placing equipment on the floor plan
  const handleFloorPlanClick = (e) => {
    // Don't place if we just finished dragging
    if (wizardDragging) return;
    if (!wizardActiveType && !wizardActiveEquipment) {
      setWizardSelectedMarker(null);
      return;
    }
    setWizardSelectedMarker(null);
    const img = e.currentTarget.querySelector('img');
    if (!img) return;
    const rect = img.getBoundingClientRect();
    let x_percent = Math.max(0, Math.min(100, +((e.clientX - rect.left) / rect.width * 100).toFixed(2)));
    let y_percent = Math.max(0, Math.min(100, +((e.clientY - rect.top) / rect.height * 100).toFixed(2)));
    x_percent = snapPercent(x_percent, 'x');
    y_percent = snapPercent(y_percent, 'y');

    if (wizardActiveEquipment) {
      // Placing from imported equipment inventory
      const eq = wizardActiveEquipment;
      const typeId = mapTypeNameToId(eq.equipment_type || eq.name);
      const typeInfo = EQUIPMENT_TYPES.find(t => t.id === typeId);
      const countOfType = wizardDetectedEquipment.filter(d => d.equipment_id === eq.id).length;
      setWizardDetectedEquipment(prev => [...prev, {
        type: typeInfo?.name || eq.equipment_type || eq.name,
        name: countOfType > 0 ? `${eq.name} (${countOfType + 1})` : eq.name,
        x_percent, y_percent,
        width_m: typeInfo?.width || 2.0,
        length_m: typeInfo?.height || 1.0,
        equipment_id: eq.id,
        serial_number: eq.serial_number
      }]);
      notify.success(`Placed ${eq.name}`);
    } else if (wizardActiveType) {
      // Placing from generic type palette
      const typeInfo = EQUIPMENT_TYPES.find(t => t.id === wizardActiveType);
      const countOfType = wizardDetectedEquipment.filter(d => mapTypeNameToId(d.type || d.name) === wizardActiveType).length;
      setWizardDetectedEquipment(prev => [...prev, {
        type: typeInfo?.name || wizardActiveType,
        name: `${typeInfo?.name || wizardActiveType} ${countOfType + 1}`,
        x_percent, y_percent,
        width_m: typeInfo?.width || 2.0,
        length_m: typeInfo?.height || 1.0
      }]);
      notify.success(`Placed ${typeInfo?.name} ${countOfType + 1}`);
    }
    // Keep the active type selected for rapid multi-placement (don't clear it)
  };

  const handleRemoveDetected = (idx) => {
    setWizardDetectedEquipment(prev => prev.filter((_, i) => i !== idx));
  };

  const handleEditDetectedName = (idx, newName) => {
    setWizardDetectedEquipment(prev => prev.map((eq, i) => i === idx ? { ...eq, name: newName } : eq));
  };

  // Markers to display on the floor plan image (proportionally correct to gym dimensions)
  const floorPlanMarkers = wizardDetectedEquipment.map(eq => {
    const typeInfo = EQUIPMENT_TYPES.find(t => t.id === mapTypeNameToId(eq.type || eq.name));
    const wM = eq.width_m || typeInfo?.width || 2;
    const hM = eq.length_m || typeInfo?.height || 1;
    return {
      x_percent: eq.x_percent,
      y_percent: eq.y_percent,
      color: (typeInfo || {}).color || 'var(--color-brand-blue)',
      name: eq.name || eq.type,
      width_pct: Math.max(1.5, (wM / gymLengthForCalc) * 100),
      height_pct: Math.max(1.5, (hM / gymWidthForCalc) * 100),
      rotation: eq.rotation || 0,
      width_m: wM,
      height_m: hM
    };
  });


  const handleRotateMarker = (degrees) => {
    if (wizardSelectedMarker === null) return;
    setWizardDetectedEquipment(prev => prev.map((eq, i) =>
      i === wizardSelectedMarker ? { ...eq, rotation: ((eq.rotation || 0) + degrees + 360) % 360 } : eq
    ));
  };

  const handleDeleteSelectedMarker = () => {
    if (wizardSelectedMarker === null) return;
    handleRemoveDetected(wizardSelectedMarker);
    setWizardSelectedMarker(null);
  };

  // Drag handler for repositioning markers on the floor plan
  const handleMarkerDragStart = (e, idx) => {
    e.preventDefault();
    e.stopPropagation();
    // Record start position to distinguish click from drag
    setWizardDragging({ idx, startX: e.clientX, startY: e.clientY, hasMoved: false });
  };

  const handleMarkerDragMove = useCallback((e) => {
    if (wizardDragging === null) return;
    const dx = Math.abs(e.clientX - wizardDragging.startX);
    const dy = Math.abs(e.clientY - wizardDragging.startY);
    // Only start actual movement after 4px threshold (prevents accidental drags on click)
    if (!wizardDragging.hasMoved && dx < 4 && dy < 4) return;
    if (!wizardDragging.hasMoved) {
      setWizardDragging(prev => prev ? { ...prev, hasMoved: true } : null);
    }
    const img = wizardImgRef.current;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    let x_percent = Math.max(0, Math.min(100, +((e.clientX - rect.left) / rect.width * 100).toFixed(2)));
    let y_percent = Math.max(0, Math.min(100, +((e.clientY - rect.top) / rect.height * 100).toFixed(2)));
    x_percent = snapPercent(x_percent, 'x');
    y_percent = snapPercent(y_percent, 'y');
    setWizardDetectedEquipment(prev => prev.map((eq, i) =>
      i === wizardDragging.idx ? { ...eq, x_percent, y_percent } : eq
    ));
  // eslint-disable-next-line react-hooks/exhaustive-deps -- deferred: keep current behaviour; revisit if 'snapPercent' ever captures state that needs to re-trigger the hook. Pre-existing since iter 216h226-polish-5.
  }, [wizardDragging, wizardSnapToGrid, wizardGridSize, gymLengthForCalc, gymWidthForCalc]);

  const handleMarkerDragEnd = useCallback(() => {
    if (wizardDragging && !wizardDragging.hasMoved) {
      // It was a click, not a drag — toggle selection
      setWizardSelectedMarker(prev => prev === wizardDragging.idx ? null : wizardDragging.idx);
    } else if (wizardDragging?.hasMoved) {
      setWizardSelectedMarker(wizardDragging.idx);
    }
    setWizardDragging(null);
  }, [wizardDragging]);

  useEffect(() => {
    if (wizardDragging !== null) {
      window.addEventListener('mousemove', handleMarkerDragMove);
      window.addEventListener('mouseup', handleMarkerDragEnd);
      return () => {
        window.removeEventListener('mousemove', handleMarkerDragMove);
        window.removeEventListener('mouseup', handleMarkerDragEnd);
      };
    }
  }, [wizardDragging, handleMarkerDragMove, handleMarkerDragEnd]);

  // Arrow-key nudging for selected marker (0.1% per press, 0.01% with Shift for micro-adjustment)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (wizardSelectedMarker === null) return;
      const arrows = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
      if (!arrows.includes(e.key)) return;
      // Don't nudge if user is typing in an input
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      e.preventDefault();
      const step = e.shiftKey ? 0.01 : 0.1;
      setWizardDetectedEquipment(prev => prev.map((eq, i) => {
        if (i !== wizardSelectedMarker) return eq;
        let { x_percent, y_percent } = eq;
        if (e.key === 'ArrowLeft') x_percent = Math.max(0, +(x_percent - step).toFixed(2));
        if (e.key === 'ArrowRight') x_percent = Math.min(100, +(x_percent + step).toFixed(2));
        if (e.key === 'ArrowUp') y_percent = Math.max(0, +(y_percent - step).toFixed(2));
        if (e.key === 'ArrowDown') y_percent = Math.min(100, +(y_percent + step).toFixed(2));
        return { ...eq, x_percent, y_percent };
      }));
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [wizardSelectedMarker]);


  // Dimension editing for a placed equipment item
  const handleUpdateDimension = (idx, field, value) => {
    const num = parseFloat(value);
    if (isNaN(num) || num <= 0) return;
    setWizardDetectedEquipment(prev => prev.map((eq, i) =>
      i === idx ? { ...eq, [field]: num } : eq
    ));
  };


  const handleWizardComplete = async () => {
    if (!wizardName) { notify.error('Enter a layout name'); return; }
    const token = localStorage.getItem('token');

    // For upload method, use a default canvas size that matches common gym proportions
    const length = wizardMethod === 'upload' ? 30 : wizardLength;
    const width = wizardMethod === 'upload' ? 20 : wizardWidth;

    // Convert placed equipment to canvas positions
    // Wizard stores x_percent/y_percent as CENTER of marker (CSS translate(-50%,-50%))
    // Editor expects item.x/y as TOP-LEFT corner in meters — so subtract half the equipment size
    let positions = [];
    if (wizardDetectedEquipment.length > 0) {
      positions = wizardDetectedEquipment.map((eq, idx) => {
        const typeId = mapTypeNameToId(eq.type || eq.name);
        const eqType = EQUIPMENT_TYPES.find(t => t.id === typeId) || EQUIPMENT_TYPES[0];
        const eqWidth = eq.width_m || eqType.width;
        const eqHeight = eq.length_m || eqType.height;
        return {
          id: `eq-${Date.now()}-${idx}`,
          type: typeId,
          name: eq.name || `${eq.type} ${idx + 1}`,
          x: Math.max(0, (eq.x_percent / 100) * length - eqWidth / 2),
          y: Math.max(0, (eq.y_percent / 100) * width - eqHeight / 2),
          width: eqWidth,
          height: eqHeight,
          rotation: eq.rotation || 0,
          equipment_id: eq.equipment_id || null,
          serial_number: eq.serial_number || null
        };
      });
    }

    try {
      const layoutData = {
        name: wizardName,
        gym_length: length,
        gym_width: width,
        equipment_positions: positions,
        floor_plan_url: wizardFloorPlanUrl
      };
      const res = await axios.post(`${API}/gym-layouts`, layoutData, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const newLayout = res.data;
      setLayouts([newLayout, ...layouts]);
      setCurrentLayout(newLayout);
      setEquipment(positions);
      
      // Transfer floor plan to the main state BEFORE resetting wizard
      // Save blob URL reference before reset clears it
      const savedBlobUrl = wizardFloorPlanBlobUrl;
      const savedFloorPlanUrl = wizardFloorPlanUrl;
      
      setShowWizard(false);
      // Reset wizard state but DON'T revoke the blob URL since we're transferring it
      setWizardStep(0);
      setWizardMethod(null);
      setWizardName('');
      setWizardLength(20);
      setWizardWidth(15);
      setWizardFile(null);
      setWizardUploading(false);
      setWizardFloorPlanUrl(null);
      setWizardFloorPlanBlobUrl(null);
      setWizardDetecting(false);
      setWizardDetectedEquipment([]);
      setWizardDetectionNotes('');
      
      // Now set the main floor plan state with the saved references
      if (savedFloorPlanUrl) {
        setFloorPlanUrl(savedFloorPlanUrl);
        if (savedBlobUrl) {
          // Revoke old main blob URL if different
          if (floorPlanBlobUrl && floorPlanBlobUrl !== savedBlobUrl) {
            URL.revokeObjectURL(floorPlanBlobUrl);
          }
          setFloorPlanBlobUrl(savedBlobUrl);
        } else {
          loadFloorPlanBlob(savedFloorPlanUrl);
        }
      } else {
        setFloorPlanUrl(null);
        setFloorPlanBlobUrl(null);
      }
      
      notify.success('Layout created!');
    } catch {
      notify.error('Failed to create layout');
    }
  };

  // === EXISTING HANDLERS ===
  const handleDeleteLayout = async () => {
    if (!currentLayout) return;
    const token = localStorage.getItem('token');
    try {
      await axios.delete(`${API}/gym-layouts/${currentLayout.id}`, { headers: { Authorization: `Bearer ${token}` } });
      const remaining = layouts.filter(l => l.id !== currentLayout.id);
      setLayouts(remaining);
      if (remaining.length > 0) {
        setCurrentLayout(remaining[0]);
        setEquipment(remaining[0].equipment_positions || []);
        setFloorPlanUrl(remaining[0].floor_plan_url || null);
        if (remaining[0].floor_plan_url) loadFloorPlanBlob(remaining[0].floor_plan_url);
        else setFloorPlanBlobUrl(null);
      } else {
        setCurrentLayout(null);
        setEquipment([]);
        setFloorPlanUrl(null);
        setFloorPlanBlobUrl(null);
      }
      notify.success('Layout deleted');
    } catch { notify.error('Failed to delete layout'); }
  };

  const handleSaveLayout = async (items) => {
    if (!currentLayout) return;
    const token = localStorage.getItem('token');
    try {
      await axios.patch(`${API}/gym-layouts/${currentLayout.id}`, {
        ...currentLayout,
        equipment_positions: items,
        floor_plan_url: floorPlanUrl
      }, { headers: { Authorization: `Bearer ${token}` } });
      setEquipment(items);
      notify.success('Layout saved!');
    } catch { notify.error('Failed to save layout'); }
  };

  const handleAddEquipment = async (e) => {
    e.preventDefault();
    if (!selectedEquipmentType || !currentLayout) return;
    const token = localStorage.getItem('token');
    try {
      const eqRes = await axios.post(`${API}/equipment`, {
        name: equipmentForm.name,
        equipment_type: selectedEquipmentType.name,
        manufacturer: equipmentForm.manufacturer,
        model: equipmentForm.model,
        serial_number: equipmentForm.serial_number,
        location: `Gym Layout: ${currentLayout.name}`
      }, { headers: { Authorization: `Bearer ${token}` } });

      const newItem = {
        id: `eq-${Date.now()}`,
        type: selectedEquipmentType.id,
        name: equipmentForm.name,
        equipment_id: eqRes.data.id,
        x: 2,
        y: 2,
        width: equipmentForm.length || selectedEquipmentType.width,
        height: equipmentForm.width || selectedEquipmentType.height,
        rotation: 0
      };
      const updated = [...equipment, newItem];
      setEquipment(updated);
      setShowEquipmentDialog(false);
      setEquipmentForm({ name: '', manufacturer: '', model: '', serial_number: '', length: 2, width: 0.8 });
      // Auto-save
      await axios.patch(`${API}/gym-layouts/${currentLayout.id}`, {
        ...currentLayout, equipment_positions: updated, floor_plan_url: floorPlanUrl
      }, { headers: { Authorization: `Bearer ${token}` } });
      notify.success(`${equipmentForm.name || selectedEquipmentType.name} added to layout`);
      loadData();
    } catch { notify.error('Failed to add equipment'); }
  };

  const handleEquipmentClick = (_item) => {};

  const handleFloorPlanUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setImportUploading(true);
    const token = localStorage.getItem('token');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post(`${API}/files/upload?category=floor-plans`, formData, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
      });
      const fileId = res.data.id;
      const url = fileId ? `/api/files/${fileId}` : res.data.download_url;
      setFloorPlanUrl(url);
      if (fileId) {
        const fileRes = await fetch(`${API}/files/${fileId}`, { headers: { Authorization: `Bearer ${token}` } });
        if (fileRes.ok) {
          const blob = await fileRes.blob();
          if (floorPlanBlobUrl) URL.revokeObjectURL(floorPlanBlobUrl);
          setFloorPlanBlobUrl(URL.createObjectURL(blob));
        }
      }
      if (currentLayout) {
        await axios.patch(`${API}/gym-layouts/${currentLayout.id}`, {
          ...currentLayout, floor_plan_url: url, equipment_positions: equipment
        }, { headers: { Authorization: `Bearer ${token}` } });
      }
      setShowImportDialog(false);
      notify.success('Floor plan imported!');
    } catch { notify.error('Failed to upload floor plan'); }
    finally { setImportUploading(false); e.target.value = ''; }
  };

  const handleClearFloorPlan = async () => {
    setFloorPlanUrl(null);
    if (floorPlanBlobUrl) URL.revokeObjectURL(floorPlanBlobUrl);
    setFloorPlanBlobUrl(null);
    if (currentLayout) {
      const token = localStorage.getItem('token');
      await axios.patch(`${API}/gym-layouts/${currentLayout.id}`, {
        ...currentLayout, floor_plan_url: null, equipment_positions: equipment
      }, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    }
    notify.success('Floor plan removed');
  };

  return (
    <div className="space-y-6" data-testid="gym-design-tab">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold text-white">Gym Layouts</h2>
        <div className="flex items-center gap-2">
          {currentLayout && (
            <Button size="sm" variant="outline" className="border-white/10 text-white" onClick={() => setShowImportDialog(true)} data-testid="import-floorplan-btn">
              <FileImage size={14} className="mr-1" /> Import Floor Plan
            </Button>
          )}
          <Button size="sm" className="text-white" style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }} onClick={() => { resetWizard(); setShowWizard(true); }} data-testid="new-layout-btn">
            <Plus size={14} className="mr-1" /> New Layout
          </Button>
        </div>
      </div>

      {/* Layout Selector */}
      {currentLayout && (
        <div className="flex items-center space-x-4 flex-wrap gap-y-2">
          <Label className="text-white">Current Layout:</Label>
          <select
            value={currentLayout.id}
            onChange={(e) => {
              const layout = layouts.find(l => l.id === e.target.value);
              setCurrentLayout(layout);
              setEquipment(layout?.equipment_positions || []);
              setFloorPlanUrl(layout?.floor_plan_url || null);
              if (layout?.floor_plan_url) loadFloorPlanBlob(layout.floor_plan_url);
              else { if (floorPlanBlobUrl) URL.revokeObjectURL(floorPlanBlobUrl); setFloorPlanBlobUrl(null); }
            }}
            className="bg-[var(--theme-surface)] border border-white/10 text-white px-4 py-2 rounded-lg"
            data-testid="layout-selector"
          >
            {layouts.map(layout => (
              <option key={layout.id} value={layout.id}>{layout.name}</option>
            ))}
          </select>
          <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)]">{currentLayout.gym_length}m x {currentLayout.gym_width}m</Badge>
          {floorPlanUrl && (
            <Badge className="bg-green-500/20 text-green-400 cursor-pointer" onClick={handleClearFloorPlan}>
              Floor Plan Active <X size={12} className="ml-1 inline" />
            </Badge>
          )}
          <Button size="sm" variant="outline" className="border-red-500/30 text-red-400 hover:bg-red-500/10" onClick={handleDeleteLayout} data-testid="delete-layout-btn">
            <Trash2 size={14} className="mr-1" /> Delete Layout
          </Button>
        </div>
      )}

      {/* Canvas */}
      {currentLayout ? (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="lg:col-span-3">
            <GymLayoutEditor
              gymLength={currentLayout.gym_length}
              gymWidth={currentLayout.gym_width}
              equipment={equipment}
              onSave={handleSaveLayout}
              onEquipmentClick={handleEquipmentClick}
              allEquipmentData={allEquipment}
              floorPlanUrl={floorPlanBlobUrl || floorPlanUrl}
              onPositionsChanged={(updatedItems) => setEquipment(updatedItems)}
              equipmentTypes={EQUIPMENT_TYPES}
            />
          </div>
          <div>
            <Card className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid="equipment-palette">
              <h3 className="text-white font-semibold mb-3">Add Equipment</h3>
              <p className="text-[var(--color-text-muted)] text-xs mb-3">Click to place on layout</p>
              <div className="space-y-2 max-h-[500px] overflow-y-auto">
                {EQUIPMENT_TYPES.map(type => (
                  <button
                    key={type.id}
                    onClick={() => { setSelectedEquipmentType(type); setShowEquipmentDialog(true); setEquipmentForm({ name: '', manufacturer: '', model: '', serial_number: '', length: type.width, width: type.height }); }}
                    className="w-full flex items-center space-x-3 p-2 rounded-lg hover:bg-white/5 transition-colors text-left"
                    data-testid={`equip-type-${type.id}`}
                  >
                    <div className="w-6 h-4 rounded" style={{ backgroundColor: type.color }} />
                    <span className="text-white text-sm">{type.name}</span>
                  </button>
                ))}
              </div>
            </Card>
          </div>
        </div>
      ) : (
        <Card className="bg-[var(--theme-surface)] border-white/10 p-12 text-center" data-testid="no-layout-placeholder">
          <LayoutIcon size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
          <h3 className="text-white text-lg font-semibold mb-2">No Layouts Yet</h3>
          <p className="text-[var(--color-text-muted)] text-sm mb-4">Create your first gym layout to start placing equipment</p>
          <Button className="text-white" style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }} onClick={() => { resetWizard(); setShowWizard(true); }} data-testid="create-first-layout-btn">
            <Plus size={16} className="mr-2" /> Create Layout
          </Button>
        </Card>
      )}

      {/* === NEW LAYOUT WIZARD === */}
      <Dialog open={showWizard} onOpenChange={(open) => { if (!open) { setShowWizard(false); resetWizard(); } }}>
        <DialogContent className={`bg-[var(--theme-surface)] border-white/10 text-white ${wizardStep === 2 ? 'max-w-4xl' : 'max-w-2xl'} max-h-[85vh] overflow-y-auto`} data-testid="layout-wizard-dialog">
          <DialogHeader>
            <DialogTitle className="text-white">
              {wizardStep === 0 && 'Create New Layout'}
              {wizardStep === 1 && (wizardMethod === 'upload' ? 'Upload Floor Plan' : 'Set Dimensions')}
              {wizardStep === 2 && 'Place Equipment'}
              {wizardStep === 3 && 'Review & Create'}
            </DialogTitle>
          </DialogHeader>

          {/* Step 0: Choose Method */}
          {wizardStep === 0 && (
            <div className="space-y-4" data-testid="wizard-step-method">
              <div>
                <Label className="text-[var(--color-text-muted)] text-sm">Layout Name</Label>
                <Input
                  value={wizardName}
                  onChange={(e) => setWizardName(e.target.value)}
                  placeholder="e.g., Main Gym Floor"
                  className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                  data-testid="wizard-layout-name"
                />
              </div>
              <p className="text-[var(--color-text-muted)] text-sm">How would you like to create this layout?</p>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => { setWizardMethod('upload'); setWizardStep(1); }}
                  className={`p-6 rounded-xl border-2 text-left transition-all hover:border-[rgb(var(--rgb-brand-blue)/0.5)] ${wizardMethod === 'upload' ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.1)]' : 'border-white/10 bg-[var(--color-ink-alt)]'}`}
                  data-testid="wizard-method-upload"
                >
                  <ImageIcon size={32} className="text-[var(--color-brand-blue)] mb-3" />
                  <h4 className="text-white font-semibold mb-1">Upload Floor Plan</h4>
                  <p className="text-[var(--color-text-muted)] text-xs">Upload a PDF or image of your gym. AI will detect equipment positions automatically.</p>
                </button>
                <button
                  onClick={() => { setWizardMethod('scratch'); setWizardStep(1); }}
                  className={`p-6 rounded-xl border-2 text-left transition-all hover:border-[rgb(var(--rgb-brand-blue)/0.5)] ${wizardMethod === 'scratch' ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.1)]' : 'border-white/10 bg-[var(--color-ink-alt)]'}`}
                  data-testid="wizard-method-scratch"
                >
                  <Grid3X3 size={32} className="text-[var(--color-brand-blue)] mb-3" />
                  <h4 className="text-white font-semibold mb-1">Start from Scratch</h4>
                  <p className="text-[var(--color-text-muted)] text-xs">Enter your gym dimensions and place equipment manually on an empty grid.</p>
                </button>
              </div>
            </div>
          )}

          {/* Step 1a: Upload Floor Plan */}
          {wizardStep === 1 && wizardMethod === 'upload' && (
            <div className="space-y-4" data-testid="wizard-step-upload">
              <div className="border-2 border-dashed border-white/20 rounded-xl p-8 text-center hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors">
                {wizardFloorPlanBlobUrl ? (
                  <div>
                    <img src={wizardFloorPlanBlobUrl} alt="Floor plan preview" className="max-h-48 mx-auto rounded-lg mb-3" data-testid="wizard-floor-plan-preview" />
                    <p className="text-green-400 text-sm">{wizardFile?.name || 'Floor plan uploaded'}</p>
                  </div>
                ) : (
                  <>
                    <FileImage size={40} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
                    <p className="text-white mb-1">Drop your floor plan here or click to browse</p>
                    <p className="text-[var(--color-text-muted)] text-xs mb-4">Supports: PDF, PNG, JPG. PDFs are auto-converted to images.</p>
                  </>
                )}
                <label className="cursor-pointer">
                  <input type="file" className="hidden" accept="image/*,.pdf" onChange={handleWizardUpload} data-testid="wizard-file-input" />
                  <Button type="button" size="sm" className="pointer-events-none text-white" style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }}>
                    <Upload size={14} className="mr-1" /> {wizardUploading ? 'Uploading...' : (wizardFloorPlanUrl ? 'Replace File' : 'Choose File')}
                  </Button>
                </label>
              </div>

              <div className="flex justify-between">
                <Button variant="outline" className="border-white/10 text-[var(--color-text-muted)]" onClick={() => setWizardStep(0)} data-testid="wizard-back-btn">Back</Button>
                <Button
                  disabled={!wizardFloorPlanUrl && !wizardFloorPlanBlobUrl}
                  className="text-white"
                  style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }}
                  onClick={() => setWizardStep(2)}
                  data-testid="wizard-next-btn"
                >
                  Next — Place Equipment
                </Button>
              </div>
            </div>
          )}

          {/* Step 1b: Dimensions (scratch) */}
          {wizardStep === 1 && wizardMethod === 'scratch' && (
            <div className="space-y-4" data-testid="wizard-step-dimensions">
              <p className="text-[var(--color-text-muted)] text-sm">Enter the dimensions of your gym floor area in metres.</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-[var(--color-text-muted)] text-sm">Length (m)</Label>
                  <Input type="number" step="0.5" value={wizardLength} onChange={e => setWizardLength(parseFloat(e.target.value) || 20)} className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="wizard-length-input" />
                </div>
                <div>
                  <Label className="text-[var(--color-text-muted)] text-sm">Width (m)</Label>
                  <Input type="number" step="0.5" value={wizardWidth} onChange={e => setWizardWidth(parseFloat(e.target.value) || 15)} className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="wizard-width-input" />
                </div>
              </div>
              <div className="p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
                <p className="text-[var(--color-text-muted)] text-sm">Preview: <span className="text-white font-semibold">{wizardLength}m × {wizardWidth}m</span> ({(wizardLength * wizardWidth).toFixed(0)} m²)</p>
              </div>
              <div className="flex justify-between">
                <Button variant="outline" className="border-white/10 text-[var(--color-text-muted)]" onClick={() => setWizardStep(0)} data-testid="wizard-back-btn">Back</Button>
                <Button className="text-white" style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }} onClick={() => setWizardStep(3)} data-testid="wizard-next-btn">Next — Review</Button>
              </div>
            </div>
          )}

          {/* Step 2: Place Equipment (upload method only) */}
          {wizardStep === 2 && (
            <div className="space-y-3" data-testid="wizard-step-detect">
              {/* Instructions */}
              {!wizardDetecting && (
                <div className="p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
                  <div className="flex items-start gap-3">
                    <MousePointerClick size={18} className="text-[var(--color-brand-blue)] flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-white font-semibold text-sm mb-0.5">Place Your Equipment</h4>
                      <p className="text-[var(--color-text-muted)] text-xs">Select a machine below, then click on the floor plan to place it. <strong className="text-white">Drag</strong> shapes to reposition. Click a shape to set dimensions and rotate.</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Equipment palette — Tabbed: Types | Your Equipment */}
              {!wizardDetecting && (
                <div data-testid="equipment-type-palette">
                  {/* Palette tabs */}
                  <div className="flex gap-1 mb-2">
                    <button
                      onClick={() => { setWizardPaletteTab('types'); setWizardActiveEquipment(null); }}
                      className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${wizardPaletteTab === 'types' ? 'bg-[rgb(var(--rgb-brand-blue)/0.2)] text-white border border-[rgb(var(--rgb-brand-blue)/0.5)]' : 'text-[var(--color-text-muted)] border border-white/10 hover:border-white/20'}`}
                      data-testid="palette-tab-types"
                    >
                      Machine Types
                    </button>
                    <button
                      onClick={() => { setWizardPaletteTab('inventory'); setWizardActiveType(null); }}
                      className={`px-3 py-1 rounded-md text-xs font-medium transition-all flex items-center gap-1.5 ${wizardPaletteTab === 'inventory' ? 'bg-[rgb(var(--rgb-brand-blue)/0.2)] text-white border border-[rgb(var(--rgb-brand-blue)/0.5)]' : 'text-[var(--color-text-muted)] border border-white/10 hover:border-white/20'}`}
                      data-testid="palette-tab-inventory"
                    >
                      <Package size={12} /> Your Equipment ({allEquipment.length})
                    </button>
                  </div>

                  {/* Generic types palette */}
                  {wizardPaletteTab === 'types' && (
                    <div className="flex flex-wrap gap-1.5" data-testid="palette-types-list">
                      {EQUIPMENT_TYPES.map(type => {
                        const isActive = wizardActiveType === type.id;
                        const placedCount = wizardDetectedEquipment.filter(d => mapTypeNameToId(d.type || d.name) === type.id).length;
                        return (
                          <button
                            key={type.id}
                            onClick={() => { setWizardActiveType(isActive ? null : type.id); setWizardActiveEquipment(null); }}
                            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition-all ${
                              isActive ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.2)] text-white ring-1 ring-[var(--color-brand-blue)]' : 'border-white/10 text-[var(--color-text-muted)] hover:border-white/20'
                            }`}
                            data-testid={`palette-type-${type.id}`}
                          >
                            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: type.color }} />
                            <span>{type.name}</span>
                            {placedCount > 0 && <span className="bg-white/20 text-white px-1 rounded text-[10px] font-bold">{placedCount}</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Imported equipment list */}
                  {wizardPaletteTab === 'inventory' && (
                    <div className="space-y-1" data-testid="palette-inventory-list">
                      {allEquipment.length === 0 ? (
                        <p className="text-[var(--color-text-muted)] text-xs py-3 text-center">No equipment imported yet. Add equipment from the Equipment tab first.</p>
                      ) : (
                        <div className="max-h-36 overflow-y-auto space-y-1">
                          {allEquipment.map(eq => {
                            const typeId = mapTypeNameToId(eq.equipment_type || eq.name);
                            const typeInfo = EQUIPMENT_TYPES.find(t => t.id === typeId);
                            const isActive = wizardActiveEquipment?.id === eq.id;
                            const placedCount = wizardDetectedEquipment.filter(d => d.equipment_id === eq.id).length;
                            return (
                              <button
                                key={eq.id}
                                onClick={() => { setWizardActiveEquipment(isActive ? null : eq); setWizardActiveType(null); }}
                                className={`flex items-center gap-2 w-full px-2.5 py-1.5 rounded-lg border text-left text-xs transition-all ${
                                  isActive ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.2)] text-white ring-1 ring-[var(--color-brand-blue)]' : 'border-white/10 text-[var(--color-text-muted)] hover:border-white/20'
                                }`}
                                data-testid={`palette-equip-${eq.id}`}
                              >
                                <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: typeInfo?.color || 'var(--color-brand-blue)' }} />
                                <span className="flex-1 truncate text-white">{eq.name}</span>
                                {eq.serial_number && <span className="text-[var(--color-text-faint)] text-[10px] truncate max-w-20">{eq.serial_number}</span>}
                                {eq.equipment_type && <span className="text-[var(--color-text-faint)] text-[10px]">{eq.equipment_type}</span>}
                                {placedCount > 0 && <span className="bg-white/20 text-white px-1 rounded text-[10px] font-bold flex-shrink-0">{placedCount}</span>}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Floor plan with zoom controls */}
              {wizardFloorPlanBlobUrl && !wizardDetecting && (
                <div>
                  {/* Zoom + snap controls */}
                  <div className="flex items-center justify-between mb-2 flex-wrap gap-y-1">
                    <div className="flex items-center gap-3">
                      <span className="text-[var(--color-text-muted)] text-xs">
                        {wizardDetectedEquipment.length > 0 && `${wizardDetectedEquipment.length} placed`}
                      </span>
                    </div>
                    <div className="flex items-center gap-2" data-testid="zoom-controls">
                      {/* Snap to grid toggle */}
                      <button
                        onClick={() => setWizardSnapToGrid(s => !s)}
                        className={`flex items-center gap-1 h-7 px-2 rounded-md border text-[10px] font-medium transition-all ${
                          wizardSnapToGrid ? 'border-[rgb(var(--rgb-brand-blue)/0.5)] bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)]' : 'border-white/10 text-[var(--color-text-faint)]'
                        }`}
                        title={`Snap to grid (${wizardGridSize}m)`}
                        data-testid="snap-toggle-btn"
                      >
                        <Grid3X3 size={12} />
                        Snap {wizardGridSize}m
                      </button>
                      {wizardSnapToGrid && (
                        <select
                          value={wizardGridSize}
                          onChange={(e) => setWizardGridSize(parseFloat(e.target.value))}
                          className="h-7 bg-[var(--color-ink-alt)] border border-white/10 text-[var(--color-text-muted)] text-[10px] rounded-md px-1"
                          data-testid="grid-size-select"
                        >
                          <option value={0.25}>0.25m</option>
                          <option value={0.5}>0.5m</option>
                          <option value={1}>1m</option>
                        </select>
                      )}
                      <div className="w-px h-5 bg-white/10" />
                      <span className="text-[var(--color-text-muted)] text-xs">{Math.round(wizardZoom * 100)}%</span>
                      <Button variant="outline" size="sm" className="h-7 w-7 p-0 border-white/10 text-[var(--color-text-muted)]" onClick={() => { setWizardZoom(z => Math.max(0.5, +(z - 0.25).toFixed(2))); setWizardSelectedMarker(null); }} data-testid="zoom-out-btn">
                        <ZoomOut size={14} />
                      </Button>
                      <Button variant="outline" size="sm" className="h-7 w-7 p-0 border-white/10 text-[var(--color-text-muted)]" onClick={() => { setWizardZoom(z => Math.min(3, +(z + 0.25).toFixed(2))); setWizardSelectedMarker(null); }} data-testid="zoom-in-btn">
                        <ZoomIn size={14} />
                      </Button>
                      {wizardZoom !== 1 && (
                        <Button variant="outline" size="sm" className="h-6 px-2 border-white/10 text-[var(--color-text-muted)] text-xs" onClick={() => setWizardZoom(1)}>Reset</Button>
                      )}
                    </div>
                  </div>

                  {/* Scrollable floor plan container */}
                  <div
                    className="overflow-auto rounded-lg border border-white/10"
                    style={{ maxHeight: '420px' }}
                    onClick={() => setWizardSelectedMarker(null)}
                    data-testid="wizard-floor-plan-container"
                  >
                    <div className="flex justify-center" style={{ minWidth: wizardZoom > 1 ? `${wizardZoom * 100}%` : 'auto' }}>
                      <div
                        className="relative inline-block"
                        style={{ cursor: (wizardActiveType || wizardActiveEquipment) ? 'crosshair' : 'default' }}
                        onClick={(e) => { e.stopPropagation(); handleFloorPlanClick(e); }}
                        data-testid="wizard-floor-plan-annotate"
                      >
                        <img
                          ref={wizardImgRef}
                          src={wizardFloorPlanBlobUrl}
                          alt="Floor plan"
                          style={{ height: `${350 * wizardZoom}px`, display: 'block' }}
                          draggable={false}
                        />

                        {/* Equipment shapes — draggable proportional rectangles */}
                        {floorPlanMarkers.map((marker, i) => (
                          <div
                            key={i}
                            className={`absolute flex items-center justify-center rounded-sm transition-shadow ${
                              wizardDragging?.idx === i ? 'ring-2 ring-[var(--color-brand-blue)] shadow-2xl opacity-90' :
                              wizardSelectedMarker === i ? 'ring-2 ring-white shadow-xl' : 'hover:ring-1 hover:ring-white/50'
                            }`}
                            style={{
                              left: `${marker.x_percent}%`,
                              top: `${marker.y_percent}%`,
                              width: `${marker.width_pct}%`,
                              height: `${marker.height_pct}%`,
                              transform: `translate(-50%, -50%) rotate(${marker.rotation}deg)`,
                              backgroundColor: marker.color + '55',
                              border: `2px solid ${marker.color}`,
                              zIndex: wizardDragging?.idx === i ? 30 : wizardSelectedMarker === i ? 20 : 10,
                              cursor: wizardDragging?.idx === i ? 'grabbing' : 'grab',
                              userSelect: 'none'
                            }}
                            onMouseDown={(e) => handleMarkerDragStart(e, i)}
                            onClick={(e) => e.stopPropagation()}
                            title={`${marker.name} (${wizardDetectedEquipment[i]?.width_m || '?'}m × ${wizardDetectedEquipment[i]?.length_m || '?'}m)`}
                            data-testid={`floor-marker-${i}`}
                          >
                            <span className="text-[10px] font-bold text-white leading-none drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)] pointer-events-none">{i + 1}</span>
                          </div>
                        ))}

                        {/* Toolbar for selected marker: rotate + dimensions + delete */}
                        {wizardSelectedMarker !== null && floorPlanMarkers[wizardSelectedMarker] && !wizardDragging && (
                          <>
                            <div
                              className="absolute bg-black/90 backdrop-blur-sm rounded-lg px-2 py-1.5 flex items-center gap-1 z-30 shadow-xl"
                              style={{
                                left: `${floorPlanMarkers[wizardSelectedMarker].x_percent}%`,
                                top: `${Math.max(5, floorPlanMarkers[wizardSelectedMarker].y_percent - floorPlanMarkers[wizardSelectedMarker].height_pct / 2 - 6)}%`,
                                transform: 'translateX(-50%)'
                              }}
                              onClick={(e) => e.stopPropagation()}
                              onMouseDown={(e) => e.stopPropagation()}
                              data-testid="marker-toolbar"
                            >
                              <button onClick={() => handleRotateMarker(-90)} className="text-white p-1 hover:bg-white/20 rounded transition-colors" title="Rotate left" data-testid="rotate-left-btn">
                                <RotateCcw size={13} />
                              </button>
                              <button onClick={() => handleRotateMarker(90)} className="text-white p-1 hover:bg-white/20 rounded transition-colors" title="Rotate right" data-testid="rotate-right-btn">
                                <RotateCw size={13} />
                              </button>
                              <div className="w-px h-4 bg-white/20 mx-0.5" />
                              {/* Dimension inputs */}
                              <div className="flex items-center gap-0.5">
                                <input
                                  type="number"
                                  step="0.1"
                                  min="0.3"
                                  value={wizardDetectedEquipment[wizardSelectedMarker]?.width_m || ''}
                                  onChange={(e) => handleUpdateDimension(wizardSelectedMarker, 'width_m', e.target.value)}
                                  className="w-10 h-5 bg-white/10 text-white text-[10px] text-center rounded border border-white/20 focus:outline-none focus:border-[var(--color-brand-blue)]"
                                  title="Width (m)"
                                  data-testid="dim-width-input"
                                />
                                <span className="text-white/40 text-[10px]">×</span>
                                <input
                                  type="number"
                                  step="0.1"
                                  min="0.3"
                                  value={wizardDetectedEquipment[wizardSelectedMarker]?.length_m || ''}
                                  onChange={(e) => handleUpdateDimension(wizardSelectedMarker, 'length_m', e.target.value)}
                                  className="w-10 h-5 bg-white/10 text-white text-[10px] text-center rounded border border-white/20 focus:outline-none focus:border-[var(--color-brand-blue)]"
                                  title="Length (m)"
                                  data-testid="dim-length-input"
                                />
                                <span className="text-white/40 text-[9px]">m</span>
                              </div>
                              <div className="w-px h-4 bg-white/20 mx-0.5" />
                              <button onClick={handleDeleteSelectedMarker} className="text-red-400 p-1 hover:bg-red-500/20 rounded transition-colors" title="Remove" data-testid="delete-marker-btn">
                                <X size={13} />
                              </button>
                              <div className="w-px h-4 bg-white/20 mx-0.5" />
                              <span className="text-[#6EE7B7] text-[9px] font-mono whitespace-nowrap" data-testid="position-readout">
                                {((wizardDetectedEquipment[wizardSelectedMarker]?.x_percent / 100) * gymLengthForCalc).toFixed(1)}m, {((wizardDetectedEquipment[wizardSelectedMarker]?.y_percent / 100) * gymWidthForCalc).toFixed(1)}m
                              </span>
                            </div>
                            <div
                              className="absolute text-[8px] text-white/40 whitespace-nowrap pointer-events-none z-30"
                              style={{
                                left: `${floorPlanMarkers[wizardSelectedMarker].x_percent}%`,
                                top: `${Math.max(5, floorPlanMarkers[wizardSelectedMarker].y_percent - floorPlanMarkers[wizardSelectedMarker].height_pct / 2 - 4)}%`,
                                transform: 'translateX(-50%)'
                              }}
                              data-testid="nudge-hint"
                            >
                              Arrow keys: nudge · Shift+Arrow: micro-nudge
                            </div>
                          </>
                        )}

                        {/* Active type placement hint */}
                        {(wizardActiveType || wizardActiveEquipment) && (
                          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 bg-black/80 text-white text-xs px-3 py-1.5 rounded-full whitespace-nowrap z-30 pointer-events-none">
                            Click to place: {wizardActiveEquipment?.name || EQUIPMENT_TYPES.find(t => t.id === wizardActiveType)?.name}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Loading state */}
              {wizardDetecting && (
                <div className="text-center py-8">
                  <Loader2 size={32} className="mx-auto mb-3 text-[var(--color-brand-blue)] animate-spin" />
                  <p className="text-white font-semibold">AI is analysing your floor plan...</p>
                  <p className="text-[var(--color-text-muted)] text-sm">This may take 10-30 seconds.</p>
                </div>
              )}

              {/* Placed equipment list */}
              {!wizardDetecting && wizardDetectedEquipment.length > 0 && (
                <div className="space-y-1.5" data-testid="detected-equipment-list">
                  {wizardDetectionNotes && <p className="text-[var(--color-text-muted)] text-xs">{wizardDetectionNotes}</p>}
                  <p className="text-[var(--color-text-muted)] text-xs font-medium">Placed Equipment ({wizardDetectedEquipment.length}):</p>
                  <div className="max-h-40 overflow-y-auto space-y-1">
                    {wizardDetectedEquipment.map((eq, i) => {
                      const eqColor = (EQUIPMENT_TYPES.find(t => t.id === mapTypeNameToId(eq.type || eq.name)) || {}).color || 'var(--color-brand-blue)';
                      return (
                        <div key={i} className={`flex items-center gap-2 px-3 py-1.5 bg-[var(--color-ink-alt)] rounded-lg border transition-colors cursor-pointer group ${
                          wizardSelectedMarker === i ? 'border-white/30 bg-white/5' : 'border-white/10'
                        }`} onClick={() => setWizardSelectedMarker(wizardSelectedMarker === i ? null : i)} data-testid={`detected-eq-${i}`}>
                          <div className="w-5 h-5 rounded-sm flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0" style={{ backgroundColor: eqColor }}>
                            {i + 1}
                          </div>
                          {wizardEditingIdx === i ? (
                            <Input
                              autoFocus
                              value={eq.name || ''}
                              onChange={(e) => handleEditDetectedName(i, e.target.value)}
                              onBlur={() => setWizardEditingIdx(null)}
                              onKeyDown={(e) => { if (e.key === 'Enter') setWizardEditingIdx(null); }}
                              className="bg-transparent border-white/20 text-white text-sm h-7 py-0 flex-1"
                              onClick={(e) => e.stopPropagation()}
                              data-testid={`edit-eq-name-${i}`}
                            />
                          ) : (
                            <span className="text-white text-sm flex-1 truncate">{eq.name || eq.type}</span>
                          )}
                          <span className="text-[var(--color-text-faint)] text-[10px] flex-shrink-0">{eq.width_m || '?'}×{eq.length_m || '?'}m</span>
                          {eq.serial_number && <span className="text-[var(--color-text-faint)] text-[10px]">{eq.serial_number}</span>}
                          <button onClick={(e) => { e.stopPropagation(); setWizardEditingIdx(i); }} className="text-[var(--color-text-muted)] hover:text-white opacity-0 group-hover:opacity-100 transition-opacity p-0.5" data-testid={`edit-eq-${i}`}>
                            <Pencil size={12} />
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); handleRemoveDetected(i); }} className="text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100 transition-opacity p-0.5" data-testid={`remove-eq-${i}`}>
                            <X size={14} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Action buttons */}
              <div className="flex justify-between items-center pt-2">
                <Button variant="outline" className="border-white/10 text-[var(--color-text-muted)]" onClick={() => { setWizardStep(1); setWizardDetectedEquipment([]); }} data-testid="wizard-back-btn">Back</Button>
                <div className="flex gap-2">
                  {!wizardDetecting && (
                    <Button
                      variant="outline"
                      className="border-white/10 text-[var(--color-text-muted)]"
                      onClick={handleDetectEquipment}
                      data-testid="wizard-detect-btn"
                    >
                      <Sparkles size={14} className="mr-1.5" /> AI Auto-Detect
                    </Button>
                  )}
                  <Button className="text-white" style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }} onClick={() => setWizardStep(3)} data-testid="wizard-next-btn">
                    Next — Review
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Review & Create */}
          {wizardStep === 3 && (
            <div className="space-y-4" data-testid="wizard-step-review">
              {/* Editable layout name */}
              <div>
                <Label className="text-[var(--color-text-muted)] text-sm">Layout Name</Label>
                <Input
                  value={wizardName}
                  onChange={(e) => setWizardName(e.target.value)}
                  placeholder="e.g., Main Gym Floor"
                  className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                  data-testid="wizard-review-layout-name"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
                  <p className="text-[var(--color-text-muted)] text-xs">Method</p>
                  <p className="text-white font-semibold text-sm">{wizardMethod === 'upload' ? 'Floor Plan Upload' : 'Manual'}</p>
                </div>
                {wizardMethod === 'scratch' && (
                  <div className="p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
                    <p className="text-[var(--color-text-muted)] text-xs">Dimensions</p>
                    <p className="text-white font-semibold text-sm">{wizardLength}m × {wizardWidth}m</p>
                  </div>
                )}
                {wizardMethod === 'upload' && (
                  <div className="p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
                    <p className="text-[var(--color-text-muted)] text-xs">Floor Plan</p>
                    <p className="text-green-400 font-semibold text-sm">Uploaded</p>
                  </div>
                )}
                <div className="p-3 bg-[var(--color-ink-alt)] rounded-lg border border-white/10">
                  <p className="text-[var(--color-text-muted)] text-xs">Equipment</p>
                  <p className="text-white font-semibold text-sm">{wizardDetectedEquipment.length} items</p>
                </div>
              </div>

              <div className="flex justify-between">
                <Button variant="outline" className="border-white/10 text-[var(--color-text-muted)]" onClick={() => setWizardStep(wizardMethod === 'upload' ? 2 : 1)} data-testid="wizard-back-btn">Back</Button>
                <Button className="text-white" style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }} onClick={handleWizardComplete} data-testid="wizard-create-btn">
                  <LayoutIcon size={16} className="mr-2" /> Create Layout
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Add Equipment Dialog */}
      <Dialog open={showEquipmentDialog} onOpenChange={setShowEquipmentDialog}>
        <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white" data-testid="add-equipment-dialog">
          <DialogHeader>
            <DialogTitle className="text-white">Add {selectedEquipmentType?.name}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddEquipment} className="space-y-4">
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Equipment Name</Label>
              <Input value={equipmentForm.name} onChange={(e) => setEquipmentForm({...equipmentForm, name: e.target.value})} required placeholder="e.g., Treadmill 1" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="equipment-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-[var(--color-text-muted)] text-sm">Manufacturer</Label>
                <Input value={equipmentForm.manufacturer} onChange={(e) => setEquipmentForm({...equipmentForm, manufacturer: e.target.value})} placeholder="e.g., Life Fitness" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="manufacturer-input" />
              </div>
              <div>
                <Label className="text-[var(--color-text-muted)] text-sm">Model</Label>
                <Input value={equipmentForm.model} onChange={(e) => setEquipmentForm({...equipmentForm, model: e.target.value})} placeholder="e.g., T5-Go" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="model-input" />
              </div>
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Serial Number</Label>
              <Input value={equipmentForm.serial_number} onChange={(e) => setEquipmentForm({...equipmentForm, serial_number: e.target.value})} placeholder="SN123456789" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="serial-input" />
            </div>
            <Button type="submit" className="w-full text-white" style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }} data-testid="add-equipment-submit-btn">
              Add to Layout
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Import Floor Plan Dialog (for existing layouts) */}
      <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
        <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white" data-testid="import-floorplan-dialog">
          <DialogHeader>
            <DialogTitle className="text-white">Import Floor Plan</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-[var(--color-text-muted)] text-sm">Upload a PDF or image of your gym floor plan. It will be displayed as a background layer.</p>
            <div className="border-2 border-dashed border-white/20 rounded-xl p-8 text-center hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors">
              <FileImage size={40} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
              <p className="text-white mb-2">Drop your floor plan here or click to browse</p>
              <p className="text-[var(--color-text-muted)] text-xs mb-4">Supports: PDF, PNG, JPG</p>
              <label className="cursor-pointer">
                <input type="file" className="hidden" accept="image/*,.pdf" onChange={handleFloorPlanUpload} data-testid="floorplan-file-input" />
                <Button type="button" className="pointer-events-none text-white" style={{ backgroundColor: 'var(--brand-color, var(--color-brand-blue))' }} data-testid="floorplan-browse-btn">
                  <Upload size={16} className="mr-2" /> {importUploading ? 'Uploading...' : 'Choose File'}
                </Button>
              </label>
            </div>
            {floorPlanUrl && (
              <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center justify-between">
                <span className="text-green-400 text-sm">Floor plan active</span>
                <Button size="sm" variant="outline" className="border-red-500/50 text-red-400" onClick={handleClearFloorPlan}>Remove</Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default GymDesignTab;
