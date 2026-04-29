import json
import urllib.request
from pathlib import Path

IMPLEMENTATION_ROOTS = (
    Path("src/n225_open_gap_tail/data_lake"),
    Path("src/n225_open_gap_tail/sources"),
    Path("src/n225_open_gap_tail/market"),
    Path("src/n225_open_gap_tail/features"),
    Path("src/n225_open_gap_tail/panel"),
    Path("src/n225_open_gap_tail/forecasting"),
    Path("src/n225_open_gap_tail/models"),
    Path("src/n225_open_gap_tail/metrics"),
    Path("src/n225_open_gap_tail/inference"),
    Path("src/n225_open_gap_tail/reporting"),
    Path("src/n225_open_gap_tail/diagnostics"),
)


def _read_functional_implementation() -> str:
    chunks: list[str] = []
    for root in IMPLEMENTATION_ROOTS:
        for path in sorted(root.glob("*.py")):
            if path.name == "__init__.py":
                continue
            chunks.append(f"\n\n=== {path.as_posix()} ===\n")
            chunks.append(path.read_text(encoding="utf-8"))
    return "".join(chunks)


def call_reviewer():
    url = "http://127.0.0.1:47631/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-n225-litellm-local-20260427",
    }

    pipeline_core = _read_functional_implementation()

    with open(
        "/Users/tycheng/.gemini/antigravity/brain/a2b09d94-df0d-4225-93fb-b2332e269d24/implementation_plan.md"
    ) as f:
        plan = f.read()

    prompt = f"""
    You are a Senior Quantitative Research Reviewer.
    Please review the current pipeline implementation against our Remediation Plan.
    Provide a harsh, extremely rigorous critique of any flaws in the code,
    potential look-ahead bias, statistics mistakes, or missing alignment with the plan.
    
    === REMEDIATION PLAN ===
    {plan}
    
    === CURRENT PIPELINE CORE ===
    {pipeline_core}
    """

    data = {
        "model": "reviewer_strong",
        "messages": [
            {
                "role": "system",
                "content": "You are a quantitative systems reviewer. Be extremely critical.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
    try:
        response = urllib.request.urlopen(req, timeout=300)
        result = json.loads(response.read().decode("utf-8"))
        print(result["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"Error calling LiteLLM: {e}")


if __name__ == "__main__":
    call_reviewer()
