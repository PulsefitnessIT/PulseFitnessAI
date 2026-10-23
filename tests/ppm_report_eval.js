// Evaluates PpmScheduleDetail.buildReportHtml edge cases in Node (extracts the real function source)
const fs = require('fs');
const src = fs.readFileSync('/app/frontend/src/pages/ServiceDesk/PpmScheduleDetail.js', 'utf8');
const start = src.indexOf('const fmtDate');
const end = src.indexOf('function printReport');
const code = src.slice(start, end) + '\nmodule.exports = buildReportHtml;';
const m = { exports: {} };
new Function('module', code)(m);
const build = m.exports;
const machines = [
  { name: 'Treadmill A', equipment_type: 'Treadmill', serial_number: 'SN1' },
  { name: 'Bike B', equipment_type: 'Bike', serial_number: 'SN2' },
  { name: 'Rower C', equipment_type: 'Rower', serial_number: '' },
];
const sched = { site_name: 'Site X', engineer: 'Sched Eng', date: '2026-01-10' };
const count = (h, s) => (h.match(new RegExp(s, 'g')) || []).length;
const check = (label, html) => {
  console.log(`\n== ${label}`);
  console.log(' Not serviced rows:', count(html, 'Not serviced'),
    '| Machines on site:', html.includes('Machines on site'),
    '| Treadmill A:', count(html, 'Treadmill A'), 'Bike B:', count(html, 'Bike B'), 'Rower C:', count(html, 'Rower C'));
  const eng = html.match(/<b>Engineer<\/b><br\/>([^<]*)/); console.log(' Engineer box:', eng && eng[1]);
};
check('no visits', build({ schedule: sched, machines, visits: [] }));
check('1 visit no machine_work', build({ schedule: sched, machines, visits: [{ engineer: 'Real Eng', status: 'completed' }] }));
check('2 visits, latest none, older worked SN1', build({ schedule: sched, machines, visits: [
  { engineer: 'Latest Eng', status: 'completed' },
  { engineer: 'Old Eng', machine_work: [{ asset_name: 'Treadmill A', asset_serial: 'SN1', serviced: true }] }] }));
check('latest worked SN1+Rower by name', build({ schedule: sched, machines, visits: [
  { engineer: 'Real Eng', machine_work: [{ asset_name: 'Treadmill A', asset_serial: 'SN1', serviced: true }, { asset_name: 'Rower C', serviced: true }] }] }));
check('worked entry name-only for serial machine (mismatch edge)', build({ schedule: sched, machines, visits: [
  { engineer: 'Real Eng', machine_work: [{ asset_name: 'Bike B', serviced: true }] }] }));
check('visit with blank engineer', build({ schedule: sched, machines, visits: [{ engineer: '', status: 'scheduled' }] }));
