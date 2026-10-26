p='/app/backend/routes/crm_contracts.py'
s=open(p).read()
def rep(old,new):
    global s
    assert s.count(old)==1,(old[:70],s.count(old)); s=s.replace(old,new,1)
i=s.index('@router.get("/contracts")')
j=s.index('    query = _of(user)\n', i)
s=s[:j]+'    query = {**_of(user), "contract_type": {"$ne": "mod"}}  # MOD contracts live in their own tab\n'+s[j+len('    query = _of(user)\n'):]
rep('''    org_id = await _company_linked_org(company_id, user)
    name = (data.get("name") or "").strip()[:120]''','''    _require_location_editor(user)
    org_id = await _company_linked_org(company_id, user)
    name = (data.get("name") or "").strip()[:120]''')
rep('''@router.post("/companies/{company_id}/equipment/{equipment_id}/move")''','''def _require_location_editor(user: dict) -> None:
    if (user.get("role") or "").lower() not in ("owner", "manager", "admin", "master_admin", "super_admin", "sales_manager"):
        raise HTTPException(403, "Only managers can change locations")


@router.put("/companies/{company_id}/locations/{location_id}")
async def rename_company_location(company_id: str, location_id: str, data: dict, user=Depends(get_crm_user)):
    _require_location_editor(user)
    org_id = await _company_linked_org(company_id, user)
    name = (data.get("name") or "").strip()[:120]
    if not name:
        raise HTTPException(400, "Location name is required")
    r = await db.sites.update_one({"id": location_id, "organization_id": org_id}, {"$set": {"name": name}})
    if not r.matched_count:
        raise HTTPException(404, "Location not found")
    await db.equipment.update_many({"organization_id": org_id, "site_id": location_id}, {"$set": {"location": name}})
    return {"ok": True}


@router.delete("/companies/{company_id}/locations/{location_id}")
async def remove_company_location(company_id: str, location_id: str, user=Depends(get_crm_user)):
    """Archive an empty location (machines must be moved out first)."""
    _require_location_editor(user)
    org_id = await _company_linked_org(company_id, user)
    if await db.equipment.count_documents({"organization_id": org_id, "site_id": location_id}):
        raise HTTPException(409, "Move the equipment out of this location first")
    r = await db.sites.update_one({"id": location_id, "organization_id": org_id}, {"$set": {"status": "archived"}})
    if not r.matched_count:
        raise HTTPException(404, "Location not found")
    return {"ok": True}


@router.post("/companies/{company_id}/equipment/{equipment_id}/move")''')
rep('''        "totals": {
            "sites": len(site_rows),''','''        "totals": {
            "sites": sum(1 for r in site_rows if not r.get("virtual") and r["id"] != "__unassigned__"),''')
open(p,'w').write(s)

p='/app/frontend/src/pages/CRM/CRMCompanies.js'
s=open(p).read()
i=s.index('data-testid="company-add-contact-email"')
k=s.rfind('>Email', 0, i)
assert k>0
s=s[:k]+'>Email *'+s[k+len('>Email'):]
rep2=[('''              {s.virtual && (
                <span role="button"''','''              {!s.virtual && s.id !== '__unassigned__' && (
                <>
                  <span role="button" tabIndex={0} onClick={(e) => { e.stopPropagation(); renameLocation(s); }} className="text-[10px] underline" style={{ color: c.textDim }} data-testid={`sites-equipment-rename-${s.id}`}>Rename</span>
                  {s.equipment_count === 0 && <span role="button" tabIndex={0} onClick={(e) => { e.stopPropagation(); removeLocation(s); }} className="text-[10px] underline text-red-600" data-testid={`sites-equipment-remove-${s.id}`}>Remove</span>}
                </>
              )}
              {s.virtual && (
                <span role="button"'''),('''  const moveEq = async (eqId, siteId) => {''','''  const renameLocation = async (loc) => {
    const name = window.prompt('Rename location', loc.name);
    if (!name || name.trim() === loc.name) return;
    setLocMsg('');
    try { await axios.put(`${API}/crm/v2/companies/${companyId}/locations/${loc.id}`, { name: name.trim() }, { headers: headers() }); await load(); }
    catch (e) { setLocMsg(e?.response?.data?.detail || 'Could not rename location'); }
  };
  const removeLocation = async (loc) => {
    setLocMsg('');
    try { await axios.delete(`${API}/crm/v2/companies/${companyId}/locations/${loc.id}`, { headers: headers() }); await load(); }
    catch (e) { setLocMsg(e?.response?.data?.detail || 'Could not remove location'); }
  };
  const moveEq = async (eqId, siteId) => {''')]
for a,b in rep2:
    assert s.count(a)==1,(a[:60]); s=s.replace(a,b,1)
open(p,'w').write(s)

p='/app/frontend/src/pages/CRM/Contracts/ModContractsTab.js'
s=open(p).read()
a='''    if (!window.confirm('Delete this MOD contract?')) return;
    await axios.delete(`${API}/crm/v2/mod-contracts/${id}`, { headers: headers() });
    load();'''
assert a in s
s=s.replace(a,'''    if (!window.confirm('Delete this MOD contract?')) return;
    setErr('');
    try { await axios.delete(`${API}/crm/v2/mod-contracts/${id}`, { headers: headers() }); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || 'Could not delete the contract'); }''')
open(p,'w').write(s)
print("ok")
