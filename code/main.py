"""
Main entry point for Buy or Wait? financial decision agent.
Evaluates purchase requests deterministically using daily cash flow forecasting,
conflict resolution, and decision optimization.
"""
import os
import sys
import argparse
import csv
from datetime import datetime

from data_loader import DataLoader
from conflict_resolver import ConflictResolver
from forecast_engine import ForecastEngine
from decision_engine import DecisionEngine
from explanation_generator import ExplanationGenerator


def run_pipeline(dataset_dir: str, output_path: str, use_samples: bool = False, verbose: bool = False):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Buy or Wait? agent...")
    print(f"Dataset directory: {dataset_dir}")
    print(f"Output path: {output_path}")
    print(f"Evaluation mode: {'sample_requests.csv' if use_samples else 'requests.csv'}")

    loader = DataLoader(dataset_dir)
    data = loader.load_all(use_samples=use_samples)

    profiles = data["profiles"]
    events = data["events"]
    messages = data["messages"]
    payment_options = data["payment_options"]
    requests = data["requests"]

    print(f"Loaded {len(profiles)} profiles, {len(events)} financial events, {len(messages)} messages, {len(payment_options)} payment options, {len(requests)} requests.")

    resolver = ConflictResolver()
    forecast_engine = ForecastEngine()
    decision_engine = DecisionEngine(forecast_engine)
    explanation_gen = ExplanationGenerator()

    output_rows = []
    fieldnames = [
        "request_id",
        "amount_safe_to_pay",
        "affordability_status",
        "recommended_payment_method",
        "payment_plan",
        "earliest_date_for_full_payment",
        "spending_changes_needed",
        "decision_explanation",
    ]

    for idx, req in enumerate(requests):
        uid = req["user_id"]
        req_id = req["request_id"]
        profile = profiles[uid]

        # 1. Reconcile events & messages
        recon = resolver.reconcile(
            user_id=uid,
            request_date=req["request_date"],
            events=events,
            messages=messages,
            home_currency=profile["home_currency"],
        )

        # 2. Build 90-day cash flow forecast
        forecast = forecast_engine.build_forecast(
            profile=profile,
            request=req,
            recon_data=recon,
        )

        # 3. Decision evaluation
        decision = decision_engine.evaluate(
            profile=profile,
            request=req,
            forecast_result=forecast,
            payment_options=payment_options,
        )

        # 4. Generate grounded explanation
        explanation = explanation_gen.generate_explanation(
            profile=profile,
            request=req,
            decision=decision,
            forecast_result=forecast,
        )

        row = {
            "request_id": req_id,
            "amount_safe_to_pay": decision["amount_safe_to_pay"],
            "affordability_status": decision["affordability_status"],
            "recommended_payment_method": decision["recommended_payment_method"],
            "payment_plan": decision["payment_plan"],
            "earliest_date_for_full_payment": decision["earliest_date_for_full_payment"],
            "spending_changes_needed": decision["spending_changes_needed"],
            "decision_explanation": explanation,
        }
        output_rows.append(row)

        if verbose and (idx + 1) % 25 == 0:
            print(f"Processed {idx + 1}/{len(requests)} requests...")

    # Ensure output directory exists
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Successfully generated {len(output_rows)} decisions in {output_path}")
    return output_rows


def main():
    parser = argparse.ArgumentParser(description="Buy or Wait? AI Financial Agent")
    parser.add_argument(
        "--dataset-dir",
        type=str,
        default=None,
        help="Path to dataset directory (defaults to 'dataset' or '../dataset')",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output.csv",
        help="Path to output CSV file (default: output.csv)",
    )
    parser.add_argument(
        "--sample-only",
        action="store_true",
        help="Run on sample_requests.csv instead of requests.csv",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose processing progress",
    )

    args = parser.parse_args()

    # Determine dataset dir
    dataset_dir = args.dataset_dir
    if not dataset_dir:
        if os.path.exists("dataset"):
            dataset_dir = "dataset"
        elif os.path.exists(os.path.join("..", "dataset")):
            dataset_dir = os.path.join("..", "dataset")
        else:
            dataset_dir = "dataset"

    # Determine output path default
    output_path = args.output
    if output_path == "output.csv" and not os.path.exists("dataset") and os.path.exists(os.path.join("..", "dataset")):
        output_path = os.path.join("..", "output.csv")

    run_pipeline(
        dataset_dir=dataset_dir,
        output_path=output_path,
        use_samples=args.sample_only,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
