import ast
import sys


def indent_of(line):
    return line[: len(line) - len(line.lstrip())]


def bodies(node):
    for field in ("body", "orelse", "finalbody"):
        val = getattr(node, field, None)
        if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
            yield val


def fix_once(src):
    tree = ast.parse(src)
    lines = src.split("\n")
    fixes = {}
    for parent in ast.walk(tree):
        for body in bodies(parent):
            for stmt in body:
                ln = stmt.lineno - 1
                raw = lines[ln].encode()
                prefix = raw[: stmt.col_offset].decode().rstrip()
                if not prefix.strip():
                    continue
                if prefix.endswith(";"):
                    ind = indent_of(lines[ln])
                    cut = prefix[:-1].rstrip()
                elif prefix.endswith(":"):
                    hdr = getattr(parent, "lineno", ln + 1) - 1
                    ind = indent_of(lines[hdr]) + "    "
                    cut = prefix
                else:
                    continue
                if isinstance(stmt.col_offset, int) and (ln not in fixes or fixes[ln][0] > stmt.col_offset):
                    rest = raw[stmt.col_offset :].decode()
                    fixes[ln] = (stmt.col_offset, cut, ind + rest)
    if not fixes:
        return src, False
    for ln in sorted(fixes, reverse=True):
        _, cut, rest = fixes[ln]
        lines[ln : ln + 1] = [cut, rest]
    return "\n".join(lines), True


for path in sys.argv[1:]:
    src = open(path).read()
    changed_any = False
    while True:
        src, changed = fix_once(src)
        if not changed:
            break
        changed_any = True
    if changed_any:
        ast.parse(src)
        open(path, "w").write(src)
        print("fixed", path)
