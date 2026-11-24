"""Offline probe: does _rebuild_master keep the real workbook layout? (no DB writes)"""
import io, time, zipfile, sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from routes.crm_maintenance_master import _rebuild_master
import openpyxl

blob = open("/app/test_reports/mm_tmp/real_mm.xlsx", "rb").read()
t = time.time()
out = _rebuild_master(blob, [("Maintenance Database", 2, "Comments", "PROBE")], [])
print("rebuild secs", round(time.time() - t, 1), "in", len(blob), "out", len(out))
zi, zo = zipfile.ZipFile(io.BytesIO(blob)), zipfile.ZipFile(io.BytesIO(out))
ni, no = set(zi.namelist()), set(zo.namelist())
print("parts lost:", sorted(ni - no)[:40])
for kw in ("chart", "drawing", "media", "vbaProject", "pivot", "table", "externalLink", "comments"):
    print(kw, sum(kw in n for n in ni), "->", sum(kw in n for n in no))
a = openpyxl.load_workbook(io.BytesIO(blob)); b = openpyxl.load_workbook(io.BytesIO(out))
print("sheets same:", a.sheetnames == b.sheetnames)
for s in a.sheetnames:
    wa, wb_ = a[s], b[s]
    fa = sum(1 for r in wa.iter_rows() for c in r if isinstance(c.value, str) and c.value.startswith("="))
    fb = sum(1 for r in wb_.iter_rows() for c in r if isinstance(c.value, str) and c.value.startswith("="))
    print(s, "dims", wa.dimensions, wb_.dimensions, "formulas", fa, fb, "dv", len(wa.data_validations.dataValidation),
          len(wb_.data_validations.dataValidation), "cf", len(list(wa.conditional_formatting)), len(list(wb_.conditional_formatting)))
print("probe cell", b["Maintenance Database"].cell(row=2, column=25).value)
