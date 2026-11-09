// Unit checks for frontend/src/utils/faultTitle.js (faultTitle + faultMetaLine). Run: node /app/tests/fault_title_unit.mjs
import { faultTitle, faultMetaLine } from '/tmp/faultTitle.mjs';
let pass = 0, fail = 0;
const eq = (name, got, exp) => {
  if (got === exp) { pass++; console.log('PASS', name); }
  else { fail++; console.log('FAIL', name, '\n   got:', JSON.stringify(got), '\n   exp:', JSON.stringify(exp)); }
};
const noEdge = (name, s) => {
  const bad = s.startsWith(' |') || s.startsWith('|') || s.endsWith('| ') || s.endsWith('|') || s.includes('|  |') || s.includes('| |');
  if (bad) { fail++; console.log('FAIL edge', name, JSON.stringify(s)); } else pass++;
};
const D = '1/2/2026';

// 1. prefix-of-serial model (prod data)
const a = { equipment_make: 'Technogym', equipment_model: 'MNLPNN0', serial_number: 'MNLPNN020100194', equipment_name: 'Lat Pulldown' };
eq('prefix title', faultTitle(a).title, 'Technogym Lat Pulldown');
eq('prefix subtitle', faultTitle(a).subtitle, 'S/N MNLPNN020100194');
// 2. real model
const b = { equipment_make: 'Technogym', equipment_model: 'SKILLMILL', serial_number: 'DJK04D22000131', equipment_name: 'Self-Powered Treadmill' };
eq('real title', faultTitle(b).title, 'Technogym SKILLMILL');
eq('real subtitle', faultTitle(b).subtitle, 'Self-Powered Treadmill · S/N DJK04D22000131');
// case-insensitive prefix model
eq('prefix lower', faultTitle({ ...a, equipment_model: 'mnlpnn0' }).title, 'Technogym Lat Pulldown');

// 3. meta line
eq('meta empty type + supplier', faultMetaLine({ serial_number: 'X1', machine_type: '', supplier: 'Inda' }, D), `Inda | ${D}`);
eq('meta type is title omitted', faultMetaLine({ serial_number: 'X1', machine_type: 'Treadmill', supplier: 'Inda' }, D), `Inda | ${D}`);
eq('meta type shown', faultMetaLine({ ...b, machine_type: 'Treadmill', supplier: 'Inda', supplier_ref: 'R9' }, D), `Treadmill | Inda | ${D} | Ref: R9`);
eq('meta only date', faultMetaLine({ serial_number: 'X1' }, D), D);
eq('meta nothing', faultMetaLine({}, ''), '');
eq('meta only ref', faultMetaLine({ supplier_ref: 'R1' }, ''), 'Ref: R1');
eq('meta whitespace type', faultMetaLine({ machine_type: '   ', supplier: ' Inda ' }, D), `Inda | ${D}`);

// exhaustive combos -> never leading/trailing/double separators
const types = ['', '  ', 'Treadmill', null, undefined];
const sups = ['', 'Inda', null, '  '];
const dates = ['', D];
const refs = ['', 'R1', null];
const issues = [{}, a, b, { serial_number: 'S1' }, { equipment_type: 'Bike' }];
for (const base of issues) for (const t of types) for (const s of sups) for (const d of dates) for (const r of refs) {
  const iss = { ...base, machine_type: t, supplier: s, supplier_ref: r };
  noEdge(JSON.stringify(iss) + d, faultMetaLine(iss, d));
}

// Edge: machine_type equals title produced by model (not by type) - documents behaviour
const c = { equipment_model: 'Treadmill', machine_type: 'Treadmill', serial_number: 'Z9' };
console.log('INFO model==machine_type title:', faultTitle(c).title, '| meta:', faultMetaLine(c, D));

console.log(`\nRESULT pass=${pass} fail=${fail}`);
