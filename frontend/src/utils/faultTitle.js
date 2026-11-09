/**
 * Fault card heading: lead with what the machine IS (make + model) so site
 * staff can find it on the floor; the serial sits underneath in small text.
 *
 * Make/model come from the linked equipment record (GET /api/issues adds
 * equipment_make / equipment_model / equipment_name / equipment_type).
 * Fallbacks: make + name → equipment name → machine type → serial.
 */
const clean = (v) => (v == null ? '' : String(v).trim());

export function faultTitle(issue = {}) {
  const serial = clean(issue.serial_number);
  const make = clean(issue.equipment_make);
  let model = clean(issue.equipment_model);
  const name = clean(issue.equipment_name);
  const type = clean(issue.machine_type || issue.equipment_type);

  // Imported asset lists sometimes put the first chars of the serial in the
  // model column (e.g. model "MNLPNN0" for serial MNLPNN020100194) — that's
  // not a model, so describe the machine by its name instead.
  if (model && serial && serial.toLowerCase().startsWith(model.toLowerCase())) model = '';
  const usefulName = name && name !== serial ? name : '';

  const join = (a, b) => (a && b && b.toLowerCase().startsWith(a.toLowerCase()) ? b : [a, b].filter(Boolean).join(' '));
  const title = (model && join(make, model))
    || (usefulName && join(make, usefulName))
    || type
    || serial
    || 'Equipment';

  // Small line under the title: machine name (when not already shown) + serial.
  const nameInTitle = usefulName && title.toLowerCase().includes(usefulName.toLowerCase());
  const subtitleParts = [];
  if (usefulName && !nameInTitle && title !== usefulName) subtitleParts.push(usefulName);
  if (serial && serial !== title) subtitleParts.push(`S/N ${serial}`);

  return {
    title,
    serial: serial && serial !== title ? serial : '',
    subtitle: subtitleParts.join(' · '),
    titleIsType: !model && !usefulName && !!type && title === type,
  };
}

/** Grey meta line: machine type (unless it's the title) | supplier | date | ref. */
export function faultMetaLine(issue = {}, dateText = '') {
  const { title, titleIsType } = faultTitle(issue);
  const type = clean(issue.machine_type);
  const typeRepeatsTitle = titleIsType || (type && type.toLowerCase() === title.toLowerCase());
  return [
    typeRepeatsTitle ? '' : type,
    clean(issue.supplier),
    dateText,
    issue.supplier_ref ? `Ref: ${issue.supplier_ref}` : '',
  ].filter(Boolean).join(' | ');
}

export default faultTitle;

/**
 * Was the supplier's "new fault" email actually accepted by the provider?
 * New faults record `auto_dispatch_delivered_to`; older faults (no record)
 * keep the previous behaviour and count as delivered.
 */
export function supplierEmailDelivered(issue = {}) {
  const delivered = issue.auto_dispatch_delivered_to;
  if (!Array.isArray(delivered)) return true;
  const to = clean(issue.supplier_case?.supplier_email || issue.auto_dispatched_supplier_email).toLowerCase();
  if (!to) return true;
  return delivered.map((e) => clean(e).toLowerCase()).includes(to);
}
