"""Generate a small labelled sample set: samples/<label>/*.pdf (needs reportlab).

Synthetic documents are only good for smoke-testing the pipeline. Measure real accuracy on
your own PDFs: put 10-30 per label into <dir>/<label>/ and run `pdfclf evaluate <dir>`.
"""
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DOCS = {
    "invoice": [
        "Rechnung Nr. 2026-0412\nStadtwerke Musterstadt GmbH\nRechnungsbetrag: 84,20 EUR inkl. 20% USt.\n"
        "Zahlbar bis 30.10.2026 auf IBAN AT12 3456 7890 1234 5678.\nZahlungsbedingungen: 14 Tage netto.",
        "INVOICE #INV-88213\nAcme Cloud Ltd.\nAmount due: USD 129.00 (VAT 0%)\nPayment terms: due within 30 days.\n"
        "Please pay by November 12, 2026.",
    ],
    "receipt": [
        "Kassenbon\nSupermarkt Billig\n2x Milch 2,58\nBrot 3,10\nSumme bezahlt: 5,68 EUR\nBar bezahlt. Danke für Ihren Einkauf!",
        "RECEIPT\nCoffee House\nPaid: 7.40 EUR with card ****1234\nThank you, payment received.",
    ],
    "contract": [
        "Mietvertrag\nzwischen Vermieter Max Muster und Mieterin Erika Beispiel.\n§1 Mietgegenstand ...\n"
        "§5 Vertragsdauer: unbefristet. Kündigung mit einer Frist von drei Monaten.\nUnterschrift beider Parteien.",
        "SERVICE AGREEMENT\nThis agreement is made between the parties Contoso Inc. and the Client.\n"
        "Term: 24 months. Termination requires 90 days written notice. Signatures of both parties.",
    ],
    "bank_statement": [
        "Kontoauszug Nr. 9/2026\nIBAN AT61 1904 3002 3457 3201\nAlter Kontostand 1.230,55\n"
        "Umsätze: Gehalt +2.900,00 / Miete -950,00 / Lastschrift -84,20\nNeuer Kontostand 3.096,35",
        "ACCOUNT STATEMENT September 2026\nAccount IBAN GB29 NWBK 6016 1331 9268 19\nOpening balance 2,100.00\n"
        "Transactions: card payment -45.10, transfer +500.00\nClosing balance 2,554.90",
    ],
    "payslip": [
        "Lohn- und Gehaltsabrechnung September 2026\nMitarbeiter: Erika Beispiel\nBrutto: 4.200,00\n"
        "Lohnsteuer -612,00  Sozialversicherung -760,00\nNetto: 2.828,00",
        "PAYSLIP October 2026\nEmployee: John Doe\nGross salary 5,000.00\nDeductions: income tax 1,050.00, pension 250.00\nNet pay 3,700.00",
    ],
}


def write_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in text.splitlines():
        c.drawString(60, y, line)
        y -= 18
    c.save()


def main(out: str = "samples") -> None:
    root = Path(out)
    for label, texts in DOCS.items():
        (root / label).mkdir(parents=True, exist_ok=True)
        for i, t in enumerate(texts, 1):
            write_pdf(root / label / f"{label}_{i}.pdf", t)
    # an image-only/blank PDF to exercise the "no text" path
    blank = root / "_unlabelled_scan.pdf"
    canvas.Canvas(str(blank), pagesize=A4).save()
    print(f"wrote samples to {root}/")


if __name__ == "__main__":
    main(*sys.argv[1:])
