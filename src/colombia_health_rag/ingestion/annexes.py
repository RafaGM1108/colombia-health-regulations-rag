"""Read reviewed regulation annexes as provenance-aware sections."""

import re
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise
from pathlib import Path

import pymupdf

from colombia_health_rag.ingestion.articles import ArticleParseError, parse_resolution
from colombia_health_rag.ingestion.manifest import SourceRecord

_ANNEX = re.compile(r"^ANEXO\s+T[ÉE]CNICO$", re.IGNORECASE)
_INTRODUCTION = re.compile(r"^INTRODUC\w{3,8}$", re.IGNORECASE)
_HEADING = re.compile(r"^(\d{1,2}(?:[.,]\d{1,2}){0,4})\.?\s+(.+)$")
_NUMBER_ONLY = re.compile(r"^\d{1,2}(?:[.,]\d{1,2}){0,4}\.?$")
_CODE = re.compile(r"^[A-Z0-9-]{3,6}$", re.IGNORECASE)
_SIGNING = re.compile(r"^(?:APRO\w*|REVI\w*|PROYE\w*|ELABO\w*|FIRM\w*)\s*:", re.I)


class AnnexParseError(ValueError):
    """An annex is missing or its structural boundaries need manual review."""


@dataclass(frozen=True)
class AnnexSectionRecord:
    """One annex section or table-page fragment with exact source provenance."""

    section_id: str
    heading: str
    text: str = field(repr=False)
    page_start: int
    page_end: int
    resolution: str
    source_url: str
    source_title: str
    publication_date: date
    version: str
    sha256: str
    review_required: bool
    row_count: int | None = None

    @property
    def citation(self) -> str:
        """Cite the annex section and its one-based source pages."""
        pages = (
            f"p. {self.page_start}"
            if self.page_start == self.page_end
            else f"pp. {self.page_start}-{self.page_end}"
        )
        if self.section_id == "Anexo técnico":
            return f"{self.resolution}, anexo técnico, {pages}"
        return f"{self.resolution}, anexo técnico, sección {self.section_id}, {pages}"

    @property
    def section_path(self) -> tuple[str, ...]:
        """Return each numeric parent needed to place this section in the manual."""
        if not self.section_id[0].isdigit():
            return (self.section_id,)
        parts = self.section_id.split(".")
        return tuple(".".join(parts[:index]) for index in range(1, len(parts) + 1))


@dataclass(frozen=True)
class AnnexRecord:
    """An annex parse result with review flags for uncertain OCR/layout."""

    resolution: str
    source_url: str
    sha256: str
    sections: tuple[AnnexSectionRecord, ...]
    warnings: tuple[str, ...]


def _clean(value: str) -> str:
    return " ".join(value.split())


def _annex_start(pdf: pymupdf.Document, last_article_page: int) -> int:
    for index in range(last_article_page, len(pdf)):
        page = pdf[index]
        page_text = page.get_text("text", sort=True)  # type: ignore[no-untyped-call]
        lines = (_clean(line) for line in page_text.splitlines())
        if any(_ANNEX.fullmatch(line) for line in lines):
            return index + 1
    raise AnnexParseError("Annex heading was not found after the resolution")


def _table_rows(page: pymupdf.Page, *, first_page: bool) -> list[str]:
    """Group the four OCR columns by each CIE-code cell on a reviewed table page."""
    words = page.get_text("words")  # type: ignore[no-untyped-call]
    codes = sorted(
        (
            word
            for word in words
            if 305 <= word[0] <= 365
            and word[1] > (190 if first_page else 105)
            and _CODE.fullmatch(word[4])
        ),
        key=lambda word: word[1],
    )
    if not codes:
        raise AnnexParseError("No CIE column anchors found in annex table")

    centers = [(word[1] + word[3]) / 2 for word in codes]
    boundaries = [max(105, centers[0] - (centers[1] - centers[0]) / 2)] if len(codes) > 1 else [105]
    boundaries.extend((left + right) / 2 for left, right in pairwise(centers))
    boundaries.append(page.rect.height - 70)

    rows: list[str] = []
    for index, code in enumerate(codes):
        cells: list[list[tuple[float, float, str]]] = [[], [], [], []]
        for word in words:
            midpoint = (word[1] + word[3]) / 2
            if not boundaries[index] <= midpoint < boundaries[index + 1]:
                continue
            x = word[0]
            if not 85 <= x < 550:
                continue
            column = 0 if x < 175 else 1 if x < 300 else 2 if x < 370 else 3
            cells[column].append((word[1], x, word[4]))
        values = [" ".join(item[2] for item in sorted(cell)) for cell in cells]
        if code[4] not in values[2]:
            raise AnnexParseError("CIE row anchor could not be placed in its column")
        rows.append(
            f"Tecnología: {values[0]}; motivo: {values[1]}; "
            f"CIE-10: {values[2]}; diagnóstico: {values[3]}"
        )
    return rows


