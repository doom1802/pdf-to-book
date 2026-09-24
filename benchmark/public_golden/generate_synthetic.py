"""Generate the original, redistributable layout stress fixture.

This developer tool needs ReportLab; the committed PDF is used by CI without
ReportLab. ``invariant=1`` makes repeated generation byte-for-byte stable.
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


OUTPUT = Path(__file__).with_name("pdfs") / "layout-stress.pdf"


def lines(pdf, x, y, content, *, font="Helvetica", size=10, leading=16):
    pdf.setFont(font, size)
    for line in content:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(OUTPUT), pagesize=A4, invariant=1)
    pdf.setTitle("Public golden: layout stress")
    pdf.setAuthor("pdf-to-book contributors")
    width, _ = A4

    pdf.setFont("Helvetica", 9)
    pdf.drawString(55, 806, "REGRESSION ATLAS  |  technical note")
    pdf.line(55, 796, width - 55, 796)
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(55, 752, "Reading order under stress")
    lines(pdf, 55, 725, [
        "Two columns, a merged table header, code, a figure, and a footnote",
        "must survive conversion into a reflowable book.",
    ])

    left, right = 55, 315
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(left, 660, "1. Input sequence")
    pdf.drawString(right, 660, "2. Output sequence")
    lines(pdf, left, 635, [
        "The copper marker starts the left column.",
        "Read every left-column block before moving",
        "to the right column. A soft line break is not",
        "a new paragraph. The key has three steps:",
    ])
    lines(pdf, left + 11, 552, [
        "1. Capture the source characters.",
        "2. Preserve the code indentation.",
        "3. Keep the footnote reference [1].",
    ], leading=19)
    lines(pdf, right, 635, [
        "The violet marker starts the right column.",
        "The table has a header spanning three cells.",
        "Its numeric values must stay in their rows.",
        "Then the diagram follows the table.",
    ])

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, 470, "Listing 1. XML-safe output")
    pdf.rect(left, 318, 230, 139, stroke=1, fill=0)
    lines(pdf, left + 10, 434, [
        "def escape(value):",
        "    if value < 0:",
        "        return \"<none>\"",
        "    return f\"{value}&ok\"",
    ], font="Courier", size=9, leading=20)

    table_left, table_top, table_width = right, 551, 230
    row_height = 31
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(table_left + table_width / 2, table_top - 21, "Merged measurement header")
    pdf.line(table_left, table_top - row_height, table_left + table_width, table_top - row_height)
    for index in range(4):
        y = table_top - (index + 1) * row_height
        pdf.line(table_left, y, table_left + table_width, y)
    for x in (table_left, table_left + table_width):
        pdf.line(x, table_top, x, table_top - 4 * row_height)
    for x in (table_left + 77, table_left + 154):
        pdf.line(x, table_top - row_height, x, table_top - 4 * row_height)
    pdf.setFont("Helvetica", 9)
    for row, cells in enumerate((
        ("Item", "Input", "Output"),
        ("alpha", "2", "4"),
        ("beta", "5", "25"),
    ), start=1):
        for col, cell in enumerate(cells):
            pdf.drawString(table_left + 7 + col * 77, table_top - row * row_height - 20, cell)

    pdf.setFont("Helvetica", 9)
    pdf.drawString(left, 285, "Literal tags <book> and ampersands & remain text.")
    pdf.drawString(left, 264, "The goldfinch marker ends the left column.")
    pdf.drawString(right, 393, "Figure 1. Two stages in reading order")
    pdf.roundRect(right + 7, 311, 88, 54, 5, stroke=1, fill=0)
    pdf.roundRect(right + 137, 311, 88, 54, 5, stroke=1, fill=0)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(right + 51, 336, "SOURCE")
    pdf.drawCentredString(right + 181, 336, "EPUB")
    pdf.line(right + 96, 338, right + 129, 338)
    pdf.line(right + 129, 338, right + 123, 341)
    pdf.line(right + 129, 338, right + 123, 335)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(right, 280, "The indigo marker ends the right column.")

    pdf.line(55, 141, width - 55, 141)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(55, 125, "[1] This note belongs to the list, not to the page furniture.")
    pdf.drawString(55, 38, "PUBLIC GOLDEN FIXTURE")
    pdf.drawRightString(width - 55, 38, "1")
    pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    main()
