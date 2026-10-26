"""Extract citation-ready articles from reviewed resolution PDFs."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pymupdf

from colombia_health_rag.ingestion.manifest import SourceRecord

_RESOLUTION = re.compile(r"^Resolución\s+(\d+)\s+de\s+(\d{4})\b", re.IGNORECASE)
_RESOLVE = re.compile(r"^R\s*E\s*S\s*U\s*E\s*L\s*V\s*E\s*:?$", re.IGNORECASE)
_CLOSE = re.compile(r"\bC[ÚU]MPLASE\b", re.IGNORECASE)
_ARTICLE = re.compile(
    r"^ART[ÍI]CULO\s*['\u2019]?\s*(\d+)"
    r"(?:\s*[.°º:]|\s+(?=(?-i:[A-ZÁÉÍÓÚÜ])))",
    re.IGNORECASE,
)
_TITLE = re.compile(r"^T[ÍI]TULO\s+([IVXLCDM]+|\d+)$", re.IGNORECASE)
_CHAPTER = re.compile(r"^CAP[ÍI]TULO\s+([IVXLCDM]+|\d+)$", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


class ArticleParseError(ValueError):
    """A PDF cannot be safely split into numbered normative articles."""


@dataclass(frozen=True)
class ArticleRecord:
    """One normative article and the provenance needed for a citation."""

    number: int
    text: str
    page_start: int
    page_end: int
    section_path: tuple[str, ...]
    resolution: str
    source_url: str
    source_title: str
    publication_date: date
    version: str
    sha256: str

    @property
    def citation(self) -> str:
        """Name the resolution and article without relying on page numbers alone."""
        return f"{self.resolution}, artículo {self.number}"


@dataclass(frozen=True)
class ResolutionRecord:
    """A reviewed resolution with article-level parsed content."""

    resolution: str
    source_url: str
    sha256: str
    articles: tuple[ArticleRecord, ...]


def _clean(line: str) -> str:
    return _WHITESPACE.sub(" ", line).strip()


def _article_number(line: str) -> int | None:
    match = _ARTICLE.match(line)
    return int(match.group(1)) if match else None


def parse_resolution(record: SourceRecord, root: Path) -> ResolutionRecord:
    """Parse only the articles between RESUELVE and the closing formula.

    The checksum ties the parser to the reviewed local original. A missing
    boundary, nonconsecutive heading, or unreadable PDF requires manual review.
    """
    title_match = _RESOLUTION.match(record.title)
    if title_match is None:
        raise ArticleParseError("Manifest title does not identify a resolution")
    resolution = f"Resolución {title_match.group(1)} de {title_match.group(2)}"

    raw_root = (root / "data/01_raw").resolve()
    path = (root / record.raw_path).resolve()
    if not path.is_relative_to(raw_root):
        raise ArticleParseError("PDF path escapes data/01_raw")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record.sha256:
        raise ArticleParseError("PDF checksum differs from the reviewed manifest")

    source_url = str(record.source_url)
    articles: list[ArticleRecord] = []
    current_lines: list[str] = []
    current_number = 0
    start_page = 0
    end_page = 0
    title_section: str | None = None
    chapter_section: str | None = None
    current_section: tuple[str, ...] = ()
    inside = False
    closed = False

    def finish_article() -> None:
        if not current_number:
            return
        text = "\n".join(current_lines).strip()
        if not text:
            raise ArticleParseError(f"Article {current_number} has no extracted text")
        articles.append(
            ArticleRecord(
                number=current_number,
                text=text,
                page_start=start_page,
                page_end=end_page,
                section_path=current_section,
                resolution=resolution,
                source_url=source_url,
                source_title=record.title,
                publication_date=record.publication_date,
                version=record.version,
                sha256=record.sha256,
            )
        )

    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:  # type: ignore[no-untyped-call]
            for page_number, page in enumerate(pdf, start=1):
                # The reviewed layouts use this margin for running headers and page numbers.
                content = pymupdf.Rect(  # type: ignore[no-untyped-call]
                    0, 95, page.rect.width, page.rect.height - 75
                )
                for raw_line in page.get_text("text", sort=True, clip=content).splitlines():
                    line = _clean(raw_line)
                    if not line:
                        continue
                    if not inside:
                        if _RESOLVE.fullmatch(line):
                            inside = True
                        continue
                    if _CLOSE.search(line):
                        finish_article()
                        closed = True
                        break

                    title = _TITLE.fullmatch(line)
                    if title:
                        finish_article()
                        current_number = 0
                        current_lines = []
                        title_section = f"Título {title.group(1)}"
                        chapter_section = None
                        continue
                    chapter = _CHAPTER.fullmatch(line)
                    if chapter:
                        finish_article()
                        current_number = 0
                        current_lines = []
                        chapter_section = f"Capítulo {chapter.group(1)}"
                        continue

                    number = _article_number(line)
                    if number is not None:
                        if number != len(articles) + (1 if current_number else 0) + 1:
                            raise ArticleParseError(
                                f"Unexpected article number {number} on page {page_number}"
                            )
                        finish_article()
                        current_number = number
                        current_lines = [line]
                        start_page = page_number
                        end_page = page_number
                        current_section = tuple(
                            section
                            for section in (title_section, chapter_section)
                            if section is not None
                        )
                    elif current_number:
                        current_lines.append(line)
                        end_page = page_number
                if closed:
                    break
    except pymupdf.FileDataError as error:
        raise ArticleParseError("Reviewed source is not a readable PDF") from error

    if not inside or not closed or not articles:
        raise ArticleParseError("RESUELVE, closing formula, or articles could not be found")
    return ResolutionRecord(resolution, source_url, record.sha256, tuple(articles))
