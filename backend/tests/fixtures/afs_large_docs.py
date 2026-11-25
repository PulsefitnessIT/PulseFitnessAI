"""Synthetic TEST_ fixtures for large Aftersales document uploads (Build Quote import + custom tender pricing)."""
import io
import os
import random

from PIL import Image


def noise_jpeg(w=330, h=280, seed=0) -> bytes:
    rnd = random.Random(seed)
    img = Image.frombytes("RGB", (w, h), bytes(rnd.getrandbits(8) for _ in range(w * h * 3)))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=95)
    return b.getvalue()


def big_invoice_pdf(pages=20, per_page=20, tag="A", min_bytes=2_600_000) -> bytes:
    """Sales invoice: pages*per_page machine lines ('PF-TR-900 Pulse Fusion Treadmill 900 Qty 2 Serial SN00001') + noise images."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    cv = canvas.Canvas(b, pagesize=A4)
    n = 0
    for p in range(pages):
        y = 800
        hdr = [f"Pulse Fitness Limited - Sales Invoice TEST_{tag}-{p + 1}", "Invoice No: TEST-INV-9001  Date: 12/03/2026",
               "Customer: TEST_ Brightwater Leisure Trust Ltd", "Item code | Description | Qty | Serial"]
        for line in hdr:
            cv.drawString(40, y, line)
            y -= 16
        for _ in range(per_page):
            n += 1
            cv.drawString(40, y, f"PF-TR-900 Pulse Fusion Treadmill 900 Qty 2 Serial SN{tag}{n:05d}")
            y -= 16
        cv.drawImage(ImageReader(io.BytesIO(noise_jpeg(seed=hash((tag, p)) & 0xFFFF))), 40, 40, width=300, height=200)
        cv.showPage()
    cv.save()
    data = b.getvalue()
    assert len(data) >= min_bytes, len(data)
    return data


def tender_csv(rows=700) -> bytes:
    out = ["Section,Machine type,Price"]
    for i in range(rows):
        out.append(f"Service Prices,TEST Machine Type {i + 1:03d} Treadmill model - commercial cardio unit incl PPM visit and safety check,{10 + (i % 90)}.{i % 100:02d}")
    for i in range(20):
        out.append(f"Travel,TEST Site Town {i + 1:02d},{40 + i}.00")
    for i in range(5):
        out.append(f"Repair Labour,TEST Repair Type {i + 1},{25 + i}.00")
    return ("\n".join(out) + "\n").encode()


if __name__ == "__main__":
    os.makedirs("/tmp/afs", exist_ok=True)
    pdf = big_invoice_pdf()
    open("/tmp/afs/TEST_big_invoice.pdf", "wb").write(pdf)
    open("/tmp/afs/TEST_big_invoice_ui.pdf", "wb").write(big_invoice_pdf(tag="U"))
    open("/tmp/afs/TEST_tender_700.csv", "wb").write(tender_csv())
    print(len(pdf), len(tender_csv()))
