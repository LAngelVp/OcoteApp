import csv
import io
import math
import stat
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from xml.sax.saxutils import escape

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import iterparse
from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from app.core.errors import CommandError
from app.services.exports import neutralize

MAX_ROWS, MAX_COLUMNS = 1000, 100
MAX_COMPRESSED, MAX_EXPANDED, MAX_CELLS = 10485760, 67108864, 100000


@dataclass(frozen=True)
class ImportLimits:
    rows: int
    bytes: int

    def __post_init__(self):
        if type(self.rows) is not int or type(self.bytes) is not int or not (
            1 <= self.rows <= MAX_ROWS and 1 <= self.bytes <= MAX_COMPRESSED
        ):
            raise CommandError(409, "CONFIGURATION_INCOMPLETE")


def formula_text(value):
    return isinstance(value, str) and neutralize(value.lstrip("\ufeff\u200b")) != (
        value.lstrip("\ufeff\u200b")
    )


def plain_cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime) and value.tzinfo is None and not any((
        value.hour, value.minute, value.second, value.microsecond,
    )):
        return value.date().isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        raise CommandError(422, "IMPORT_CELL_INVALID")
    if not isinstance(value, (str, int, float, Decimal)):
        raise CommandError(422, "IMPORT_CELL_INVALID")
    result = str(value)
    if len(result) > 10000 or any(ord(char) < 32 and char not in "\t\r\n" for char in result):
        raise CommandError(422, "IMPORT_CELL_INVALID")
    if formula_text(result):
        raise CommandError(422, "IMPORT_FORMULA_FORBIDDEN")
    return result


def inspect_xlsx(content, limits):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if not 1 <= len(entries) <= 1024 or len(names) != len(set(names)):
            raise CommandError(422, "IMPORT_ARCHIVE_INVALID")
        expanded = sum(entry.file_size for entry in entries)
        if expanded > MAX_EXPANDED or expanded > max(1, len(content)) * 100:
            raise CommandError(413, "IMPORT_ARCHIVE_TOO_LARGE")
        if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
            raise CommandError(422, "IMPORT_ARCHIVE_INVALID")
        cells = 0
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (
                path.is_absolute() or ".." in path.parts or "\\" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1
                or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                or entry.file_size > max(1, entry.compress_size) * 100
                or any(word in entry.filename.lower() for word in (
                    "vbaproject", "externallinks", "activex", "embeddings", "connections",
                ))
            ):
                raise CommandError(422, "IMPORT_ARCHIVE_INVALID")
            if entry.is_dir():
                continue
            if path.suffix not in {".xml", ".rels"} and entry.filename != "_rels/.rels":
                raise CommandError(422, "IMPORT_ACTIVE_CONTENT_FORBIDDEN")
            with archive.open(entry) as stream:
                for event, element in iterparse(
                    stream, events=("start", "end"), forbid_dtd=True,
                    forbid_entities=True, forbid_external=True,
                ):
                    tag = element.tag.rsplit("}", 1)[-1]
                    if event == "start":
                        if tag in {"f", "definedName", "mergeCell"} or (
                            element.attrib.get("TargetMode", "").lower() == "external"
                            or "macroenabled" in element.attrib.get("ContentType", "").lower()
                            or "vba" in element.attrib.get("ContentType", "").lower()
                        ):
                            raise CommandError(422, "IMPORT_ACTIVE_CONTENT_FORBIDDEN")
                        if tag == "c" and entry.filename.startswith("xl/worksheets/"):
                            coordinate, row = coordinate_from_string(element.attrib.get("r", ""))
                            cells += 1
                            if row > limits.rows + 1 or (
                                column_index_from_string(coordinate) > MAX_COLUMNS
                                or cells > MAX_CELLS
                            ):
                                raise CommandError(413, "IMPORT_TOO_LARGE")
                    else:
                        element.clear()


