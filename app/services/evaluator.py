"""
LLM Evaluation Suite for CollabMind AI Copilot.

Measures four things:
1. Classification accuracy (F1 score)
2. Latency per endpoint (p50, p95, p99)
3. Summary faithfulness (hallucination detection)
4. Regression tests against a golden dataset
"""
import time
import json
import statistics
from datetime import datetime
from pathlib import Path

from app.services.ai_copilot import classify, summarize, suggest_replies


# ── Golden dataset ────────────────────────────────────────────────────────────
# These are hand-labeled test cases. The LLM's output is compared against them.
# In production you'd have hundreds of these built up over time.

CLASSIFICATION_GOLDEN = [
    {
        "message": "URGENT: Production is down, customers can't login!",
        "expected": {"urgency": "high", "intent": "escalation", "sentiment": "negative"},
    },
    {
        "message": "Hey can someone review my PR when they get a chance?",
        "expected": {"urgency": "low", "intent": "question", "sentiment": "positive"},
    },
    {
        "message": "The new feature shipped successfully to all users.",
        "expected": {"urgency": "low", "intent": "information", "sentiment": "positive"},
    },
    {
        "message": "We need to fix the memory leak before Friday or we'll miss SLA.",
        "expected": {"urgency": "high", "intent": "action_item", "sentiment": "negative"},
    },
    {
        "message": "Weekly standup notes are in the shared doc.",
        "expected": {"urgency": "low", "intent": "information", "sentiment": "neutral"},
    },
    {
        "message": "Can anyone help me understand how the auth flow works?",
        "expected": {"urgency": "low", "intent": "question", "sentiment": "neutral"},
    },
    {
        "message": "Database CPU at 95%, queries timing out across all services!",
        "expected": {"urgency": "high", "intent": "escalation", "sentiment": "negative"},
    },
    {
        "message": "Please update the deployment docs by end of week.",
        "expected": {"urgency": "high", "intent": "action_item", "sentiment": "neutral"},
    },
]

SUMMARIZATION_GOLDEN = [
    {
        "messages": [
            {"author": {"username": "alice"}, "content": "The API is returning 500 errors on /checkout"},
            {"author": {"username": "bob"}, "content": "I see it too, started about 10 mins ago"},
            {"author": {"username": "alice"}, "content": "Found it — bad deploy of payment service, rolling back now"},
            {"author": {"username": "bob"}, "content": "Rollback complete, errors stopped"},
        ],
        "must_contain_concepts": ["500", "checkout", "payment", "rollback"],
        "must_not_contain": ["database", "frontend", "authentication"],
    },
    {
        "messages": [
            {"author": {"username": "carol"}, "content": "Sprint planning is moved to Thursday 2pm"},
            {"author": {"username": "dave"}, "content": "Works for me"},
            {"author": {"username": "carol"}, "content": "Great, I'll send the calendar invite"},
        ],
        "must_contain_concepts": ["sprint", "thursday"],
        "must_not_contain": ["cancelled", "friday", "monday"],
    },
]


# ── Metrics helpers ───────────────────────────────────────────────────────────

def compute_f1(predictions: list[str], labels: list[str]) -> float:
    """
    Compute F1 score for a single field (e.g. urgency).
    F1 = 2 * (precision * recall) / (precision + recall)
    """
    classes = list(set(labels))
    f1_scores = []

    for cls in classes:
        tp = sum(1 for p, l in zip(predictions, labels) if p == cls and l == cls)
        fp = sum(1 for p, l in zip(predictions, labels) if p == cls and l != cls)
        fn = sum(1 for p, l in zip(predictions, labels) if p != cls and l == cls)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0)
        f1_scores.append(f1)

    return round(sum(f1_scores) / len(f1_scores), 3) if f1_scores else 0.0


