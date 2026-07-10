from pathlib import Path


def test_research_docs_use_christoffersen_independence_terminology() -> None:
    text = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("docs/paper_plan.md", "docs/manuscript_audit_prompt.md")
    )

    assert "Christoffersen conditional coverage" not in text
    assert "Christoffersen independence or conditional coverage" not in text
    assert "Christoffersen independence" in text


def test_paper_plan_marks_secondary_targets_as_deferred() -> None:
    text = Path("docs/paper_plan.md").read_text(encoding="utf-8")

    assert "current locked run evaluates only `full_gap_settle_to_open`" in text
    assert "close-to-open and night-close-to-open target variants remain deferred" in text


def test_active_docs_use_coverage_admissibility_not_retired_promotion_routes() -> None:
    text = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/paper_plan.md",
            "docs/manuscript_audit_prompt.md",
            "docs/results_snapshot.md",
            "docs/faq.md",
        )
    )

    retired = (
        "Side-specific ML-tail promotion gate",
        "promoted ML-tail",
        "selected-model figures",
        "tailrisk_selected_model_performance_table",
        "ml_tail_promoted_tail_models_table",
        "tailrisk_dm_summary_table",
    )
    assert all(term not in text for term in retired)
    assert "coverage-admissible" in text.lower()
