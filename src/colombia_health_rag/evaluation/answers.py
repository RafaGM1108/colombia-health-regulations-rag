"""Run the fixed question set through cited generation and save raw outputs for grading."""

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from colombia_health_rag.evaluation.questions import QuestionSet, load_questions, matches_evidence
from colombia_health_rag.evaluation.retrieval import _sha256_file
from colombia_health_rag.indexing.embeddings import Passage, _write_atomic
from colombia_health_rag.indexing.vector_index import SearchHit
from colombia_health_rag.serving.generation import (
    GENERATION_EFFORT,
    GENERATION_MODEL,
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    AnthropicGenerator,
    TextGenerator,
    answer_from_hits,
    api_key_from_env,
    open_article_index,
    retrieve,
)

TOP_K = 5


class RecordingGenerator:
    """Keep each raw structured output so graders see what the model proposed."""

    def __init__(self, inner: TextGenerator) -> None:
        """Wrap a generator without changing its behavior."""
        self.inner = inner
        self.outputs: list[str] = []

    def generate(self, prompt: str) -> str:
        """Forward the prompt and record the returned JSON text."""
        output = self.inner.generate(prompt)
        self.outputs.append(output)
        return output


def _as_passage(hit: SearchHit) -> Passage:
    """Rebuild passage provenance from index metadata to reuse the gold matcher."""
    values: dict[str, Any] = {field.name: hit.metadata.get(field.name) for field in fields(Passage)}
    values.update(id=hit.id, text=hit.text)
    return Passage(**values)


def evaluate_answers(
    questions: QuestionSet,
    search: Callable[[str], list[SearchHit]],
    generator: TextGenerator,
) -> list[dict[str, object]]:
    """Answer every question once and record retrieval, raw output, and the verified answer."""
    recorder = RecordingGenerator(generator)
    records: list[dict[str, object]] = []
    for item in questions.questions:
        hits = search(item.question)[:TOP_K]
        recorder.outputs.clear()
        answer = answer_from_hits(item.question, hits, recorder)
        gold = item.evidence
        retrieved = [
            {
                "evidence_id": f"E{number}",
                "passage_id": hit.id,
                "citation": hit.metadata.get("citation"),
                "is_gold": None
                if gold is None
                else matches_evidence(_as_passage(hit), gold, questions.sources),
            }
            for number, hit in enumerate(hits, start=1)
        ]
        records.append(
            {
                "question_id": item.id,
                "answerable": gold is not None,
                "gold_retrieved": None
                if gold is None
                else any(entry["is_gold"] for entry in retrieved),
                "retrieved": retrieved,
                "raw_output": recorder.outputs[0] if recorder.outputs else None,
                "refused": answer.refused,
                "refusal_reason": answer.refusal_reason,
                "claims": [
                    {"text": claim.text, "quote": claim.quote, "citation": claim.citation.label}
                    for claim in answer.claims
                ],
            }
        )
    return records


def summarize(records: Sequence[dict[str, object]]) -> dict[str, object]:
    """Count mechanical outcomes only; correctness and support need separate grading."""

    def outcomes(rows: list[dict[str, object]]) -> dict[str, int]:
        counts = Counter(
            "answered" if not row["refused"] else str(row["refusal_reason"]) for row in rows
        )
        return dict(sorted(counts.items()))

    answerable = [row for row in records if row["answerable"]]
    unanswerable = [row for row in records if not row["answerable"]]
    return {
        "answerable": {
            "count": len(answerable),
            "gold_retrieved": sum(bool(row["gold_retrieved"]) for row in answerable),
            "outcomes": outcomes(answerable),
        },
        "unanswerable": {"count": len(unanswerable), "outcomes": outcomes(unanswerable)},
    }


def run(root: Path, report_path: Path, generator: TextGenerator) -> dict[str, object]:
    """Answer the frozen question set from the verified article-aware index and save it."""
    question_path = root / "data/06_evaluation/questions.json"
    manifest_path = root / "data/manifest.json"
    questions = load_questions(question_path, manifest_path)
    build_id, index_dir, encoder = open_article_index(root)
    records = evaluate_answers(
        questions, lambda question: retrieve(question, index_dir, encoder, k=TOP_K), generator
    )
    generator_config = json.dumps(
        {
            "model": GENERATION_MODEL,
            "effort": GENERATION_EFFORT,
            "system": SYSTEM_PROMPT,
            "schema": OUTPUT_SCHEMA,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "question_set_sha256": _sha256_file(question_path),
        "source_manifest_sha256": _sha256_file(manifest_path),
        "index_build_id": build_id,
        "generation_model": GENERATION_MODEL,
        "generation_effort": GENERATION_EFFORT,
        "generator_config_sha256": hashlib.sha256(generator_config.encode("utf-8")).hexdigest(),
        "top_k": TOP_K,
        "summary": summarize(records),
        "results": records,
    }
    _write_atomic(report_path, report, indent=2)
    return report


def main() -> None:
    """Generate answers for every public evaluation question with the pinned model."""
    parser = argparse.ArgumentParser(description="Generate cited answers for the frozen Q&A set")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    api_key = api_key_from_env(args.root)
    if not api_key:
        parser.error("Set ANTHROPIC_API_KEY in the local .env file or environment")
    report_path = args.report or args.root / f"data/07_reporting/answers-{GENERATION_MODEL}.json"
    report = run(args.root, report_path, AnthropicGenerator(api_key))
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved {report_path}")


if __name__ == "__main__":
    main()
