# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from n225_open_gap_tail.config.runtime import (
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL,
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_UNIBM_MODEL,
    _optional_float,
)
from n225_open_gap_tail.config.model_labels import (
    display_information_set_label,
    display_model_label,
    display_source_block_label,
)
from n225_open_gap_tail.panel.information_sets import (
    ml_tail_feature_columns_for_information_set,
    registered_ml_tail_information_sets,
)
from n225_open_gap_tail.reporting.latex_utils import _latex_escape


def _predictor_block_coverage_to_latex(
    coverage: pl.DataFrame,
    *,
    manifest: Mapping[str, object] | None = None,
    retained_features: set[str] | None = None,
) -> str:
    manifest = manifest or {}
    headers = (
        "\\shortstack[l]{Information-set\\\\increment}",
        "Source/block",
        "Candidate features",
        "Representative predictors",
        "Mean missing (\\%)",
        "Maximum missing (\\%)",
    )
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: predictor_block_coverage_information_transparency",
        (
            "\\begin{tabularx}{\\linewidth}{@{}"
            ">{\\raggedright\\arraybackslash}p{0.15\\linewidth}"
            ">{\\raggedright\\arraybackslash}p{0.21\\linewidth}"
            "r>{\\raggedright\\arraybackslash}Xrr@{}}"
        ),
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _predictor_block_coverage_rows(
        coverage,
        retained_features=retained_features,
    ):
        lines.append(
            f"{_latex_escape(row.get('information_increment'))} & "
            f"{_latex_escape(row.get('source_block'))} & "
            f"{int(_optional_float(row.get('features')) or 0)} & "
            f"{_latex_escape(row.get('examples'))} & "
            f"{_missingness_percent(row.get('mean_missing'))} & "
            f"{_missingness_percent(row.get('max_missing'))} \\\\"
        )
    note = (
        "Notes: counts cover candidate predictors retained by at least one reported "
        "LightGBM refit. Missingness is calculated over the 1,722 modeling dates; "
        "mean and maximum missingness are computed across predictors within each row. "
        "Refit-specific timestamp, missingness, and variance screens still apply, so "
        "not every listed predictor enters every fitted forecast."
    )
    lines.extend(["\\bottomrule", "\\end{tabularx}"])
    lines.extend(
        [
            "\\par\\smallskip",
            (
                f"\\begin{{minipage}}{{\\linewidth}}\\footnotesize "
                f"{_latex_escape(note)}\\end{{minipage}}"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _predictor_block_coverage_rows(
    coverage: pl.DataFrame,
    *,
    retained_features: set[str] | None = None,
) -> list[dict[str, object]]:
    required = {"source_family", "source_block", "feature", "missingness_rate"}
    if coverage.is_empty() or not required.issubset(coverage.columns):
        return []
    if retained_features is not None:
        coverage = coverage.filter(pl.col("feature").is_in(sorted(retained_features)))
    if coverage.is_empty():
        return []

    coverage_records = coverage.to_dicts()
    information_sets = registered_ml_tail_information_sets()
    first_increment: dict[str, str] = {}
    for information_set in information_sets:
        for feature in ml_tail_feature_columns_for_information_set(
            coverage_records,
            information_set=information_set,
        ):
            first_increment.setdefault(feature, information_set)

    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in coverage_records:
        feature = str(row["feature"])
        increment = first_increment.get(feature)
        if increment is None:
            continue
        key = (
            increment,
            str(row["source_block"]),
        )
        grouped.setdefault(key, []).append(row)

    information_order = {name: index for index, name in enumerate(information_sets)}
    rows: list[dict[str, object]] = []
    for (information_set, source_block), group in grouped.items():
        missingness = [
            value
            for value in (_optional_float(row.get("missingness_rate")) for row in group)
            if value is not None
        ]
        source_families = {str(row["source_family"]) for row in group}
        rows.append(
            {
                "information_set": information_set,
                "information_increment": display_information_set_label(information_set),
                "source_block": _source_block_summary_label(source_block, source_families),
                "features": len(group),
                "examples": ", ".join(_representative_feature_examples(group)),
                "mean_missing": sum(missingness) / len(missingness) if missingness else None,
                "max_missing": max(missingness) if missingness else None,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            information_order.get(str(row["information_set"]), len(information_order)),
            str(row["source_block"]),
        ),
    )


def _missingness_percent(value: object) -> str:
    number = _optional_float(value)
    return "n/a" if number is None else f"{100.0 * number:.2f}"


def _source_block_summary_label(source_block: str, source_families: set[str]) -> str:
    labels = {
        "asia_proxy": "Massive and derived Asia proxies",
        "calendar_controls": "Official event calendars",
        "fred_core": "FRED, Cboe, and derived rates/volatility",
        "japan_only": "Japan history and J-Quants options",
        "japan_proxy": "Massive and derived Japan proxies",
        "us_core": "Massive and derived U.S. core",
    }
    if source_block in labels:
        return labels[source_block]
    sources = sorted(display_source_block_label(value) for value in source_families)
    block = display_source_block_label(source_block)
    return block if sources == [block] else f"{'; '.join(sources)} / {block}"


def _representative_feature_examples(
    rows: list[dict[str, object]],
    limit: int = 2,
) -> list[str]:
    selected: list[str] = []
    seen_families: set[str] = set()
    for row in rows:
        source_family = str(row["source_family"])
        if source_family in seen_families:
            continue
        selected.append(str(row["feature"]))
        seen_families.add(source_family)
        if len(selected) == limit:
            break
    for row in rows:
        feature = str(row["feature"])
        if len(selected) == limit:
            break
        if feature not in selected:
            selected.append(feature)
    return [_feature_example_label(feature) for feature in selected]


def _feature_example_label(feature: str) -> str:
    tokens = feature.split("_")
    replacements = {
        "n225": "Nikkei 225",
        "xmarket": "cross-market",
        "japan": "Japan",
        "asia": "Asia",
        "atm": "ATM",
        "iv": "implied volatility",
        "oi": "open interest",
        "boj": "BOJ",
        "cpi": "CPI",
        "ose": "OSE",
        "us": "U.S.",
        "vix": "VIX",
        "usdjpy": "USD/JPY",
        "dgs10": "10-year Treasury yield",
        "dgs2": "2-year Treasury yield",
        "t10y2y": "term spread",
        "var": "variance",
        "semivar": "semivariance",
        "cos": "cosine",
        "sin": "sine",
        "1d": "one-day",
        "20d": "20-day",
        "60d": "60-day",
        "30m": "30-minute",
        "60m": "60-minute",
        "diff": "change",
        "zscore": "z-score",
        "down": "downside",
        "up": "upside",
    }
    label_tokens = [replacements.get(token, token) for token in tokens if token != "event"]
    ticker_tokens = {"dia", "dxj", "eem", "ewh", "ewj", "gld", "spy", "uup"}
    label_tokens = [
        token.upper() if raw_token in ticker_tokens else token
        for raw_token, token in zip(
            (raw_token for raw_token in tokens if raw_token != "event"),
            label_tokens,
            strict=True,
        )
    ]
    if tokens and tokens[0].isalpha() and len(tokens[0]) <= 4:
        label_tokens[0] = tokens[0].upper()
    label = " ".join(label_tokens)
    return (
        label.replace("change 20 lag 1", "20-day change (one-day lag)")
        .replace("final window", "final-window")
        .replace("lag 1", "one-day lag")
    )


def _model_inventory_to_latex(*, manifest: Mapping[str, object] | None = None) -> str:
    manifest = manifest or {}
    headers = (
        "Model family",
        "Specifications",
        "Information basis",
        "VaR construction",
        "ES construction",
    )
    rows = [
        (
            "Empirical quantiles",
            "historical quantile; rolling quantile",
            "lagged opening-gap losses",
            "empirical quantile",
            "empirical tail mean",
        ),
        (
            "EWMA",
            "EWMA volatility scaling",
            "lagged opening-gap losses",
            "Gaussian conditional quantile",
            "Gaussian conditional tail mean",
        ),
        (
            "GARCH family",
            "GARCH-t; GJR-GARCH-t",
            "lagged opening-gap losses",
            "Student-t conditional quantile",
            "Student-t conditional tail mean",
        ),
        (
            "GARCH-EVT",
            "GJR-GARCH-EVT",
            "lagged opening-gap losses",
            "filtered POT-GPD",
            "GPD ES",
        ),
        (
            "CAViaR",
            "SAV; asymmetric slope",
            "lagged opening-gap losses",
            "recursive quantile",
            "empirical exceedance companion",
        ),
        (
            "CARE",
            "expectile SAV; expectile asymmetric slope",
            "lagged opening-gap losses",
            "training-selected expectile",
            "empirical exceedance companion",
        ),
        (
            "GAS-t",
            "location-scale; POT-GPD",
            "lagged opening-gap losses",
            "Student-t conditional or POT-GPD quantile",
            "Student-t conditional or POT-GPD tail mean",
        ),
        (
            "LightGBM direct quantile",
            display_model_label(ML_TAIL_DIRECT_QUANTILE_MODEL),
            "nested information sets",
            "quantile regression",
            "empirical exceedance companion",
        ),
        (
            "LightGBM empirical location-scale",
            display_model_label(ML_TAIL_LOCATION_SCALE_MODEL),
            "nested information sets",
            "empirical standardized-loss quantile",
            "empirical standardized-loss tail mean",
        ),
        (
            "LightGBM-EVT (mean/scale filter)",
            "; ".join(
                (
                    display_model_label(ML_TAIL_POT_GPD_PLAIN_MLE_MODEL),
                    display_model_label(ML_TAIL_POT_GPD_UNIBM_MODEL),
                )
            ),
            "nested information sets",
            "standardized POT-GPD",
            "GPD ES",
        ),
        (
            "LightGBM-EVT (robust filters)",
            "; ".join(
                display_model_label(model_name)
                for model_name in (
                    ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL,
                    ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL,
                    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
                    ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL,
                )
            ),
            "nested information sets",
            "POT-GPD on robust standardized losses",
            "GPD ES",
        ),
    ]
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: model_inventory_information_basis_forecast_construction",
        "\\begin{tabularx}{\\textwidth}{@{}"
        ">{\\raggedright\\arraybackslash}p{0.15\\textwidth}"
        ">{\\raggedright\\arraybackslash}X"
        ">{\\raggedright\\arraybackslash}p{0.14\\textwidth}"
        ">{\\raggedright\\arraybackslash}p{0.17\\textwidth}"
        ">{\\raggedright\\arraybackslash}p{0.17\\textwidth}@{}}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(_latex_escape(value) for value in row) + r" \\")
    note = (
        "Notes: the first four rows form the baseline benchmark set; CAViaR, CARE, and GAS-t "
        "are the advanced econometric benchmarks. Together they form the benchmark suite."
    )
    note_line = (
        f"\\multicolumn{{5}}{{p{{0.96\\textwidth}}}}{{\\footnotesize {_latex_escape(note)}}} \\\\"
    )
    lines.extend(["\\midrule", note_line])
    lines.extend(["\\bottomrule", "\\end{tabularx}", ""])
    return "\n".join(lines)
