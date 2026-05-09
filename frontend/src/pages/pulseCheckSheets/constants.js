// Equipment-type → daily-checklist mapping plus name-heuristic classifier.
// Extracted from PulseCheckSheetsTab during the iter-216c refactor so the
// orchestrator file stays focused on state/API plumbing.
//
// Lee's Feb-2026 production feedback drove the heuristic: equipment_type
// is often blank on import, so we fall back to substring-matching the
// equipment name (priority order, first hit wins). Anything still
// unmatched falls into "Uncategorised" (never the silent "Other" dump).

export const EQUIPMENT_TYPE_TASKS = {
  // ─── Cardio: Treadmills ───
  'Treadmill':       ['All Areas Cleaned','Hoover Underneath','E-Stop Check','Console + & - Keys Check','Heart Rate Check','Speed Test','Incline Check','Belt Aligned','Power/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Running Machine': ['All Areas Cleaned','Hoover Underneath','E-Stop Check','Console + & - Keys Check','Heart Rate Check','Speed Test','Incline Check','Belt Aligned','Power/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  // ─── Cardio: Bikes (upright, recumbent, generic exercise) ───
  'Upright Bike':    ['All Areas Cleaned','Hoover Underneath','Seat Adjustment Working','Foot Straps & Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Recumbent Bike':  ['All Areas Cleaned','Hoover Underneath','Seat Adjustment Working','Foot Straps & Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Exercise Bike':   ['All Areas Cleaned','Hoover Underneath','Seat Adjustment Working','Foot Straps & Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Bike':            ['All Areas Cleaned','Hoover Underneath','Seat Adjustment Working','Foot Straps & Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  // ─── Cardio: Cross trainers ───
  'Cross Trainer':   ['All Areas Cleaned','Hoover Underneath','Handles Move Smoothly','Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Elliptical':      ['All Areas Cleaned','Hoover Underneath','Handles Move Smoothly','Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  // ─── Cardio: Rowers ───
  'Rower':           ['All Areas Cleaned','Hoover Underneath','Foot Straps & Heel Lock Check','Console Check/Batteries OK','Console Keys Check','Smooth Chain/Seat Rail - Lubricate If Required','Heart Rate Check','Resistance Check/Fan','Hoover Fan','Inspect Bungees and Drive Cords'],
  'Rowing Machine':  ['All Areas Cleaned','Hoover Underneath','Foot Straps & Heel Lock Check','Console Check/Batteries OK','Console Keys Check','Smooth Chain/Seat Rail - Lubricate If Required','Heart Rate Check','Resistance Check/Fan','Hoover Fan','Inspect Bungees and Drive Cords'],
  // ─── Cardio: Spin / group cycle ───
  'Spin Bike':       ['All Areas Cleaned','All Locking Levers/Knobs Checked','Pedals Screwed In Tightly','Toe Straps Secure','Crank Feels Smooth','Handlebars Check','Console Batteries OK','Speed Test','Resistance Check'],
  'Group Cycle':     ['All Areas Cleaned','All Locking Levers/Knobs Checked','Pedals Screwed In Tightly','Toe Straps Secure','Crank Feels Smooth','Handlebars Check','Console Batteries OK','Speed Test','Resistance Check'],
  // ─── Cardio: Steppers / StepMills ───
  'StepMill':        ['All Areas Cleaned','Hoover Underneath','Steps Move Smoothly','E-Stop Check','+ & - Keys Check','Speed Test','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Stepper':         ['All Areas Cleaned','Hoover Underneath','Steps Move Smoothly','E-Stop Check','+ & - Keys Check','Speed Test','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  // ─── Strength: selectorised / cable / press ───
  'Strength Equipment': ['All Areas Cleaned','Hoover Around','Check Upholstery for Splits','Tighten Upholstery Bolts','Lubricate Guiding Rods','Lubricate Moving Parts When Needed','Check all Cables & Pulleys','Smooth Seat Movement','Weight Pin Available & Can Select Each Weight','Handles Move Smoothly'],
  'Leg Press':       ['All Areas Cleaned','Hoover Around','Check Upholstery for Splits','Tighten Upholstery Bolts','Lubricate Guiding Rods','Lubricate Moving Parts When Needed','Check all Cables & Pulleys','Smooth Seat Movement','Weight Pin Available & Can Select Each Weight','Handles Move Smoothly'],
  'Cable Machine':   ['All Areas Cleaned','Hoover Around','Check Upholstery for Splits','Tighten Upholstery Bolts','Lubricate Guiding Rods','Lubricate Moving Parts When Needed','Check all Cables & Pulleys','Smooth Seat Movement','Weight Pin Available & Can Select Each Weight','Handles Move Smoothly'],
  // ─── Free weights / dumbbells / benches ───
  'Free Weights':    ['Framework Dusted','Upholstery Clean','Clean Mirrors','Wipe down Weight Plates','Check Weight Bars for Defects','Check Rubber Weight Covers','Check & Clean Dumbbell Stack','Lubricate Moving Parts','Check Upholstery for Splits','Tighten Weight Bolts'],
  'Dumbbell':        ['Framework Dusted','Upholstery Clean','Clean Mirrors','Wipe down Weight Plates','Check Weight Bars for Defects','Check Rubber Weight Covers','Check & Clean Dumbbell Stack','Lubricate Moving Parts','Check Upholstery for Splits','Tighten Weight Bolts'],
  'Bench':           ['Framework Dusted','Upholstery Clean','Check Upholstery for Splits','Tighten Upholstery Bolts','Check Adjustment Pins','Lubricate Moving Parts','Check All Bolts & Fixings','Clean Frame'],
};

export const DEFAULT_TASKS = ['All Areas Cleaned','Visual Inspection for Damage','Check for Loose Bolts/Fixings','Lubricate Moving Parts','Check Safety Features','Console/Display Check','Power Cable Check','Test Equipment Operation'];

const NAME_HEURISTICS = [
  ['Treadmill',          ['treadmill', 'running machine', 'tread']],
  ['Stepper',            ['stepmill', 'stair', 'stepper', 'step machine']],
  ['Cross Trainer',      ['cross trainer', 'elliptical', 'crosstrainer']],
  ['Rower',              ['rower', 'rowing']],
  ['Spin Bike',          ['spin bike', 'group cycle', 'spinner']],
  ['Upright Bike',       ['upright', 'air bike', 'assault bike']],
  ['Recumbent Bike',     ['recumbent']],
  ['Exercise Bike',      ['cycle', 'bike', 'cardio bike']],
  ['Strength Equipment', ['lat pulldown', 'leg press', 'chest press', 'shoulder press', 'cable cross', 'pec deck', 'smith', 'rack', 'multi-station', 'selectorised']],
  ['Free Weights',       ['dumbbell', 'kettlebell', 'barbell', 'plate']],
  ['Bench',              ['bench']],
];

export function classifyByName(name) {
  if (!name) return null;
  const n = String(name).toLowerCase();
  for (const [type, needles] of NAME_HEURISTICS) {
    if (needles.some(needle => n.includes(needle))) return type;
  }
  return null;
}

export function getTasksForType(type) {
  if (!type) return DEFAULT_TASKS;
  const lower = type.toLowerCase();
  for (const [key, tasks] of Object.entries(EQUIPMENT_TYPE_TASKS)) {
    if (lower.includes(key.toLowerCase()) || key.toLowerCase().includes(lower)) return tasks;
  }
  return DEFAULT_TASKS;
}
