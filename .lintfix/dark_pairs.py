import json
import re
import sys

KEEP = {("LiteDashboard/staffing/orgchart/Settings.js", 19): "dark:bg-white",
        ("LiteDashboard/staffing/VehiclesTab.js", 734): "dark:text-slate-900"}

RULES = [
    (r"bg-white", "bg-zinc-900"),
    (r"bg-(?:zinc|gray|slate|neutral|stone)-50", "bg-zinc-900"),
    (r"bg-(?:zinc|gray|slate|neutral|stone)-100", "bg-zinc-800"),
    (r"text-(?:zinc|gray|slate|neutral)-900", "text-zinc-100"),
    (r"border-(?:zinc|gray|slate)-(?:100|200)", "border-zinc-800"),
]

d = json.load(open(sys.argv[1]))
for x in d:
    msgs = [m for m in x["messages"] if m.get("ruleId") == "gymaxis/no-dark-mode-leakage"]
    if not msgs:
        continue
    path = x["filePath"]
    rel = path.split("/src/pages/")[-1]
    lines = open(path).read().split("\n")
    for m in msgs:
        ln = m["line"] - 1
        cls = re.search(r"`([^`]+)`", m["message"]).group(1)
        s = lines[ln]
        tok = re.search(r"(?<![\w:-])((?:[a-z-]+:)*)" + re.escape(cls) + r"(?![\w/-])", s)
        if not tok:
            print("MISS", rel, ln + 1, cls)
            continue
        if (rel, ln + 1) in KEEP:
            pair = KEEP[(rel, ln + 1)]
        else:
            pair = next("dark:" + tok.group(1) + dark for pat, dark in RULES if re.fullmatch(pat, cls))
        lines[ln] = s[: tok.end()] + " " + pair + s[tok.end():]
    open(path, "w").write("\n".join(lines))
