/**
 * EquipmentPlaceholder
 * ---------------------
 *
 * Minimal machine-type logo shown whenever we have no photo, no auto-matched
 * manufacturer image, and no spec-sheet hero to display. Deliberately styled
 * to match the "mini logos" inside the Operations options-bar pills — flat
 * cyan chip (var(--color-brand-cyan)), single Lucide silhouette in deep navy, no rings, no
 * gradient, no brand caption. Keeps the Equipment grid visually calm and
 * instantly recognisable at a glance.
 *
 * Why pure SVG/Lucide?
 *   - Zero AI cost, zero latency, zero external dependency.
 *   - Deterministic output → uniform across the whole fleet.
 *   - Crisp at any size, renders offline.
 */
import {
  Activity, Bike, Dumbbell, Disc, Waves, Footprints, Heart,
  Settings2, Package,
} from 'lucide-react';

// Menu-bar active-pill colour — identical to the `var(--color-brand-cyan)` chip used for the
// selected tab in LiteDashboardPage / PillTabBar. Reusing the exact token
// keeps the placeholders feeling native to the rest of the shell.
const PILL_BG = 'var(--color-brand-cyan)';
const PILL_FG = 'var(--color-ink)';

// Map equipment type → Lucide icon component. Order is most-specific first.
const TYPE_ICON_MAP = [
  [/treadmill|run|cardio.*tread/, Footprints],
  [/bike|cycle|spin|elliptic/, Bike],
  [/row|rower|erg/, Waves],
  [/dumbbell|kettle|free.*weight/, Dumbbell],
  [/cable|pulley|crossover|functional/, Settings2],
  [/squat|rack|bench|press|smith/, Activity],
  [/disc|plate/, Disc],
  [/cardio|stair|step/, Heart],
];

const iconFor = (equipmentType) => {
  const t = (equipmentType || '').toLowerCase();
  if (!t) return Package;
  for (const [pattern, Icon] of TYPE_ICON_MAP) {
    if (pattern.test(t)) return Icon;
  }
  return Package;
};

/**
 * Props
 *   equipmentType  string — drives the silhouette icon
 *   manufacturer   string — kept for API compatibility (not rendered)
 *   model          string — kept for API compatibility (not rendered)
 *   className      string
 *   testId         string
 */
const EquipmentPlaceholder = ({
  equipmentType,
  className = '',
  testId = 'equipment-placeholder',
   
  _manufacturer,
   
  _model,
}) => {
  const Icon = iconFor(equipmentType);

  return (
    <div
      className={`relative w-full h-full rounded-lg flex items-center justify-center select-none ${className}`}
      style={{ background: PILL_BG, color: PILL_FG }}
      data-testid={testId}
    >
      <Icon
        size="52%"
        strokeWidth={1.9}
        className="relative"
        data-testid={`${testId}-icon`}
      />
    </div>
  );
};

export default EquipmentPlaceholder;