def parse_table(content, file_format, limits):
    if not isinstance(content, bytes) or not content or len(content) > limits.bytes:
        raise CommandError(413, "IMPORT_TOO_LARGE")
    workbook = None
    try:
        if file_format == "csv":
            text = content.decode("utf-8-sig", errors="strict")
            if "\x00" in text:
                raise CommandError(422, "IMPORT_CELL_INVALID")
            iterator = csv.reader(io.StringIO(text, newline=""), strict=True)
        elif file_format == "xlsx":
            inspect_xlsx(content, limits)
            workbook = load_workbook(
                io.BytesIO(content), read_only=True, data_only=False, keep_links=False,
            )
            if len(workbook.worksheets) != 1 or workbook.worksheets[0].sheet_state != "visible":
                raise CommandError(422, "IMPORT_SINGLE_SHEET_REQUIRED")
            sheet = workbook.worksheets[0]
            sheet.reset_dimensions()
            iterator = sheet.iter_rows(values_only=True)
        else:
            raise CommandError(422, "IMPORT_FORMAT_INVALID")
        headers = [plain_cell(value).strip() for value in next(iterator)]
        if (
            not 1 <= len(headers) <= MAX_COLUMNS or len(headers) != len(set(headers))
            or any(not value or len(value) > 160 for value in headers)
        ):
            raise CommandError(422, "IMPORT_HEADERS_INVALID")
        rows, cells = [], len(headers)
        for raw in iterator:
            cells += len(raw)
            if len(rows) >= limits.rows or cells > MAX_CELLS:
                raise CommandError(413, "IMPORT_TOO_LARGE")
            if len(raw) != len(headers):
                raise CommandError(422, "IMPORT_COLUMNS_INVALID")
            rows.append([plain_cell(value) for value in raw])
        if not rows:
            raise CommandError(422, "IMPORT_EMPTY")
        return headers, rows
    except CommandError:
        raise
    except (ValueError, KeyError, TypeError, UnicodeError, StopIteration, csv.Error,
            zipfile.BadZipFile, DefusedXmlException, OSError, SyntaxError):
        raise CommandError(422, "IMPORT_FORMAT_INVALID") from None
    finally:
        if workbook is not None:
            workbook.close()


def xlsx_report(columns, rows, context, maximum):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("OCOTE")

    def append(values):
        cells = []
        for value in values:
            value = neutralize(str(value)) if value is not None else ""
            cell = WriteOnlyCell(sheet, value=value)
            cell.data_type = "s"
            cell.quotePrefix = True
            cells.append(cell)
        sheet.append(cells)

    append(columns)
    for row in rows:
        append(row)
    metadata = workbook.create_sheet("Contexto")
    for key, value in context.items():
        safe = neutralize(str(value))
        cell = WriteOnlyCell(metadata, value=safe)
        cell.data_type = "s"
        cell.quotePrefix = True
        metadata.append([key, cell])
    content = io.BytesIO()
    workbook.save(content)
    workbook.close()
    result = content.getvalue()
    if len(result) > maximum:
        raise CommandError(413, "EXPORT_TOO_LARGE")
    return result


def pdf_report(columns, rows, context, maximum):
    from pathlib import Path

    name = "OCOTE-Vera"
    if name not in pdfmetrics.getRegisteredFontNames():
        path = next(Path(folder) / "Vera.ttf" for folder in rl_config.TTFSearchPath
                    if (Path(folder) / "Vera.ttf").is_file())
        pdfmetrics.registerFont(TTFont(name, str(path)))
    font = pdfmetrics.getFont(name)
    values = [str(value if value is not None else "") for row in rows for value in row]
    values.extend(str(value) for value in context.values())
    if any(ord(character) not in font.face.charToGlyph for value in values
           for character in value if not character.isspace()):
        raise CommandError(422, "REPORT_UNSUPPORTED_CHARACTERS")
    style = ParagraphStyle("OCOTE", fontName=name, fontSize=8, leading=11)
    title = ParagraphStyle("Title", parent=style, fontSize=15, leading=20)
    content = io.BytesIO()
    document = SimpleDocTemplate(
        content, pagesize=landscape(A4), leftMargin=28, rightMargin=28,
        topMargin=28, bottomMargin=28, title="OCOTE", author="OCOTE",
    )
    elements = [Paragraph("OCOTE", title), Spacer(1, 10)]
    elements.extend(Paragraph(escape(str(key)) + ": " + escape(str(value)), style)
                    for key, value in context.items())
    elements.append(Spacer(1, 12))
    table = LongTable(
        [[Paragraph(escape(str(value if value is not None else "")), style) for value in row]
         for row in [columns, *rows]], repeatRows=1, hAlign="LEFT",
        colWidths=[(landscape(A4)[0] - 56) / len(columns)] * len(columns),
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3ECE6")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#506057")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    document.build([*elements, table])
    result = content.getvalue()
    if len(result) > maximum:
        raise CommandError(413, "EXPORT_TOO_LARGE")
    return result