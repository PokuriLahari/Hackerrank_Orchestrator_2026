"""
Benchmark agent predictions against dataset/sample_requests.csv.
Measures field-by-field accuracy on public sample cases.
"""
import os
import sys
import csv

# Add code dir to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import run_pipeline


def benchmark(dataset_dir: str = "dataset"):
    sample_path = os.path.join(dataset_dir, "sample_requests.csv")
    temp_output = os.path.join(os.path.dirname(__file__), "sample_predictions.csv")

    print("Running pipeline on sample_requests.csv...")
    predictions = run_pipeline(
        dataset_dir=dataset_dir,
        output_path=temp_output,
        use_samples=True,
        verbose=False,
    )

    expected = []
    with open(sample_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            expected.append(row)

    print(f"\nEvaluating {len(expected)} sample cases...")
    metrics = {
        "status": 0,
        "method": 0,
        "amount_safe": 0,
        "plan": 0,
        "earliest_date": 0,
        "spending_changes": 0,
    }

    diffs = []

    for pred, exp in zip(predictions, expected):
        rid = exp["request_id"]
        status_match = pred["affordability_status"] == exp["affordability_status"]
        method_match = pred["recommended_payment_method"] == exp["recommended_payment_method"]
        amount_match = abs(float(pred["amount_safe_to_pay"]) - float(exp["amount_safe_to_pay"])) < 0.01
        plan_match = pred["payment_plan"] == exp["payment_plan"]
        earliest_match = pred["earliest_date_for_full_payment"] == exp["earliest_date_for_full_payment"]
        changes_match = pred["spending_changes_needed"] == exp["spending_changes_needed"]

        if status_match: metrics["status"] += 1
        if method_match: metrics["method"] += 1
        if amount_match: metrics["amount_safe"] += 1
        if plan_match: metrics["plan"] += 1
        if earliest_match: metrics["earliest_date"] += 1
        if changes_match: metrics["spending_changes"] += 1

        if not (status_match and method_match and amount_match and plan_match and earliest_match and changes_match):
            diffs.append({
                "request_id": rid,
                "pred": pred,
                "exp": exp,
                "status_match": status_match,
                "method_match": method_match,
                "amount_match": amount_match,
                "plan_match": plan_match,
                "earliest_match": earliest_match,
                "changes_match": changes_match,
            })

    total = len(expected)
    print("\n--- Benchmark Results on sample_requests.csv ---")
    for k, v in metrics.items():
        print(f"  {k:20s}: {v}/{total} ({v/total*100:.1f}%)")

    if diffs:
        print(f"\nDifferences found in {len(diffs)} / {total} samples:")
        for d in diffs:
            print(f"\nRequest {d['request_id']}:")
            if not d["status_match"]:
                print(f"  status: pred='{d['pred']['affordability_status']}' vs exp='{d['exp']['affordability_status']}'")
            if not d["method_match"]:
                print(f"  method: pred='{d['pred']['recommended_payment_method']}' vs exp='{d['exp']['recommended_payment_method']}'")
            if not d["amount_match"]:
                print(f"  amount_safe: pred={d['pred']['amount_safe_to_pay']} vs exp={d['exp']['amount_safe_to_pay']}")
            if not d["plan_match"]:
                print(f"  plan: pred='{d['pred']['payment_plan']}' vs exp='{d['exp']['payment_plan']}'")
            if not d["earliest_match"]:
                print(f"  earliest_date: pred='{d['pred']['earliest_date_for_full_payment']}' vs exp='{d['exp']['earliest_date_for_full_payment']}'")
            if not d["changes_match"]:
                print(f"  spending_changes: pred='{d['pred']['spending_changes_needed']}' vs exp='{d['exp']['spending_changes_needed']}'")
    else:
        print("\nPERFECT MATCH: 100% agreement on all sample fields!")

    # Clean up temp output
    if os.path.exists(temp_output):
        os.remove(temp_output)


if __name__ == "__main__":
    benchmark()
