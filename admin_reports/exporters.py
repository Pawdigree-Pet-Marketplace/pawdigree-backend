from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NUMBER_FORMATS = {"money": "#,##0.00", "count": "#,##0", "percent": '0.0"%"'}


def _cell(value, fmt):
    """Excel gets real numbers, so admins can sort and sum them."""
    if value is None:
        return ""
    if fmt == "money":
        return Decimal(str(value))
    return value


def _text(value, fmt):
    """PDF gets display text."""
    if value is None:
        return ""
    if fmt == "money":
        return f"{Decimal(str(value)):,.2f}"
    if fmt == "percent":
        return f"{value}%"
    if fmt == "count":
        return f"{int(value):,}"
    return str(value)


# ---------- Excel ----------

def to_xlsx(report):
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="DDE7F5")

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([report["title"]])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Generated at", report["generated_at"]])
    ws.append(["Currency", report["currency"]])
    for key, value in report["filters"].items():
        ws.append([f"Filter: {key}", str(value)])
    ws.append([])
    ws.append(["Metric", "Value"])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = header_font, header_fill
    for item in report["summary"]:
        ws.append([item["label"], _cell(item["value"], item["format"])])
        ws.cell(ws.max_row, 2).number_format = NUMBER_FORMATS.get(
            item["format"], "General"
        )
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 28

    for sec in report["sections"]:
        sheet = wb.create_sheet(title=sec["title"][:31])  # Excel's limit
        columns = sec["columns"]
        sheet.append([c["label"] for c in columns])
        for cell in sheet[1]:
            cell.font, cell.fill = header_font, header_fill
        for row in sec["rows"]:
            sheet.append([_cell(row.get(c["key"]), c["format"]) for c in columns])
            for index, c in enumerate(columns, start=1):
                sheet.cell(sheet.max_row, index).number_format = (
                    NUMBER_FORMATS.get(c["format"], "General")
                )
        for index in range(1, len(columns) + 1):
            sheet.column_dimensions[chr(64 + index)].width = 28 if index == 1 else 18

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------- PDF ----------

def to_pdf(report):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), title=report["title"],
        leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8, leading=10)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold")
    grid = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE7F5")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C2D0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])

    def p(text, style=cell):
        return Paragraph(escape(str(text)), style)   # escape: names may hold "&"

    filters = ", ".join(f"{k}: {v}" for k, v in report["filters"].items())
    story = [
        Paragraph(escape(report["title"]), styles["Title"]),
        p(f"Generated {report['generated_at']} | Currency {report['currency']}"),
        p(f"Filters: {filters}"),
        Spacer(1, 12),
    ]

    summary = [[p("Metric", head), p("Value", head)]] + [
        [p(i["label"]), p(_text(i["value"], i["format"]))] for i in report["summary"]
    ]
    table = Table(summary, colWidths=[300, 160], hAlign="LEFT")
    table.setStyle(grid)
    story.append(table)

    for sec in report["sections"]:
        story += [Spacer(1, 14), Paragraph(escape(sec["title"]), styles["Heading3"])]
        if not sec["rows"]:
            story.append(Paragraph("No data for this period.", styles["Italic"]))
            continue
        columns = sec["columns"]
        data = [[p(c["label"], head) for c in columns]] + [
            [p(_text(row.get(c["key"]), c["format"])) for c in columns]
            for row in sec["rows"]
        ]
        table = Table(data, repeatRows=1)   # header repeats on each page
        table.setStyle(grid)
        story.append(table)

    doc.build(story)
    return buffer.getvalue()


def export_response(report, fmt, filename):
    if fmt == "xlsx":
        content, content_type = to_xlsx(report), XLSX_TYPE
    else:
        content, content_type = to_pdf(report), "application/pdf"
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}.{fmt}"'
    return response