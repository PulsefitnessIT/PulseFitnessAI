import json
import sys

d = json.load(open(sys.argv[1]))
for x in d:
    msgs = [m for m in x["messages"] if m.get("ruleId") == "unused-imports/no-unused-vars"]
    if not msgs:
        continue
    path = x["filePath"]
    src = open(path).read()
    lines = src.split("\n")
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln) + 1)
    edits = []
    for m in msgs:
        pos = offs[m["line"] - 1] + m["column"] - 1
        name = m["message"].split("'")[1]
        assert src[pos:pos + len(name)] == name, (path, m)
        depth = 0
        i = pos - 1
        enclosing = None
        while i >= 0:
            c = src[i]
            if c in ")]}":
                depth += 1
            elif c in "([{":
                if depth == 0:
                    enclosing = c
                    break
                depth -= 1
            i -= 1
        j = pos - 1
        while j >= 0 and src[j] in " \t\n":
            j -= 1
        k = pos + len(name)
        while k < len(src) and src[k] in " \t\n":
            k += 1
        shorthand = enclosing == "{" and src[j] in "{," and src[k] != ":"
        new = f"{name}: _{name}" if shorthand else f"_{name}"
        edits.append((pos, len(name), new))
    for pos, n, new in sorted(edits, reverse=True):
        src = src[:pos] + new + src[pos + n:]
    open(path, "w").write(src)
