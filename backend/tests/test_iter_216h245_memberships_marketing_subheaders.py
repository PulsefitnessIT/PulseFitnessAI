"""Iter 216h245 — Remaining sub-headers: Memberships + Marketing.

The user spotted three holdouts after the iter h243/h244 sweeps:

- Memberships → Invoicing: BILLING eyebrow + "Monthly class invoicing" H1 + description.
- Memberships → Desk sales: "Desk sales reconciliation" H2 + description.
- Marketing → Dynamic Lists: "Dynamic Lists" H2 (kept the "What is a
  Dynamic List?" explainer — that's onboarding content, not a sub-header).

This test guards against regression.
"""
from __future__ import annotations

import pathlib


def test_invoicing_subheader_removed():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/InvoicingTab.js").read_text()
    assert ">Monthly class invoicing<" not in src, "Monthly class invoicing H1 must be gone"
    assert ">Billing<" not in src, "Billing eyebrow must be gone"
    assert "Bill every member for the classes they booked" not in src, "description must be gone"


def test_desk_sales_subheader_removed():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/DeskSalesReportTab.js").read_text()
    assert "Desk sales reconciliation" not in src, "Desk sales H2 must be gone"
    assert "Every pack sold at the front desk" not in src, "description must be gone"


def test_dynamic_lists_h2_removed_but_explainer_kept():
    src = pathlib.Path("/app/frontend/src/pages/Marketing/DynamicListsTab.js").read_text()
    # H2 with the inline ListChecks icon must be gone.
    assert "<ListChecks size={18} className=\"text-fuchsia-500\" /> Dynamic Lists" not in src
    # Explainer block must remain.
    assert "What is a Dynamic List?" in src, "explainer must NOT have been removed"
