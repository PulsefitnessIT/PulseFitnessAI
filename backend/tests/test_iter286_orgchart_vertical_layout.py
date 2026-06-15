"""Iter 286 — Org Chart vertical (stacked) layout.

Covers the bug-fix work:
  * `_vertical_positions` lays a hierarchy out as an indented tree where every
    report stacks below its manager (unique rows) and indents right per depth.
  * New charts default to the `vertical` layout in DEFAULT_SETTINGS.
"""
from routes.staffing_orgchart import _vertical_positions, DEFAULT_SETTINGS, _V_INDENT, _V_ROW


def _nodes():
    # ceo → (mgrA, mgrB); mgrA → eng1, eng2
    return [
        {"id": "ceo", "manager_node_id": None},
        {"id": "mgrA", "manager_node_id": "ceo"},
        {"id": "eng1", "manager_node_id": "mgrA"},
        {"id": "eng2", "manager_node_id": "mgrA"},
        {"id": "mgrB", "manager_node_id": "ceo"},
    ]


def test_default_layout_is_vertical():
    assert DEFAULT_SETTINGS["layout"] == "vertical"


def test_every_node_gets_a_unique_row():
    pos = _vertical_positions(_nodes())
    ys = [pos[n][1] for n in pos]
    assert len(set(ys)) == len(ys), "rows must not overlap — teams stack vertically"


def test_depth_drives_horizontal_indent():
    pos = _vertical_positions(_nodes())
    # root at depth 0, managers at depth 1, engineers at depth 2
    assert pos["ceo"][0] == 0
    assert pos["mgrA"][0] == _V_INDENT
    assert pos["eng1"][0] == 2 * _V_INDENT


def test_reports_stack_directly_below_manager():
    pos = _vertical_positions(_nodes())
    # DFS order: ceo(0), mgrA(1), eng1(2), eng2(3), mgrB(4)
    assert pos["ceo"][1] == 0
    assert pos["mgrA"][1] == _V_ROW
    assert pos["eng1"][1] == 2 * _V_ROW
    assert pos["eng2"][1] == 3 * _V_ROW
    assert pos["mgrB"][1] == 4 * _V_ROW


def test_orphans_and_cycles_still_placed():
    nodes = [
        {"id": "a", "manager_node_id": "missing"},  # orphan → treated as root
        {"id": "b", "manager_node_id": "c"},        # cycle b<->c
        {"id": "c", "manager_node_id": "b"},
    ]
    pos = _vertical_positions(nodes)
    assert set(pos.keys()) == {"a", "b", "c"}
    ys = [pos[n][1] for n in pos]
    assert len(set(ys)) == 3
