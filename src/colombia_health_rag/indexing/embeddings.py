"""Build reproducible embeddings from citation-ready official passages."""

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from typing import Literal, Protocol, cast

from colombia_health_rag.ingestion.annexes import (
    AnnexSectionRecord,
    parse_reviewed_manual_sections,
    parse_reviewed_table_rows,
)
from colombia_health_rag.ingestion.articles import ArticleRecord, parse_resolution
from colombia_health_rag.ingestion.manifest import load_manifest

MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MODEL_DIMENSION = 384
_WORDS = re.compile(r"\S+")


class Tokenizer(Protocol):
    """The token-count operation needed to avoid model truncation."""

    def encode(
        self, text: str, *, add_special_tokens: bool = True, verbose: bool = False
    ) -> Sequence[int]:
        """Count tokens including model-specific special tokens."""
        ...


class Encoder(Protocol):
    """The batch encoding operation provided by SentenceTransformer."""

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Iterable[Iterable[float]]:
        """Return one normalized vector per prefixed passage."""
        ...


@dataclass(frozen=True)
class Passage:
    """A token-bounded passage with its exact citation and source version."""

    id: str
    text: str
    resolution: str
    citation: str
    source_url: str
    source_title: str
    publication_date: str
    version: str
    source_sha256: str
    kind: Literal["article", "annex"]
    article_number: int | None
    section_id: str | None
    row_number: int | None
    excerpt_id: str | None
    page_start: int
    page_end: int
    part_number: int
    part_count: int


