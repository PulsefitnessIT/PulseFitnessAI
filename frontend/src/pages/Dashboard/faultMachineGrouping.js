/**
 * Iter 216d2 — equipment grouping for the "Log a Fault" dialog.
 *
 * Background
 * ----------
 * Pre-iter-216d2 the GymAxis Dashboard's `Log a Fault` form grouped the
 * Machine Type dropdown by `equipment_type`, so a row imported with
 * `equipment_type="cardio"` and `name="Treadmill"` showed up as
 * "cardio (1)" — meaningless to operators (Lee's Feb-2026 prod report).
 *
 * The fix groups by the machine's display NAME (using everything before
 * the first comma so "Treadmill, Bay 3" + "Treadmill, Bay 4" collapse
 * into "Treadmill (2)"), falling back to `equipment_type` only when
 * `name` is empty. The Serial Number dropdown filters by the SAME
 * derived key.
 *
 * This file extracts the pure grouping function so we can pin its
 * behaviour without spinning up the whole dialog in jsdom.
 */

export function deriveGroupKey(equipment) {
  const name = (equipment?.name || '').trim();
  if (name) return name.includes(',') ? name.split(',')[0].trim() : name;
  return (equipment?.equipment_type || '').trim();
}

export function buildMachineTypeGroups(equipmentList) {
  if (!Array.isArray(equipmentList)) return [];
  const counts = new Map();
  for (const e of equipmentList) {
    const key = deriveGroupKey(e);
    if (!key) continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([type, count]) => ({ type, count, label: `${type} (${count})` }));
}

export function filterSerialsByGroup(equipmentList, groupKey) {
  if (!Array.isArray(equipmentList)) return [];
  if (!groupKey) return equipmentList;
  return equipmentList.filter(e => deriveGroupKey(e) === groupKey);
}