def _parse_table_annex(
    pdf: pymupdf.Document, start: int, record: SourceRecord, resolution: str
) -> AnnexRecord:
    sections: list[AnnexSectionRecord] = []
    uncertain_codes = 0
    for page_number in range(start, len(pdf) + 1):
        page = pdf[page_number - 1]
        page_text = page.get_text("text")  # type: ignore[no-untyped-call]
        if any(_SIGNING.match(_clean(line)) for line in page_text.splitlines()):
            raise AnnexParseError(f"Possible signing details on annex page {page_number}")
        rows = _table_rows(page, first_page=page_number == start)
        uncertain_codes += sum(
            not re.fullmatch(r"[A-Z][0-9]{2,3}", row.split("CIE-10: ", 1)[1].split(";", 1)[0])
            for row in rows
        )
        text = "\n".join(rows)
        sections.append(
            AnnexSectionRecord(
                section_id="Anexo técnico",
                heading="Tabla de medicamentos excluidos",
                text=text,
                page_start=page_number,
                page_end=page_number,
                resolution=resolution,
                source_url=str(record.source_url),
                source_title=record.title,
                publication_date=record.publication_date,
                version=record.version,
                sha256=record.sha256,
                review_required=True,
                row_count=len(rows),
            )
        )
    warnings = ["Table-row alignment and OCR codes require comparison with the official PDF"]
    if uncertain_codes:
        warnings.append(f"{uncertain_codes} CIE cells fail the expected code shape")
    return AnnexRecord(
        resolution,
        str(record.source_url),
        record.sha256,
        tuple(sections),
        tuple(warnings),
    )


@dataclass(frozen=True)
class _Line:
    text: str
    x: float
    y: float
    size: float


def _manual_lines(page: pymupdf.Page) -> list[_Line]:
    lines: list[_Line] = []
    for block in page.get_text("dict", sort=True)["blocks"]:  # type: ignore[no-untyped-call]
        for line in block.get("lines", []):
            y = line["bbox"][1]
            if not 145 <= y <= page.rect.height - 65:
                continue
            text = _clean("".join(span["text"] for span in line["spans"]))
            if text:
                lines.append(
                    _Line(text, line["bbox"][0], y, max(span["size"] for span in line["spans"]))
                )
    lines.sort(key=lambda line: (round(line.y / 3), line.x))
    merged: list[_Line] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if (
            _NUMBER_ONLY.fullmatch(line.text)
            and index + 1 < len(lines)
            and abs(lines[index + 1].y - line.y) <= 3
            and lines[index + 1].x > line.x
        ):
            following = lines[index + 1]
            merged.append(
                _Line(
                    f"{line.text} {following.text}", line.x, line.y, max(line.size, following.size)
                )
            )
            index += 2
        else:
            merged.append(line)
            index += 1
    return merged


def _heading(line: _Line) -> tuple[str, str] | None:
    match = _HEADING.fullmatch(line.text)
    if match is None or line.size < 9 or len(match.group(2)) > 140:
        return None
    identifier = match.group(1).replace(",", ".")
    if not 1 <= int(identifier.split(".")[0]) <= 11:
        return None
    title = match.group(2)
    letters = [character for character in title if character.isalpha()]
    if len(letters) < 4 or sum(character.isupper() for character in letters) / len(letters) < 0.75:
        return None
    return identifier, title


