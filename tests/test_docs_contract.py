from pathlib import Path


def test_research_docs_use_christoffersen_independence_terminology() -> None:
    text = Path("docs/paper_plan.md").read_text(encoding="utf-8")

    assert "Christoffersen conditional coverage" not in text
    assert "Christoffersen independence or conditional coverage" not in text
    assert "Christoffersen independence" in " ".join(text.split())


def test_paper_plan_marks_secondary_targets_as_deferred() -> None:
    text = Path("docs/paper_plan.md").read_text(encoding="utf-8")

    assert "current locked run evaluates only `full_gap_settle_to_open`" in text
    assert "close-to-open and night-close-to-open target variants remain deferred" in text


def test_active_docs_use_robust_satisficing_not_retired_promotion_routes() -> None:
    text = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/paper_plan.md",
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
    assert "robust-satisficing" in text.lower()


def test_site_navigation_uses_public_pages_and_excludes_local_evaluation_notes() -> None:
    from mkdocs.config import load_config

    nav = Path("mkdocs.yml").read_text(encoding="utf-8").split("\nnav:\n", 1)[1]
    assert nav.splitlines() == [
        "  - Home: index.md",
        "  - Paper Plan: paper_plan.md",
        "  - Data: data.md",
        "  - Results Snapshot: results_snapshot.md",
        "  - FAQ: faq.md",
        "  - Future Work: future_work.md",
    ]
    for name in ("paper_plan.md", "results_snapshot.md"):
        assert (Path("docs") / name).is_file()
        assert name in Path("docs/index.md").read_text(encoding="utf-8")
    config = load_config("mkdocs.yml")
    public = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/index.md", "docs/paper_plan.md", "docs/results_snapshot.md")
    )
    for name in ("evaluation_protocol.md", "evaluation_20260921.md"):
        assert f"/docs/{name}" in Path(".gitignore").read_text(encoding="utf-8").splitlines()
        assert config.exclude_docs is not None and config.exclude_docs.match_file(name)
        assert name not in nav and name not in public


def test_data_inventory_separates_current_populations_from_historical_outputs() -> None:
    text = Path("docs/data.md").read_text(encoding="utf-8")
    assert "body22_expanding_oof_cov97_full_20260913" in text
    assert "reevaluation_fzg_grem_20260921" in text
    for count in ("2,403 rows", "722 clean target dates", "466 common dates", "628 common dates"):
        assert count in text
    assert "not the current OOS sample" in text
    assert "Current Clean-Run Data Inventory" not in text
    assert "They do not shorten every model's history" not in text
    assert "97% finite" in text
    assert "source provenance has also been deleted" in text
    assert "historical identifier, not" in text
    assert "reduces historical traceability" in text
    assert "remains under `artifacts/`" not in text


def test_paper_bundle_is_the_manuscript_figure_table_entrypoint() -> None:
    text = Path("docs/paper_plan.md").read_text(encoding="utf-8")
    assert "paper bundle is the manuscript figure/table entrypoint" in text
    assert "n225-open-gap-tail-manuscript" in text
    assert "information-contrast and paper-bundle directories separate" in text


def test_snapshot_displays_the_current_bundle_and_declares_plot_populations() -> None:
    text = Path("docs/results_snapshot.md").read_text(encoding="utf-8")
    for figure in (
        "sample",
        "timeline",
        "gates",
        "global_comparison",
        "information_scores",
        "grem",
        "var_paths_left_tail",
        "var_paths_right_tail",
        "target_tail_motivation",
    ):
        relative = f"figures/paper_bundle_20260921/{figure}.png"
        assert f"]({relative})" in text
        assert (Path("docs") / relative).is_file()
    assert "IQR-D, Gamma-D and GJR" in text
    assert "2,206 finite target-clean observations" in text
    assert "not D-only inference" in text
    assert "figures/information_contrasts_20260921/" not in text
