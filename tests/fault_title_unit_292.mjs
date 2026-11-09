// iter292: faultMetaLine drops machine_type when it equals title (case-insensitive) or title came from type.
import { faultTitle, faultMetaLine } from '/tmp/faultTitle.mjs';
let p=0,f=0; const eq=(n,a,e)=>{ if(a===e){p++;console.log('PASS',n);} else {f++;console.log('FAIL',n,JSON.stringify(a),'!=',JSON.stringify(e));} };
eq('model==type', faultMetaLine({equipment_model:'Treadmill',machine_type:'Treadmill',serial_number:'S1'},'d'),'d');
eq('skillmill', faultMetaLine({equipment_make:'Technogym',equipment_model:'SKILLMILL',machine_type:'Treadmill',supplier:'Inda',serial_number:'S1'},'d'),'Treadmill | Inda | d');
eq('case-insens', faultMetaLine({equipment_model:'treadmill',machine_type:'TREADMILL',serial_number:'S1'},'d'),'d');
eq('name==type', faultMetaLine({equipment_name:'Rower',machine_type:'rower',serial_number:'S1',supplier:'X'},'d'),'X | d');
eq('make+model==type? keeps type', faultMetaLine({equipment_make:'Life',equipment_model:'Treadmill',machine_type:'Treadmill',serial_number:'S1'},'d'),'Treadmill | d');
eq('type title only', faultMetaLine({machine_type:'Bike',serial_number:'S1',supplier_ref:'R'},'d'),'d | Ref: R');
eq('whitespace type==title', faultMetaLine({equipment_model:'Bike ',machine_type:' bike',serial_number:'S1'},'d'),'d');
eq('no type no title data', faultMetaLine({serial_number:'S1'},''),'');
eq('equipment_type title, machine_type differs', faultMetaLine({equipment_type:'Rower',machine_type:'Cardio',serial_number:'S1'},'d'), 'd');
console.log('INFO last:', faultTitle({equipment_type:'Rower',machine_type:'Cardio',serial_number:'S1'}));
console.log(`RESULT pass=${p} fail=${f}`);
