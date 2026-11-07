import csv
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def export_csv(headers, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def export_pdf(title, headers, rows):
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    _width, height = A4

    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, height - 50, title)

    y = height - 85
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, y, " | ".join(map(str, headers)))
    y -= 20

    pdf.setFont("Helvetica", 8)
    for row in rows:
        if y < 50:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 8)

        pdf.drawString(
            40,
            y,
            " | ".join(str(value) for value in row)[:130],
        )
        y -= 15

    pdf.save()
    return output.getvalue()
