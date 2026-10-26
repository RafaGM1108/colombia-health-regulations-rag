"""Read reviewed regulation annexes as provenance-aware sections."""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
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
_TABLE_HEADING = "Medicamentos excluidos explícitamente que excepcionalmente podrán ser prescritos"
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
    row_number: int | None = None
    excerpt_id: str | None = None

    @property
    def citation(self) -> str:
        """Cite the annex section and its one-based source pages."""
        pages = (
            f"p. {self.page_start}"
            if self.page_start == self.page_end
            else f"pp. {self.page_start}-{self.page_end}"
        )
        if self.section_id == "Anexo técnico":
            row = f", fila {self.row_number}" if self.row_number is not None else ""
            return f"{self.resolution}, anexo técnico{row}, {pages}"
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
                heading=_TABLE_HEADING,
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


def parse_reviewed_table_rows(
    record: SourceRecord, root: Path, review_path: Path | None = None
) -> AnnexRecord:
    """Return source-checked table rows only for the exact reviewed PDF checksum."""
    provisional = parse_annex(record, root)
    if provisional.resolution != "Resolución 740 de 2024":
        raise AnnexParseError("No reviewed table is configured for this resolution")
    path = review_path or root / "data/reviews/resolution-740-annex.json"
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
        if review["source_sha256"] != record.sha256:
            raise AnnexParseError("Table review does not match the source checksum")
        pages = review["source_pages"]
        counts = review["page_row_counts"]
        if pages != [section.page_start for section in provisional.sections] or counts != [
            section.row_count for section in provisional.sections
        ]:
            raise AnnexParseError("Table row layout differs from the reviewed source")
        common = review["common_rows"]
        reviewed_rows = [
            {
                "technology": technology,
                "reason": review["common_reason"],
                **entry,
            }
            for technology in review["common_technologies"]
            for entry in common
        ] + review["additional_rows"]
        if len(reviewed_rows) != sum(counts):
            raise AnnexParseError("Table review row count does not match the source")
    except AnnexParseError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise AnnexParseError("Table review file is unreadable or incomplete") from error

    output: list[AnnexSectionRecord] = []
    offset = 0
    for page, count, provisional_section in zip(pages, counts, provisional.sections, strict=True):
        raw_rows = provisional_section.text.splitlines()
        for row_number, (raw, reviewed) in enumerate(
            zip(raw_rows, reviewed_rows[offset : offset + count], strict=True), start=1
        ):
            try:
                raw_code = raw.split("CIE-10: ", 1)[1].split(";", 1)[0]
                code = reviewed["code"]
                technology = reviewed["technology"].strip()
                reason = reviewed["reason"].strip()
                diagnosis = reviewed["diagnosis"].strip()
                verified = reviewed["verified"]
            except (IndexError, KeyError, AttributeError) as error:
                raise AnnexParseError("Table review row is incomplete") from error
            raw_digits = "".join(character for character in raw_code if character.isdigit())
            code_digits = "".join(character for character in code if character.isdigit())
            if (
                re.fullmatch(r"[A-Z][0-9]{2,3}", code) is None
                or not raw_digits.endswith(code_digits)
                or not technology
                or not reason
                or not diagnosis
                or not isinstance(verified, bool)
            ):
                raise AnnexParseError(f"Table review row {page}:{row_number} failed validation")
            if not verified:
                continue
            output.append(
                AnnexSectionRecord(
                    section_id="Anexo técnico",
                    heading=_TABLE_HEADING,
                    text=(
                        f"Tecnología: {technology}; motivo: {reason}; "
                        f"CIE-10: {code}; diagnóstico: {diagnosis}"
                    ),
                    page_start=page,
                    page_end=page,
                    resolution=provisional.resolution,
                    source_url=provisional_section.source_url,
                    source_title=provisional_section.source_title,
                    publication_date=provisional_section.publication_date,
                    version=provisional_section.version,
                    sha256=provisional_section.sha256,
                    review_required=False,
                    row_count=1,
                    row_number=row_number,
                )
            )
        offset += count
    excluded = len(reviewed_rows) - len(output)
    warnings = (f"{excluded} unverified table rows excluded",) if excluded else ()
    return AnnexRecord(
        provisional.resolution, provisional.source_url, provisional.sha256, tuple(output), warnings
    )


