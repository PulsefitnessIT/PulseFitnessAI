import ast
import io
import re
import sys
import tokenize
NEW = sys.argv[1] if False else "ln"


def rename_l(src):
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    lines = src.split("\n")
    edits = []
    for i, t in enumerate(toks):
        if t.type != tokenize.NAME or t.string != "l":
            continue
        prev = toks[i - 1].string if i else ""
        nxt = toks[i + 1].string if i + 1 < len(toks) else ""
        if prev == "." or nxt == "=":
            continue
        edits.append(t.start)
    for row, col in sorted(edits, reverse=True):
        s = lines[row - 1]
        lines[row - 1] = s[:col] + NEW + s[col + 1 :]
    return "\n".join(lines)


def lambdas_to_defs(src):
    tree = ast.parse(src)
    lines = src.split("\n")
    targets = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Lambda)
            and node.lineno == node.end_lineno
        ):
            targets.append(node)
    for node in sorted(targets, key=lambda n: n.lineno, reverse=True):
        line = lines[node.lineno - 1]
        indent = line[: len(line) - len(line.lstrip())]
        lam = node.value
        raw = line.encode()
        args = raw[lam.col_offset + len("lambda") : lam.body.col_offset].decode().strip().rstrip(":").strip()
        body = ast.get_source_segment(src, lam.body)
        name = node.targets[0].id
        lines[node.lineno - 1 : node.lineno] = [f"{indent}def {name}({args}):", f"{indent}    return {body}"]
    return "\n".join(lines)


for path in sys.argv[1:]:
    src = open(path).read()
    if re.search(r"\bln\b", src) is None:
        src = rename_l(src)
    src = lambdas_to_defs(src)
    src = re.sub(r"'\{%s\}(\w+)' % W", r"f'{{{W}}}\1'", src)
    ast.parse(src)
    open(path, "w").write(src)