def percentile(data: list[float], p: int) -> float:
    """Compute the Pth percentile of a list of numbers."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = int(len(sorted_data) * p / 100)
    index = min(index, len(sorted_data) - 1)
    return round(sorted_data[index], 3)


def faithfulness_score(summary: str, source_messages: list[dict]) -> float:
    """
    Simple faithfulness check: what fraction of key words in the summary
    actually appear in the source messages?

    A score of 1.0 = fully grounded. 0.5 = half the words are hallucinated.
    This is a simplified version of the RAGAS faithfulness metric.
    """
    source_text = " ".join(
        m.get("content", "").lower() for m in source_messages
    )
    summary_words = [
        w.lower().strip(".,!?") for w in summary.split()
        if len(w) > 4  # skip short words like "the", "and"
    ]
    if not summary_words:
        return 0.0

    grounded = sum(1 for w in summary_words if w in source_text)
    return round(grounded / len(summary_words), 3)


# ── Eval runners ──────────────────────────────────────────────────────────────

async def run_classification_eval() -> dict:
    """
    Run all golden classification test cases.
    Returns accuracy and F1 score per field.
    """
    print("\n[eval] Running classification eval...")
    latencies = []
    urgency_preds, urgency_labels = [], []
    intent_preds, intent_labels = [], []
    sentiment_preds, sentiment_labels = [], []
    failures = []

    for i, case in enumerate(CLASSIFICATION_GOLDEN):
        start = time.perf_counter()
        try:
            result = await classify(case["message"])
            latency = time.perf_counter() - start
            latencies.append(latency)

            urgency_preds.append(result.get("urgency", "low"))
            urgency_labels.append(case["expected"]["urgency"])

            intent_preds.append(result.get("intent", "information"))
            intent_labels.append(case["expected"]["intent"])

            sentiment_preds.append(result.get("sentiment", "neutral"))
            sentiment_labels.append(case["expected"]["sentiment"])

            match = result.get("urgency") == case["expected"]["urgency"]
            status = "PASS" if match else "FAIL"
            print(f"  [{status}] case {i+1}: urgency={result.get('urgency')} "
                  f"(expected={case['expected']['urgency']}) {latency:.2f}s")

            if not match:
                failures.append({
                    "case": i + 1,
                    "message": case["message"][:60],
                    "expected": case["expected"]["urgency"],
                    "got": result.get("urgency"),
                })
        except Exception as e:
            print(f"  [ERROR] case {i+1}: {e}")
            latencies.append(999)

    return {
        "name": "classification",
        "total_cases": len(CLASSIFICATION_GOLDEN),
        "urgency_f1": compute_f1(urgency_preds, urgency_labels),
        "intent_f1": compute_f1(intent_preds, intent_labels),
        "sentiment_f1": compute_f1(sentiment_preds, sentiment_labels),
        "latency_p50": percentile(latencies, 50),
        "latency_p95": percentile(latencies, 95),
        "latency_p99": percentile(latencies, 99),
        "failures": failures,
        "passed": len(CLASSIFICATION_GOLDEN) - len(failures),
    }


async def run_summarization_eval() -> dict:
    """
    Run summarization golden cases.
    Checks faithfulness and that key concepts appear in summary.
    """
    print("\n[eval] Running summarization eval...")
    latencies = []
    faithfulness_scores = []
    concept_hits = []
    hallucination_flags = []

    for i, case in enumerate(SUMMARIZATION_GOLDEN):
        start = time.perf_counter()
        try:
            summary = await summarize(case["messages"])
            latency = time.perf_counter() - start
            latencies.append(latency)

            # Faithfulness: are summary words grounded in source?
            faith = faithfulness_score(summary, case["messages"])
            faithfulness_scores.append(faith)

            # Concept check: do required concepts appear?
            summary_lower = summary.lower()
            hits = sum(
                1 for c in case["must_contain_concepts"]
                if c.lower() in summary_lower
            )
            hit_rate = hits / len(case["must_contain_concepts"])
            concept_hits.append(hit_rate)

            # Hallucination check: do forbidden words appear?
            hallucinated = [
                w for w in case["must_not_contain"]
                if w.lower() in summary_lower
            ]
            hallucination_flags.extend(hallucinated)

            status = "PASS" if faith > 0.4 and hit_rate > 0.5 else "FAIL"
            print(f"  [{status}] case {i+1}: faithfulness={faith:.2f} "
                  f"concept_hit={hit_rate:.2f} {latency:.2f}s")
            print(f"    summary: {summary[:100]}...")

        except Exception as e:
            print(f"  [ERROR] case {i+1}: {e}")
            latencies.append(999)

    avg_faith = round(statistics.mean(faithfulness_scores), 3) if faithfulness_scores else 0
    avg_concepts = round(statistics.mean(concept_hits), 3) if concept_hits else 0

    return {
        "name": "summarization",
        "total_cases": len(SUMMARIZATION_GOLDEN),
        "avg_faithfulness": avg_faith,
        "avg_concept_hit_rate": avg_concepts,
        "hallucinated_words": hallucination_flags,
        "latency_p50": percentile(latencies, 50),
        "latency_p95": percentile(latencies, 95),
        "passed": sum(
            1 for f, c in zip(faithfulness_scores, concept_hits)
            if f > 0.4 and c > 0.5
        ),
    }


async def run_latency_benchmark() -> dict:
    """
    Run each AI endpoint 3 times and measure latency distribution.
    In production you'd run 100+ times for statistical significance.
    """
    print("\n[eval] Running latency benchmark...")
    results = {}

    test_message = "The server is down and users cannot access the application."
    test_thread = [
        {"author": {"username": "alice"}, "content": "Server is down"},
        {"author": {"username": "bob"}, "content": "Investigating now"},
        {"author": {"username": "alice"}, "content": "Fixed, was a memory issue"},
    ]

    for name, coro_fn, args in [
        ("classify", classify, (test_message,)),
        ("summarize", summarize, (test_thread,)),
        ("suggest_replies", suggest_replies, (test_message, [])),
    ]:
        latencies = []
        print(f"  Benchmarking {name}...")
        for run in range(3):
            start = time.perf_counter()
            try:
                await coro_fn(*args)
                latencies.append(time.perf_counter() - start)
                print(f"    run {run+1}: {latencies[-1]:.2f}s")
            except Exception as e:
                print(f"    run {run+1}: ERROR {e}")

        results[name] = {
            "runs": len(latencies),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "mean": round(statistics.mean(latencies), 3) if latencies else 0,
        }

    return {"name": "latency_benchmark", "endpoints": results}


async def run_all_evals() -> dict:
    """Master runner — runs all evals and saves results to disk."""
    print("\n" + "="*60)
    print("CollabMind LLM Evaluation Suite")
    print("="*60)

    start = time.perf_counter()

    classification = await run_classification_eval()
    summarization = await run_summarization_eval()
    latency = await run_latency_benchmark()

    total_time = round(time.perf_counter() - start, 2)

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_time_seconds": total_time,
        "classification": classification,
        "summarization": summarization,
        "latency": latency,
        "overall_pass": (
            classification["urgency_f1"] >= 0.5
            and summarization["avg_faithfulness"] >= 0.2
        ),
    }

    # Save to disk
    Path("eval_results").mkdir(exist_ok=True)
    output_path = f"eval_results/eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print("\n" + "="*60)
    print("EVAL RESULTS SUMMARY")
    print("="*60)
    print(f"Classification urgency F1:  {classification['urgency_f1']:.3f}")
    print(f"Classification intent F1:   {classification['intent_f1']:.3f}")
    print(f"Classification sentiment F1:{classification['sentiment_f1']:.3f}")
    print(f"Summarization faithfulness: {summarization['avg_faithfulness']:.3f}")
    print(f"Summarization concept hit:  {summarization['avg_concept_hit_rate']:.3f}")
    print(f"Classify latency p50/p99:   {latency['endpoints']['classify']['p50']}s / {latency['endpoints']['classify']['p95']}s")
    print(f"Summarize latency p50/p99:  {latency['endpoints']['summarize']['p50']}s / {latency['endpoints']['summarize']['p95']}s")
    print(f"Total eval time: {total_time}s")
    print(f"Overall: {'PASS ✓' if report['overall_pass'] else 'FAIL ✗'}")
    print(f"Results saved to: {output_path}")
    print("="*60)

    return report