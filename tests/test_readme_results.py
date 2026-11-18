"""README result tables must be copied from the tracked reporting files."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
REPORTING = ROOT / "data/07_reporting"


def test_retrieval_table_matches_report() -> None:
    results = json.loads((REPORTING / "retrieval-v1.json").read_bytes())["results"]
    for name, label in (("article_aware", "Article-aware"), ("fixed_window", "Fixed-window")):
        result = results[name]
        hits = result["hit_rate_at_k"]
        row = f"| {label} | {hits['1']:.6f} | {hits['5']:.6f} | {result['mrr']:.6f} |"
        assert row in README


def test_answer_table_matches_graded_metrics() -> None:
    runs = json.loads((REPORTING / "answer-quality-v1.json").read_bytes())["runs"]
    labels = {
        "claude-sonnet-4-6": "Claude Sonnet 4.6 (baseline)",
        "claude-haiku-5-5": "Claude Haiku 5.5 (current)",
    }
    assert {run["generation_model"] for run in runs} == set(labels)
    for run in runs:
        answered = run["correct_of_answered"]
        claims = run["claims_supported"]
        absent = run["abstained_when_evidence_absent"]
        row = (
            f"| {labels[run['generation_model']]} | {run['correct_of_answerable']['count']} "
            f"| {answered['count']}/{answered['of']} | {claims['count']}/{claims['of']} "
            f"| {absent['count']}/{absent['of']} |"
        )
        assert row in README


def test_current_model_in_readme_is_the_configured_one() -> None:
    from colombia_health_rag.serving.generation import GENERATION_MODEL

    assert GENERATION_MODEL == "claude-haiku-5-5"
    assert "Claude Haiku 5.5 (current)" in README
