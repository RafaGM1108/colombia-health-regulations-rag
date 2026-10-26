"""Reproduce source-level retrieval metrics on reviewed official regulations."""

import argparse
import hashlib
from collections.abc import Sequence
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from typing import cast

from colombia_health_rag.evaluation.questions import (
    QuestionSet,
    load_questions,
    matches_evidence,
    validate_gold_locations,
)
from colombia_health_rag.indexing.embeddings import (
    MODEL_DIMENSION,
    MODEL_ID,
    MODEL_REVISION,
    Encoder,
    Passage,
    Tokenizer,
    _valid_vectors,
    _write_atomic,
    build_embeddings,
    collect_official_records,
    format_query,
    make_passages,
)
from colombia_health_rag.indexing.vector_index import _load_batches

TOP_K = (1, 3, 5, 10)
BASELINE_TOKENS = 192
BASELINE_OVERLAP_WORDS = 24


def rank_passages(
    passages: Sequence[Passage], vectors: Sequence[Sequence[float]], query: Sequence[float]
) -> list[Passage]:
    """Rank normalized vectors by exact cosine, breaking ties by passage ID."""
    if (
        len(passages) != len(vectors)
        or not passages
        or any(len(vector) != len(query) for vector in vectors)
    ):
        raise ValueError("Passages and vectors must have matching, nonempty dimensions")
    return [
        passages[index]
        for index in sorted(
            range(len(passages)),
            key=lambda index: (
                -sum(a * b for a, b in zip(vectors[index], query, strict=True)),
                passages[index].id,
            ),
        )
    ]


def evaluate_strategy(
    questions: QuestionSet,
    passages: Sequence[Passage],
    vectors: Sequence[Sequence[float]],
    query_vectors: Sequence[Sequence[float]],
) -> dict[str, object]:
    """Score exact source-and-locator hits for answerable questions only."""
    answerable = [item for item in questions.questions if item.evidence is not None]
    if not answerable or len(query_vectors) != len(answerable):
        raise ValueError("One query vector is required per answerable question")
    validate_gold_locations(questions, passages)
    ranks: dict[str, int] = {}
    examples: list[dict[str, object]] = []
    for item, query in zip(answerable, query_vectors, strict=True):
        if item.evidence is None:
            raise ValueError("Answerable question is missing evidence")
        ranked = rank_passages(passages, vectors, query)
        first_rank = next(
            rank
            for rank, passage in enumerate(ranked, start=1)
            if matches_evidence(passage, item.evidence, questions.sources)
        )
        ranks[item.id] = first_rank
        examples.append(
            {
                "question_id": item.id,
                "first_relevant_rank": first_rank,
                "top_5_citations": [passage.citation for passage in ranked[:5]],
            }
        )
    count = len(ranks)
    return {
        "passage_count": len(passages),
        "answerable_count": count,
        "unanswerable_count": len(questions.questions) - count,
        "hit_rate_at_k": {
            str(k): round(sum(rank <= k for rank in ranks.values()) / count, 6) for k in TOP_K
        },
        "mrr": round(sum(1 / rank for rank in ranks.values()) / count, 6),
        "per_question": examples,
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root: Path, report_path: Path) -> dict[str, object]:
    """Embed two splits of the same reviewed corpus and save measured results."""
    question_path = root / "data/06_evaluation/questions.json"
    manifest_path = root / "data/manifest.json"
    questions = load_questions(question_path, manifest_path)
    torch = import_module("torch")
    sentence_transformers = import_module("sentence_transformers")
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    model = sentence_transformers.SentenceTransformer(
        MODEL_ID, revision=MODEL_REVISION, device="cpu", trust_remote_code=False
    )
    tokenizer = cast(Tokenizer, model.tokenizer)
    encoder = cast(Encoder, model)
    records = collect_official_records(root)
    model_limit = min(512, int(model.max_seq_length))
    if model_limit < BASELINE_TOKENS:
        raise ValueError("Pinned model window is too short for the baseline")
    software_versions = {
        name: version(name) for name in ("sentence-transformers", "transformers", "torch")
    }
    splits = {
        "article_aware": make_passages(records, tokenizer, model_limit),
        "fixed_window": make_passages(
            records, tokenizer, BASELINE_TOKENS, overlap_words=BASELINE_OVERLAP_WORDS
        ),
    }
    answerable = [item for item in questions.questions if item.evidence is not None]
    encoded_queries = encoder.encode(
        [format_query(item.question) for item in answerable],
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    query_vectors = [[float(value) for value in vector] for vector in encoded_queries]
    if not _valid_vectors(query_vectors, len(answerable), MODEL_DIMENSION):
        raise ValueError("Query encoder returned invalid vectors")
    results: dict[str, object] = {}
    for name, split in splits.items():
        build_dir = build_embeddings(
            split,
            encoder,
            root / "data/04_embeddings",
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
            software_versions=software_versions,
        )
        build, passages, vectors, _ = _load_batches(root, build_dir)
        if {passage.id for passage in passages} != {passage.id for passage in split}:
            raise ValueError("Validated embedding snapshot differs from current corpus split")
        results[name] = {
            "build_id": build["build_id"],
            **evaluate_strategy(questions, passages, vectors, query_vectors),
        }
    report: dict[str, object] = {
        "schema_version": 1,
        "question_set_sha256": _sha256_file(question_path),
        "source_manifest_sha256": _sha256_file(manifest_path),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "software_versions": software_versions,
        "ranking": "exact cosine of normalized vectors; passage ID breaks ties",
        "relevance": "exact source SHA-256 and article or reviewed annex locator",
        "chunking": {
            "article_aware": {"max_tokens": model_limit, "overlap_words": 0},
            "fixed_window": {
                "max_tokens": BASELINE_TOKENS,
                "overlap_words": BASELINE_OVERLAP_WORDS,
            },
        },
        "unanswerable_question_ids": [
            item.id for item in questions.questions if item.evidence is None
        ],
        "results": results,
    }
    _write_atomic(report_path, report, indent=2)
    return report


def main() -> None:
    """Measure both chunking strategies on the frozen question set."""
    parser = argparse.ArgumentParser(description="Evaluate official-source retrieval")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report_path = args.report or args.root / "data/07_reporting/retrieval-v1.json"
    report = run(args.root, report_path)
    for name, result in cast(dict[str, dict[str, object]], report["results"]).items():
        print(f"{name}: {result['passage_count']} passages, MRR {result['mrr']}")
        print(f"  hit rate@k: {result['hit_rate_at_k']}")
    print(f"Saved {report_path}")


if __name__ == "__main__":
    main()