def _numbering_warnings(identifiers: set[str]) -> list[str]:
    warnings: list[str] = []
    for identifier in sorted(identifiers, key=lambda value: tuple(map(int, value.split(".")))):
        parts = identifier.split(".")
        if len(parts) > 1 and ".".join(parts[:-1]) not in identifiers:
            warnings.append(f"Parent heading missing for section {identifier}")
        if int(parts[-1]) > 1:
            predecessor = ".".join([*parts[:-1], str(int(parts[-1]) - 1)])
            if predecessor not in identifiers:
                warnings.append(f"Previous heading missing before section {identifier}")
    return warnings


def _parse_manual_annex(
    pdf: pymupdf.Document, start: int, record: SourceRecord, resolution: str
) -> AnnexRecord:
    introduction_page = next(
        (
            page_number
            for page_number in range(start, min(start + 7, len(pdf) + 1))
            if any(
                _INTRODUCTION.fullmatch(line.text) for line in _manual_lines(pdf[page_number - 1])
            )
        ),
        None,
    )
    if introduction_page is None:
        raise AnnexParseError("Manual body boundary was not found after the annex contents")

    sections: list[AnnexSectionRecord] = []
    current_id: str | None = None
    current_heading = ""
    current_lines: list[str] = []
    first_page = 0
    last_page = 0
    identifiers: set[str] = set()

    def finish() -> None:
        if current_id is None:
            return
        sections.append(
            AnnexSectionRecord(
                section_id=current_id,
                heading=current_heading,
                text="\n".join(current_lines),
                page_start=first_page,
                page_end=last_page,
                resolution=resolution,
                source_url=str(record.source_url),
                source_title=record.title,
                publication_date=record.publication_date,
                version=record.version,
                sha256=record.sha256,
                review_required=True,
            )
        )

    for page_number in range(introduction_page, len(pdf) + 1):
        for line in _manual_lines(pdf[page_number - 1]):
            if current_id is None and not _INTRODUCTION.fullmatch(line.text):
                continue
            if _SIGNING.match(line.text):
                raise AnnexParseError(f"Possible signing details on annex page {page_number}")
            heading = _heading(line)
            if heading is not None or (current_id is None and _INTRODUCTION.fullmatch(line.text)):
                finish()
                current_id, current_heading = heading or ("Introducción", "Introducción")
                if current_id in identifiers:
                    raise AnnexParseError(f"Duplicate annex section heading {current_id}")
                identifiers.add(current_id)
                current_lines = [line.text]
                first_page = page_number
                last_page = page_number
            elif current_id is not None:
                current_lines.append(line.text)
                last_page = page_number
    finish()
    if len(sections) < 2:
        raise AnnexParseError("No numbered manual sections were found")
    warnings = _numbering_warnings(identifiers - {"Introducción"})
    warnings.append("OCR text and heading boundaries require comparison with the official PDF")
    return AnnexRecord(
        resolution, str(record.source_url), record.sha256, tuple(sections), tuple(warnings)
    )


def parse_annex(record: SourceRecord, root: Path) -> AnnexRecord:
    """Parse the two reviewed annex layouts, retaining uncertainty for review."""
    try:
        main = parse_resolution(record, root)
    except ArticleParseError as error:
        raise AnnexParseError("Main resolution failed provenance or boundary checks") from error
    if main.resolution not in {"Resolución 740 de 2024", "Resolución 3100 de 2019"}:
        raise AnnexParseError("No reviewed annex layout is configured for this resolution")
    data = (root / record.raw_path).read_bytes()
    with pymupdf.open(stream=data, filetype="pdf") as pdf:  # type: ignore[no-untyped-call]
        start = _annex_start(pdf, main.articles[-1].page_end)
        if main.resolution == "Resolución 740 de 2024":
            return _parse_table_annex(pdf, start, record, main.resolution)
        return _parse_manual_annex(pdf, start, record, main.resolution)