def normalize_text(text: str) -> str:
    """Apply stable Unicode and whitespace normalization without rewriting words."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def format_query(text: str) -> str:
    """Use the retrieval prefix required by the pinned E5 model."""
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("Query is empty")
    return f"query: {normalized}"


def split_text(text: str, tokenizer: Tokenizer, max_tokens: int) -> tuple[str, ...]:
    """Split on word boundaries so every prefixed passage fits the model window."""
    normalized = normalize_text(text)
    words = list(_WORDS.finditer(normalized))
    if not words or max_tokens < 4:
        raise ValueError("Passage is empty or token limit is invalid")
    parts: list[str] = []
    start = 0
    while start < len(words):
        low = start + 1
        high = len(words)
        best = start
        while low <= high:
            middle = (low + high) // 2
            candidate = normalized[words[start].start() : words[middle - 1].end()]
            token_count = len(tokenizer.encode(f"passage: {candidate}", verbose=False))
            if token_count <= max_tokens:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        if best == start:
            raise ValueError("A source token exceeds the model context window")
        parts.append(normalized[words[start].start() : words[best - 1].end()])
        start = best
    return tuple(parts)


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def make_passages(
    records: Sequence[ArticleRecord | AnnexSectionRecord], tokenizer: Tokenizer, max_tokens: int
) -> tuple[Passage, ...]:
    """Keep article/section boundaries and reject provisional annex text."""
    passages: list[Passage] = []
    for record in records:
        if isinstance(record, AnnexSectionRecord) and record.review_required:
            raise ValueError("Unreviewed annex text cannot be embedded")
        parts = split_text(record.text, tokenizer, max_tokens)
        if isinstance(record, ArticleRecord):
            kind: Literal["article", "annex"] = "article"
            locator = f"article:{record.number}"
            article_number, section_id, row_number, excerpt_id = record.number, None, None, None
        else:
            kind = "annex"
            locator = (
                f"annex:{record.section_id}:{record.page_start}:"
                f"{record.row_number or record.excerpt_id}"
            )
            article_number = None
            section_id = record.section_id
            row_number = record.row_number
            excerpt_id = record.excerpt_id
        for part_number, part in enumerate(parts, start=1):
            identity = {
                "source_sha256": record.sha256,
                "locator": locator,
                "part_number": part_number,
                "text": part,
            }
            passages.append(
                Passage(
                    id=_sha256(identity),
                    text=part,
                    resolution=record.resolution,
                    citation=record.citation,
                    source_url=record.source_url,
                    source_title=record.source_title,
                    publication_date=record.publication_date.isoformat(),
                    version=record.version,
                    source_sha256=record.sha256,
                    kind=kind,
                    article_number=article_number,
                    section_id=section_id,
                    row_number=row_number,
                    excerpt_id=excerpt_id,
                    page_start=record.page_start,
                    page_end=record.page_end,
                    part_number=part_number,
                    part_count=len(parts),
                )
            )
    if len({passage.id for passage in passages}) != len(passages):
        raise ValueError("Duplicate passage identity in official corpus")
    return tuple(sorted(passages, key=lambda passage: passage.id))


def collect_official_records(root: Path) -> tuple[ArticleRecord | AnnexSectionRecord, ...]:
    """Read only checksum-matched manifest sources and reviewed annex records."""
    records: list[ArticleRecord | AnnexSectionRecord] = []
    sources = sorted(
        load_manifest(root / "data/manifest.json"),
        key=lambda item: (str(item.source_url), item.sha256),
    )
    for source in sources:
        resolution = parse_resolution(source, root)
        records.extend(resolution.articles)
        if resolution.resolution == "Resolución 740 de 2024":
            records.extend(parse_reviewed_table_rows(source, root).sections)
        elif resolution.resolution == "Resolución 3100 de 2019":
            records.extend(parse_reviewed_manual_sections(source, root).sections)
    return tuple(records)


def _write_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _valid_vectors(vectors: object, count: int, dimension: int) -> bool:
    return (
        isinstance(vectors, list)
        and len(vectors) == count
        and all(
            isinstance(vector, list)
            and len(vector) == dimension
            and all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector)
            and abs(math.sqrt(sum(float(value) ** 2 for value in vector)) - 1.0) < 1e-3
            for vector in vectors
        )
    )


def build_embeddings(
    passages: Sequence[Passage],
    encoder: Encoder,
    output_root: Path,
    *,
    model_id: str,
    model_revision: str,
    software_versions: Mapping[str, str],
    batch_size: int = 16,
    dimension: int = MODEL_DIMENSION,
) -> Path:
    """Write atomic batches and skip matching batches on a resumed build."""
    if not passages or batch_size < 1 or dimension < 1:
        raise ValueError("Embedding build needs passages and positive dimensions")
    ordered = tuple(sorted(passages, key=lambda passage: passage.id))
    if len({passage.id for passage in ordered}) != len(ordered):
        raise ValueError("Duplicate passage identity in embedding input")
    inputs = [asdict(passage) for passage in ordered]
    build_config = {
        "model_id": model_id,
        "model_revision": model_revision,
        "software_versions": dict(sorted(software_versions.items())),
        "batch_size": batch_size,
        "dimension": dimension,
        "input_sha256": _sha256(inputs),
    }
    build_id = _sha256(build_config)[:20]
    build_dir = output_root / build_id
    build_dir.mkdir(parents=True, exist_ok=True)
    batch_files: list[str] = []
    for offset in range(0, len(ordered), batch_size):
        batch = ordered[offset : offset + batch_size]
        batch_input = [asdict(passage) for passage in batch]
        input_sha256 = _sha256(batch_input)
        filename = f"batch-{offset // batch_size:05d}.json"
        batch_files.append(filename)
        path = build_dir / filename
        if path.exists():
            existing = json.loads(path.read_bytes())
            if (
                existing.get("input_sha256") != input_sha256
                or existing.get("passages") != batch_input
                or not _valid_vectors(existing.get("vectors"), len(batch), dimension)
            ):
                raise ValueError(f"Existing embedding batch failed validation: {filename}")
            continue
        encoded = encoder.encode(
            [f"passage: {passage.text}" for passage in batch],
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = [[float(value) for value in vector] for vector in encoded]
        if not _valid_vectors(vectors, len(batch), dimension):
            raise ValueError("Encoder returned invalid vectors")
        _write_atomic(
            path, {"input_sha256": input_sha256, "passages": batch_input, "vectors": vectors}
        )
    _write_atomic(
        build_dir / "build.json",
        {
            **build_config,
            "build_id": build_id,
            "passage_count": len(ordered),
            "source_sha256s": sorted({passage.source_sha256 for passage in ordered}),
            "batch_files": batch_files,
        },
    )
    return build_dir


def main() -> None:
    """Build a local, versioned embedding snapshot from the reviewed corpus."""
    parser = argparse.ArgumentParser(description="Embed reviewed official regulation passages")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    torch = import_module("torch")
    sentence_transformers = import_module("sentence_transformers")
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    model = sentence_transformers.SentenceTransformer(
        MODEL_ID, revision=MODEL_REVISION, device="cpu", trust_remote_code=False
    )
    tokenizer = cast(Tokenizer, model.tokenizer)
    records = collect_official_records(args.root)
    passages = make_passages(records, tokenizer, min(512, int(model.max_seq_length)))
    build_dir = build_embeddings(
        passages,
        cast(Encoder, model),
        args.root / "data/04_embeddings",
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
        software_versions={
            name: version(name) for name in ("sentence-transformers", "transformers", "torch")
        },
        batch_size=args.batch_size,
    )
    _write_atomic(
        args.root / "data/03_chunks" / f"{build_dir.name}.json", [asdict(item) for item in passages]
    )
    print(f"Embedded {len(passages)} passages in {build_dir}")


if __name__ == "__main__":
    main()
