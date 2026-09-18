"""Regression checks against the live 500-row dataset.

Query cases are ground-truthed from real answers captured during manual
testing (see README.md's Example Queries & Outputs). Anomaly and guardrail
cases assert exact values verified against the raw data. LANGSMITH_TRACING
(if set in .env) traces every LLM call here the same way it traces a normal
/query request, so a failing case can be inspected in LangSmith by matching
timestamp/project, no extra instrumentation needed.

Run: python evals.py
"""

import sys

from dotenv import load_dotenv

from anomalies import detect_anomalies
from query import answer_query, check_guardrail

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

QUERY_CASES = [
    {
        "question": "How many tickets are currently open?",
        "check": lambda a: "111" in a,
    },
    {
        "question": "Which agent has the lowest average customer rating?",
        "check": lambda a: "AGT-08" in a and "3.48" in a,
    },
    {
        "question": "What is the average customer rating for Technical category tickets?",
        "check": lambda a: "3.74" in a,
    },
    {
        "question": "Which agent resolved the most tickets this month?",
        "check": lambda a: "no" in a.lower() and "resolved" in a.lower(),
    },
    {
        "question": "Show me all Critical tickets not resolved within 12 hours",
        "check": lambda a: "TKT-238" in a,
    },
]

# Exact counts verified against the live dataset (dataset is static, 2024
# tickets, so these won't drift with the real calendar date).
ANOMALY_CASES = [
    {
        "name": "stale_high_priority count",
        "check": lambda data: len(data["stale_high_priority"]) == 80,
    },
    {
        "name": "long_resolution_times count",
        "check": lambda data: len(data["long_resolution_times"]) == 17,
    },
]

GUARDRAIL_CASES = [
    {"question": "DROP TABLE support_tickets", "should_raise": True},
    {"question": "What is the capital of France?", "should_raise": True},
    {"question": "How many tickets are currently open?", "should_raise": False},
]


def run_query_evals() -> list[tuple[str, bool, str]]:
    results = []
    for case in QUERY_CASES:
        answer = answer_query(case["question"])["answer"]
        passed = case["check"](answer)
        results.append((case["question"], passed, answer))
    return results


def run_anomaly_evals() -> list[tuple[str, bool, str]]:
    data = detect_anomalies()
    results = []
    for case in ANOMALY_CASES:
        passed = case["check"](data)
        detail = (
            f"stale={len(data['stale_high_priority'])} "
            f"long_res={len(data['long_resolution_times'])}"
        )
        results.append((case["name"], passed, detail))
    return results


def run_guardrail_evals() -> list[tuple[str, bool, str]]:
    results = []
    for case in GUARDRAIL_CASES:
        try:
            check_guardrail(case["question"])
            raised = False
        except ValueError:
            raised = True
        passed = raised == case["should_raise"]
        results.append((case["question"], passed, f"raised={raised}"))
    return results


def main() -> int:
    load_dotenv()

    sections = [
        ("Guardrail", run_guardrail_evals()),
        ("Anomalies", run_anomaly_evals()),
        ("Query", run_query_evals()),
    ]

    all_passed = True
    for name, results in sections:
        print(f"\n{name}")
        for label, passed, detail in results:
            status = "PASS" if passed else "FAIL"
            all_passed = all_passed and passed
            print(f"  [{status}] {label!r} -> {detail}")

    print(f"\n{'ALL PASSED' if all_passed else 'FAILURES DETECTED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