def _review_text_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(
        "".join(character if character.isalnum() else " " for character in plain).split()
    ).lower()


def _anchor_on_page(path: Path, page_number: int, anchor: str) -> bool:
    with pymupdf.open(str(path)) as pdf:  # type: ignore[no-untyped-call]
        if not 1 <= page_number <= len(pdf):
            return False
        return anchor in pdf[page_number - 1].get_text("text")


def parse_reviewed_manual_sections(
    record: SourceRecord, root: Path, review_path: Path | None = None
) -> AnnexRecord:
    """Return only manually checked home-care excerpts from the exact manual PDF."""
    provisional = parse_annex(record, root)
    if provisional.resolution != "Resolución 3100 de 2019":
        raise AnnexParseError("No reviewed manual is configured for this resolution")
    path = review_path or root / "data/reviews/resolution-3100-home-care.json"
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
        if review["source_sha256"] != record.sha256:
            raise AnnexParseError("Manual review does not match the source checksum")
        entries = review["entries"]
        if not isinstance(entries, list) or not entries:
            raise AnnexParseError("Manual review has no entries")
    except AnnexParseError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise AnnexParseError("Manual review file is unreadable or incomplete") from error

    parents = {section.section_id: section for section in provisional.sections}
    output: list[AnnexSectionRecord] = []
    seen: set[str] = set()
    for entry in entries:
        try:
            identifier = entry["section_id"]
            excerpt_id = entry.get("excerpt_id", identifier)
            parent = parents[entry["parent_section"]]
            page_start = entry["page_start"]
            page_end = entry["page_end"]
            start_anchor = entry["start_anchor"]
            end_anchor = entry["end_anchor"]
            heading = entry["heading"].strip()
            reviewed_text = entry["text"].strip()
            verified = entry["verified"]
            start = parent.text.index(start_anchor)
            end = parent.text.index(end_anchor, start) if end_anchor else len(parent.text)
            source_fragment = parent.text[start:end].strip()
        except (KeyError, ValueError, AttributeError, TypeError) as error:
            raise AnnexParseError("Manual review entry does not match a source section") from error
        if (
            not isinstance(identifier, str)
            or not isinstance(excerpt_id, str)
            or not excerpt_id
            or not isinstance(page_start, int)
            or not isinstance(page_end, int)
            or not isinstance(start_anchor, str)
            or not isinstance(end_anchor, (str, type(None)))
            or excerpt_id in seen
            or not (
                identifier == parent.section_id or identifier.startswith(f"{parent.section_id}.")
            )
            or not parent.page_start <= page_start <= page_end <= parent.page_end
            or not _anchor_on_page(root / record.raw_path, page_start, start_anchor)
            or (
                end_anchor is not None
                and not _anchor_on_page(root / record.raw_path, page_end, end_anchor)
            )
            or not heading
            or not reviewed_text
            or not isinstance(verified, bool)
            or SequenceMatcher(
                None, _review_text_key(reviewed_text), _review_text_key(source_fragment)
            ).ratio()
            < 0.9
            or any(_SIGNING.match(_clean(line)) for line in reviewed_text.splitlines())
            or re.search(r"\S+@\S+|\b\d{6,}\b", reviewed_text)
        ):
            raise AnnexParseError("Manual review entry failed source or privacy validation")
        seen.add(excerpt_id)
        if not verified:
            continue
        output.append(
            AnnexSectionRecord(
                section_id=identifier,
                heading=heading,
                text=reviewed_text,
                page_start=page_start,
                page_end=page_end,
                resolution=provisional.resolution,
                source_url=parent.source_url,
                source_title=parent.source_title,
                publication_date=parent.publication_date,
                version=parent.version,
                sha256=parent.sha256,
                review_required=False,
                excerpt_id=excerpt_id,
            )
        )
    warnings = ("All other manual text remains unreviewed and excluded",)
    return AnnexRecord(
        provisional.resolution, provisional.source_url, provisional.sha256, tuple(output), warnings
    )
