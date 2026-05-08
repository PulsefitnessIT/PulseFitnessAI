"""Iter 215z — Sibling discount regression tests.

Unit-tests the pure helper ``_apply_sibling_discount`` so we don't need
full Mongo fixtures. Endpoints are covered by the live testing agent.
"""
from routes.memberships.studio_billing import _apply_sibling_discount


def _class_line(amount: int, sub_id: str, att_name: str, booking_id: str) -> dict:
    return {
        "kind": "class",
        "description": f"Yoga · {att_name}",
        "amount_pence": amount,
        "attendee_name": att_name,
        "attendee_kind": "sub_profile",
        "attendee_sub_profile_id": sub_id,
        "booking_id": booking_id,
    }


def test_no_discount_when_pct_zero():
    lines = [_class_line(1500, "kid-a", "Alice", "b1")]
    out, delta = _apply_sibling_discount(lines, [{"id": "b1"}], 0)
    assert delta == 0
    assert len(out) == 1


def test_no_discount_with_single_sibling():
    lines = [_class_line(1500, "kid-a", "Alice", "b1")]
    out, delta = _apply_sibling_discount(lines, [{"id": "b1"}], 10)
    assert delta == 0
    assert len(out) == 1


def test_no_discount_when_no_sub_profile():
    # Solo adult member booking their own classes — kind != sub_profile.
    lines = [
        {"kind": "class", "amount_pence": 1500, "booking_id": "b1"},
        {"kind": "class", "amount_pence": 1500, "booking_id": "b2"},
    ]
    out, delta = _apply_sibling_discount(lines, [{"id": "b1"}, {"id": "b2"}], 10)
    assert delta == 0
    assert len(out) == 2


def test_two_siblings_apply_pct():
    lines = [
        _class_line(2000, "kid-a", "Alice", "b1"),
        _class_line(2000, "kid-a", "Alice", "b2"),  # Alice total = 4000
        _class_line(3000, "kid-b", "Bob", "b3"),    # Bob total = 3000
    ]
    out, delta = _apply_sibling_discount(lines, [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}], 10)
    # Alice is 1st (earliest booking b1), Bob is 2nd → 10% off Bob's 3000 = -300
    assert delta == -300
    assert len(out) == 4  # 3 class lines + 1 discount line
    disc = out[-1]
    assert disc["kind"] == "sibling_discount"
    assert disc["amount_pence"] == -300
    assert disc["attendee_sub_profile_id"] == "kid-b"
    assert disc["attendee_name"] == "Bob"
    assert disc["sibling_rank"] == 2


def test_three_siblings_all_discounted():
    lines = [
        _class_line(1000, "kid-a", "Alice", "b1"),
        _class_line(2000, "kid-b", "Bob", "b2"),
        _class_line(4000, "kid-c", "Cara", "b3"),
    ]
    out, delta = _apply_sibling_discount(lines, [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}], 20)
    # 20% off Bob (2000) = -400; 20% off Cara (4000) = -800 → total -1200
    assert delta == -1200
    assert sum(1 for ln in out if ln["kind"] == "sibling_discount") == 2


def test_ordering_uses_first_booking():
    # Bob was booked first (b1), then Alice (b2). Bob should be free, Alice discounted.
    lines = [
        _class_line(3000, "kid-b", "Bob", "b1"),
        _class_line(2000, "kid-a", "Alice", "b2"),
    ]
    out, delta = _apply_sibling_discount(lines, [{"id": "b1"}, {"id": "b2"}], 25)
    # Alice is 2nd → 25% off 2000 = -500
    assert delta == -500
    disc = [ln for ln in out if ln["kind"] == "sibling_discount"]
    assert len(disc) == 1
    assert disc[0]["attendee_sub_profile_id"] == "kid-a"


def test_rounding_floors():
    # 3 × 1000 = 3000 on Bob. 33% → 990 (floor division 3000*33//100 = 990).
    lines = [
        _class_line(1500, "kid-a", "Alice", "b1"),
        _class_line(1000, "kid-b", "Bob", "b2"),
        _class_line(1000, "kid-b", "Bob", "b3"),
        _class_line(1000, "kid-b", "Bob", "b4"),
    ]
    out, delta = _apply_sibling_discount(lines, [{"id": bid} for bid in ["b1", "b2", "b3", "b4"]], 33)
    assert delta == -990


def test_label_2nd_3rd_ordinals():
    lines = [
        _class_line(1000, "kid-a", "A", "b1"),
        _class_line(1000, "kid-b", "B", "b2"),
        _class_line(1000, "kid-c", "C", "b3"),
        _class_line(1000, "kid-d", "D", "b4"),
    ]
    out, delta = _apply_sibling_discount(lines, [{"id": bid} for bid in ["b1", "b2", "b3", "b4"]], 10)
    disc = [ln for ln in out if ln["kind"] == "sibling_discount"]
    descs = " ".join(d["description"] for d in disc)
    assert "2nd child" in descs
    assert "3rd child" in descs
    assert "4th child" in descs
