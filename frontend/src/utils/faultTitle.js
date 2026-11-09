/**
 * Fault card heading: lead with what the machine IS (make + model) so site
 * staff can find it on the floor; the serial sits underneath in small text.
 *
 * Make/model come from the linked equipment record (GET /api/issues adds
 * equipment_make / equipment_model / equipment_name / equipment_type).
 * Fallbacks: equipment name → machine type → serial → generic label.
 */
export function faultTitle(issue = {}) {
  const serial = (issue.serial_number || '').trim();
  const make = (issue.equipment_make || '').trim();
  const model = (issue.equipment_model || '').trim();
  // Avoid "Life Fitness Life Fitness 95T" when the model already names the make.
  const makeModel = make && model && model.toLowerCase().startsWith(make.toLowerCase())
    ? model
    : [make, model].filter(Boolean).join(' ');
  const name = (issue.equipment_name || '').trim();
  const type = (issue.machine_type || issue.equipment_type || '').trim();

  const title = makeModel
    || (name && name !== serial ? name : '')
    || type
    || serial
    || 'Equipment';
  return {
    title,
    serial: serial && serial !== title ? serial : '',
    // The grey meta line already shows machine_type — skip it if it's the title.
    titleIsType: !makeModel && !(name && name !== serial) && !!type && title === type,
  };
}

export default faultTitle;
