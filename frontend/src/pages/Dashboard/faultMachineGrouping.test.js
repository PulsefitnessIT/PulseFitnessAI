import {
  deriveGroupKey,
  buildMachineTypeGroups,
  filterSerialsByGroup,
} from './faultMachineGrouping';

/* eslint-env jest */
/* global describe, test, expect */

describe('iter 216d2 — fault machine grouping', () => {
  // Minimal repro of Lee's Feb-2026 production data: the Machine Type
  // dropdown was showing "cardio (1)" because we grouped by
  // `equipment_type`. Now we group by the display `name` so the user
  // sees "Treadmill (1)".
  const bobsEstate = [
    {
      id: '1',
      name: 'Treadmill',
      equipment_type: 'cardio',
      serial_number: '12345',
      manufacturer: 'Pulse Fitness',
    },
  ];

  test('deriveGroupKey prefers name over equipment_type', () => {
    expect(deriveGroupKey(bobsEstate[0])).toBe('Treadmill');
  });

  test('buildMachineTypeGroups labels with name + count', () => {
    const groups = buildMachineTypeGroups(bobsEstate);
    expect(groups).toEqual([{ type: 'Treadmill', count: 1, label: 'Treadmill (1)' }]);
  });

  test('collapses comma-suffixed names into one group', () => {
    const estate = [
      { id: '1', name: 'Treadmill, Bay 1', equipment_type: 'cardio' },
      { id: '2', name: 'Treadmill, Bay 2', equipment_type: 'cardio' },
      { id: '3', name: 'Treadmill, Bay 3', equipment_type: 'cardio' },
      { id: '4', name: 'Bike',             equipment_type: 'cardio' },
    ];
    const groups = buildMachineTypeGroups(estate);
    expect(groups).toEqual([
      { type: 'Bike',      count: 1, label: 'Bike (1)' },
      { type: 'Treadmill', count: 3, label: 'Treadmill (3)' },
    ]);
  });

  test('falls back to equipment_type when name is missing', () => {
    expect(deriveGroupKey({ name: '', equipment_type: 'Strength Equipment' }))
      .toBe('Strength Equipment');
  });

  test('filterSerialsByGroup matches the same derived key', () => {
    const estate = [
      { id: '1', name: 'Treadmill, Bay 1', serial_number: 'T1' },
      { id: '2', name: 'Treadmill, Bay 2', serial_number: 'T2' },
      { id: '3', name: 'Bike',             serial_number: 'B1' },
    ];
    const treadmills = filterSerialsByGroup(estate, 'Treadmill');
    expect(treadmills.map(e => e.serial_number)).toEqual(['T1', 'T2']);
    const bikes = filterSerialsByGroup(estate, 'Bike');
    expect(bikes.map(e => e.serial_number)).toEqual(['B1']);
  });

  test('empty group key returns the full list (filter unset)', () => {
    expect(filterSerialsByGroup(bobsEstate, '')).toEqual(bobsEstate);
  });
});
