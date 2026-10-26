"""Persist checksum-verified official passage vectors for cited retrieval."""

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api.types import Embeddings
from chromadb.config import Settings
from pydantic import TypeAdapter

from colombia_health_rag.indexing.embeddings import (
    MODEL_DIMENSION,
    MODEL_ID,
    MODEL_REVISION,
    Passage,
    _sha256,
    _valid_vectors,
    _write_atomic,
)
from colombia_health_rag.ingestion.manifest import load_manifest

COLLECTION = "official_regulations"
_PASSAGE_ADAPTER = TypeAdapter(Passage)


@dataclass(frozen=True)
class SearchHit:
    """A ranked passage and the provenance needed for a precise citation."""

    id: str
    text: str
    distance: float
    metadata: dict[str, str | int]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_batches(
    root: Path, build_dir: Path
) -> tuple[dict[str, Any], list[Passage], list[list[float]], dict[str, str]]:
    build = _read_json(build_dir / "build.json")
    config_keys = (
        "model_id",
        "model_revision",
        "software_versions",
        "batch_size",
        "dimension",
        "input_sha256",
    )
    config = {key: build[key] for key in config_keys}
    if (
        build.get("model_id") != MODEL_ID
        or build.get("model_revision") != MODEL_REVISION
        or build.get("dimension") != MODEL_DIMENSION
        or not isinstance(build.get("batch_size"), int)
        or build["batch_size"] < 1
        or build.get("build_id") != _sha256(config)[:20]
        or build_dir.name != build["build_id"]
    ):
        raise ValueError("Embedding build configuration does not match the pinned model")
    batch_size = build["batch_size"]
    expected_names = [
        f"batch-{number:05d}.json"
        for number in range((build["passage_count"] + batch_size - 1) // batch_size)
    ]
    if build.get("batch_files") != expected_names or not expected_names:
        raise ValueError("Embedding batch list is incomplete or out of order")

    sources = {source.sha256: source for source in load_manifest(root / "data/manifest.json")}
    for source in sources.values():
        if _file_sha256(root / source.raw_path) != source.sha256:
            raise ValueError(f"Official source checksum changed: {source.raw_path}")

    passages: list[Passage] = []
    vectors: list[list[float]] = []
    batch_hashes: dict[str, str] = {}
    for name in expected_names:
        path = build_dir / name
        batch_hashes[name] = _file_sha256(path)
        batch = _read_json(path)
        raw_passages = batch.get("passages")
        raw_vectors = batch.get("vectors")
        if (
            not isinstance(raw_passages, list)
            or batch.get("input_sha256") != _sha256(raw_passages)
            or not _valid_vectors(raw_vectors, len(raw_passages), MODEL_DIMENSION)
        ):
            raise ValueError(f"Embedding batch failed integrity checks: {name}")
        for item in raw_passages:
            passage = _PASSAGE_ADAPTER.validate_python(item)
            if asdict(passage) != item:
                raise ValueError(f"Passage fields changed in {name}")
            matched_source = sources.get(passage.source_sha256)
            if matched_source is None or (
                passage.source_url != str(matched_source.source_url)
                or passage.source_title != matched_source.title
                or passage.publication_date != matched_source.publication_date.isoformat()
                or passage.version != matched_source.version
                or not passage.citation
                or not passage.text
                or passage.kind not in ("article", "annex")
            ):
                raise ValueError(f"Passage has unverified official provenance: {passage.id}")
            passages.append(passage)
        vectors.extend(cast(list[list[float]], raw_vectors))
    ids = [passage.id for passage in passages]
    if (
        len(passages) != build["passage_count"]
        or len(set(ids)) != len(ids)
        or ids != sorted(ids)
        or _sha256([asdict(item) for item in passages]) != build["input_sha256"]
        or sorted({item.source_sha256 for item in passages}) != build["source_sha256s"]
    ):
        raise ValueError("Embedding build passage set does not match its manifest")
    return build, passages, vectors, batch_hashes


def _metadata(passage: Passage) -> dict[str, str | int]:
    return {
        key: value
        for key, value in asdict(passage).items()
        if key not in ("id", "text") and isinstance(value, (str, int))
    }


def _client(index_dir: Path) -> chromadb.api.ClientAPI:
    return chromadb.PersistentClient(
        path=str(index_dir), settings=Settings(anonymized_telemetry=False)
    )


def build_index(root: Path, build_dir: Path, *, rebuild: bool = False) -> Path:
    """Build or verify a versioned local index from an intact embedding snapshot."""
    build, passages, vectors, batch_hashes = _load_batches(root, build_dir)
    build_id = cast(str, build["build_id"])
    index_dir = root / "data/05_index" / build_id
    manifest = {
        "build_id": build_id,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "dimension": MODEL_DIMENSION,
        "distance": "cosine",
        "passage_count": len(passages),
        "passage_ids_sha256": _sha256([passage.id for passage in passages]),
        "embedding_build_sha256": _file_sha256(build_dir / "build.json"),
        "batch_sha256s": batch_hashes,
        "chroma_version": version("chromadb"),
    }
    if index_dir.exists():
        if rebuild:
            client = _client(index_dir)
            if COLLECTION in [item.name for item in client.list_collections()]:
                client.delete_collection(COLLECTION)
            (index_dir / "index.json").unlink(missing_ok=True)
        else:
            existing = _read_json(index_dir / "index.json")
            if existing != manifest:
                raise ValueError("Existing index differs from embedding inputs; use --rebuild")
            collection = _client(index_dir).get_collection(COLLECTION)
            if (
                collection.count() != len(passages)
                or _sha256(sorted(collection.get(include=[])["ids"]))
                != manifest["passage_ids_sha256"]
            ):
                raise ValueError("Existing index entries differ from the build; use --rebuild")
            return index_dir
    index_dir.mkdir(parents=True, exist_ok=True)
    collection = _client(index_dir).create_collection(
        COLLECTION,
        configuration={"hnsw": {"space": "cosine"}},
        metadata={"build_id": build_id, "model_revision": MODEL_REVISION},
    )
    for offset in range(0, len(passages), 100):
        group = passages[offset : offset + 100]
        collection.add(
            ids=[item.id for item in group],
            documents=[item.text for item in group],
            metadatas=[_metadata(item) for item in group],
            embeddings=cast(Embeddings, vectors[offset : offset + 100]),
        )
    if collection.count() != len(passages):
        raise ValueError("Vector index count differs from embedding build")
    _write_atomic(index_dir / "index.json", manifest)
    return index_dir


def search_index(
    index_dir: Path,
    vector: list[float],
    *,
    k: int = 5,
    resolution: str | None = None,
    article_number: int | None = None,
    section_id: str | None = None,
    kind: str | None = None,
) -> list[SearchHit]:
    """Search normalized vectors and retain citation and source metadata in every hit."""
    manifest = _read_json(index_dir / "index.json")
    if manifest.get("model_id") != MODEL_ID or manifest.get("model_revision") != MODEL_REVISION:
        raise ValueError("Index uses a different embedding model")
    if k < 1 or not _valid_vectors([vector], 1, manifest["dimension"]):
        raise ValueError("Search needs a positive k and a normalized model-sized vector")
    filters: dict[str, str | int] = {}
    for key, value in (
        ("resolution", resolution),
        ("article_number", article_number),
        ("section_id", section_id),
        ("kind", kind),
    ):
        if value is not None:
            filters[key] = value
    where: dict[str, Any] | None = None
    if len(filters) == 1:
        where = filters
    elif filters:
        where = {"$and": [{key: value} for key, value in filters.items()]}
    collection = _client(index_dir).get_collection(COLLECTION)
    if collection.count() != manifest["passage_count"]:
        raise ValueError("Index count differs from its build manifest")
    result = collection.query(
        query_embeddings=cast(Embeddings, [vector]),
        n_results=min(k, manifest["passage_count"]),
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    documents, metadatas, distances = result["documents"], result["metadatas"], result["distances"]
    if documents is None or metadatas is None or distances is None:
        raise ValueError("Index returned incomplete search results")
    hits: list[SearchHit] = []
    for identity, document, metadata, distance in zip(
        result["ids"][0], documents[0], metadatas[0], distances[0], strict=True
    ):
        if document is None or metadata is None or not math.isfinite(distance):
            raise ValueError("Index returned a result without citation data")
        hits.append(SearchHit(identity, document, distance, cast(dict[str, str | int], metadata)))
    return hits


def main() -> None:
    """Build a local index from a selected embedding snapshot."""
    parser = argparse.ArgumentParser(description="Index verified official regulation embeddings")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--build-id")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    builds = args.root / "data/04_embeddings"
    if args.build_id:
        build_dir = builds / args.build_id
    else:
        candidates = sorted(builds.glob("*/build.json"))
        if len(candidates) != 1:
            parser.error("Specify --build-id when zero or multiple embedding builds exist")
        build_dir = candidates[0].parent
    index_dir = build_index(args.root, build_dir, rebuild=args.rebuild)
    count = _read_json(index_dir / "index.json")["passage_count"]
    print(f"Indexed {count} passages in {index_dir}")


if __name__ == "__main__":
    main()
