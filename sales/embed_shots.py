"""Embed real screenshots into the .mock browser frames of both decks.

Replaces the inner `<div class="body">…</div>` of a mock (identified by its
bar label) with a full-bleed screenshot, keeping the browser chrome bar.
Div-depth aware so nested wireframe markup is removed cleanly.
"""
import re

CSS_RULE = (
    "\n.mock .body.shot{ padding:0; line-height:0; background:#fff; }"
    "\n.mock .body.shot img{ display:block; width:100%; height:auto; }"
)

SHOTS = "/app/sales/shots/final"

PLAN = {
    "/app/sales/gymaxisai_operators.html": [
        ("CRM · Sales Pipeline", f"{SHOTS}/crm.png", "GymAxis CRM sales pipeline — Apex Fitness Group"),
        ("Operations · Equipment", f"{SHOTS}/equipment.png", "GymAxis Operations equipment register"),
        ("Memberships · Today", f"{SHOTS}/memberships.png", "GymAxis Memberships analytics"),
    ],
    "/app/sales/gymaxisai_engineers.html": [
        ("Service Desk · Open cases", f"{SHOTS}/servicedesk.png", "GymAxis engineer job dashboard"),
        ("Asset · Service history", f"{SHOTS}/faults.png", "GymAxis asset fault & service log"),
    ],
}


def find_body_span(html, start):
    """Return (open_idx, close_end) of the first <div class="body" ...> after start."""
    open_idx = html.index('<div class="body"', start)
    i = open_idx
    depth = 0
    token = re.compile(r"<div\b|</div>")
    for m in token.finditer(html, open_idx):
        if m.group() == "</div>":
            depth -= 1
            if depth == 0:
                return open_idx, m.end()
        else:
            depth += 1
    raise ValueError("unbalanced div")


def main():
    for path, items in PLAN.items():
        html = open(path).read()
        # add css once
        if ".mock .body.shot" not in html:
            html = html.replace(
                ".mline{ height:11px; border-radius:6px; background:#EEF2F9; }",
                ".mline{ height:11px; border-radius:6px; background:#EEF2F9; }" + CSS_RULE,
                1,
            )
        for label, src, alt in items:
            anchor = html.index(label)
            open_idx, close_end = find_body_span(html, anchor)
            new_body = f'<div class="body shot"><img src="{src}" alt="{alt}"></div>'
            html = html[:open_idx] + new_body + html[close_end:]
            print("embedded:", label, "->", src.split("/")[-1])
        open(path, "w").write(html)
    print("done")


if __name__ == "__main__":
    main()
