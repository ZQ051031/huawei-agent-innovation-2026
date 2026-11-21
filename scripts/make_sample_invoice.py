from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def main():
    target = Path(__file__).resolve().parents[1] / "project/samples/05-print-invoice.pdf"
    pdf = canvas.Canvas(str(target), pagesize=A4, invariant=1)
    pdf.setTitle("Fictional invoice: Loess Print Shop")
    pdf.setFillColor(HexColor("#123830"))
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(65, 753, "INVOICE")
    pdf.setFont("Helvetica", 13)
    for index, line in enumerate((
        "Vendor: Loess Print Shop", "Invoice No: LP-221", "Date: 2026-11-20", "Currency: CNY",
        "Description: Printer paper and business stationery", "Subtotal: 105.00", "Tax: 5.00",
        "Grand total: 110.00", "Fictional demonstration invoice - not for payment."
    )):
        pdf.drawString(65, 712 - index * 26, line)
    pdf.save()


if __name__ == "__main__":
    main()
