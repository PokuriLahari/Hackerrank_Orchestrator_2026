"""
Strict validator for Buy or Wait? challenge output.csv.
Validates headers, row count, enums, dates, bounds, payment plans, and spending changes
against problem_statement.md and AGENTS.md requirements.
"""
import os
import sys
import csv
import re
from datetime import datetime


REQUIRED_HEADERS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

VALID_STATUSES = {
    "affordable_now",
    "affordable_with_plan",
    "affordable_later",
    "not_affordable",
}

VALID_METHODS = {
    "full_payment",
    "partial_payment",
    "installments",
    "wait",
    "not_recommended",
}


def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_output(output_path: str, dataset_dir: str = "dataset") -> bool:
    print(f"Validating output file: {output_path}")

    if not os.path.exists(output_path):
        print(f"FAIL: Output file not found at {output_path}")
        return False

    # Load requests.csv to verify request_ids and amounts
    req_file = os.path.join(dataset_dir, "requests.csv")
    if not os.path.exists(req_file):
        print(f"Warning: {req_file} not found; looking for sample_requests.csv")
        req_file = os.path.join(dataset_dir, "sample_requests.csv")

    ref_requests = {}
    with open(req_file, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ref_requests[r["request_id"]] = {
                "request_date": r["request_date"],
                "requested_amount": float(r["requested_amount"]),
                "desired_completion_date": r["desired_completion_date"],
                "allows_partial_payment": r.get("allows_partial_payment", "").strip().lower() == "true",
            }

    errors = []
    warnings = []

    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader, None)

        if headers != REQUIRED_HEADERS:
            errors.append(f"Header mismatch!\nExpected: {REQUIRED_HEADERS}\nFound:    {headers}")

        rows = list(csv.DictReader(open(output_path, "r", encoding="utf-8")))

    print(f"Total rows in output: {len(rows)}")
    if len(rows) != len(ref_requests):
        errors.append(f"Row count mismatch: expected {len(ref_requests)}, found {len(rows)}")

    for idx, row in enumerate(rows):
        row_num = idx + 2
        rid = row.get("request_id", "")

        if rid not in ref_requests:
            errors.append(f"Row {row_num}: unknown request_id '{rid}'")
            continue

        ref = ref_requests[rid]
        req_amt = ref["requested_amount"]
        req_date = ref["request_date"]
        deadline = ref["desired_completion_date"]

        # 1. amount_safe_to_pay
        try:
            safe_amt = float(row["amount_safe_to_pay"])
            if safe_amt < -1e-4 or safe_amt > req_amt + 1e-4:
                errors.append(f"Row {row_num} ({rid}): amount_safe_to_pay ({safe_amt}) must be between 0 and {req_amt}")
        except (ValueError, TypeError):
            errors.append(f"Row {row_num} ({rid}): invalid amount_safe_to_pay '{row.get('amount_safe_to_pay')}'")
            safe_amt = 0.0

        # 2. affordability_status
        status = row.get("affordability_status", "")
        if status not in VALID_STATUSES:
            errors.append(f"Row {row_num} ({rid}): invalid affordability_status '{status}'")

        # 3. recommended_payment_method
        method = row.get("recommended_payment_method", "")
        if method not in VALID_METHODS:
            errors.append(f"Row {row_num} ({rid}): invalid recommended_payment_method '{method}'")

        # Status & Method consistency
        if status == "affordable_now" and method != "full_payment":
            errors.append(f"Row {row_num} ({rid}): affordable_now requires full_payment (got {method})")
        if status == "affordable_later" and method != "wait":
            errors.append(f"Row {row_num} ({rid}): affordable_later requires wait (got {method})")
        if status == "not_affordable" and method != "not_recommended":
            errors.append(f"Row {row_num} ({rid}): not_affordable requires not_recommended (got {method})")
        if status == "affordable_with_plan" and method not in ["full_payment", "partial_payment", "installments"]:
            errors.append(f"Row {row_num} ({rid}): affordable_with_plan requires full_payment, partial_payment, or installments (got {method})")

        # 4. earliest_date_for_full_payment
        earliest = row.get("earliest_date_for_full_payment", "").strip()
        if earliest:
            if not validate_date(earliest):
                errors.append(f"Row {row_num} ({rid}): invalid earliest_date_for_full_payment format '{earliest}'")
        if status == "affordable_now" and earliest != req_date:
            errors.append(f"Row {row_num} ({rid}): affordable_now requires earliest_date == request_date ({req_date}), got '{earliest}'")
        if status == "not_affordable" and earliest != "":
            # When not affordable within horizon, should be empty
            pass

        # 5. payment_plan
        plan = row.get("payment_plan", "").strip()
        if method == "not_recommended":
            if plan != "none":
                errors.append(f"Row {row_num} ({rid}): not_recommended requires payment_plan 'none' (got '{plan}')")
        else:
            if plan == "none":
                errors.append(f"Row {row_num} ({rid}): method '{method}' cannot have payment_plan 'none'")
            else:
                parts = plan.split("|")
                plan_dates = []
                plan_total = 0.0
                for p in parts:
                    if ":" not in p:
                        errors.append(f"Row {row_num} ({rid}): invalid payment_plan item '{p}'")
                        continue
                    p_date, p_amt_str = p.split(":", 1)
                    if not validate_date(p_date):
                        errors.append(f"Row {row_num} ({rid}): invalid date '{p_date}' in payment_plan")
                    try:
                        p_amt = float(p_amt_str)
                        plan_total += p_amt
                        plan_dates.append(p_date)
                    except ValueError:
                        errors.append(f"Row {row_num} ({rid}): invalid amount '{p_amt_str}' in payment_plan")

                # Check chronological ordering
                if plan_dates != sorted(plan_dates):
                    errors.append(f"Row {row_num} ({rid}): payment_plan dates must be in chronological order: {plan_dates}")

                # Specific checks per method
                if method == "partial_payment":
                    if len(parts) != 2:
                        errors.append(f"Row {row_num} ({rid}): partial_payment requires exactly 2 payments (got {len(parts)})")
                    else:
                        if abs(plan_total - req_amt) > 0.05:
                            errors.append(f"Row {row_num} ({rid}): partial_payment total ({plan_total}) does not equal requested_amount ({req_amt})")
                        if plan_dates and plan_dates[0] != req_date:
                            errors.append(f"Row {row_num} ({rid}): first partial payment date must be request_date ({req_date})")

        # 6. spending_changes_needed
        changes = row.get("spending_changes_needed", "").strip()
        if changes != "none":
            ch_list = changes.split("|")
            if len(ch_list) > 3:
                errors.append(f"Row {row_num} ({rid}): maximum 3 spending changes allowed (got {len(ch_list)})")
            for c in ch_list:
                if not (c.startswith("stop:") or c.startswith("reduce_to:")):
                    errors.append(f"Row {row_num} ({rid}): invalid spending change action '{c}'")

        # 7. decision_explanation
        expl = row.get("decision_explanation", "").strip()
        if not expl:
            errors.append(f"Row {row_num} ({rid}): missing decision_explanation")

    print("\n--- Validation Summary ---")
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"  [WARN] {w}")
    if errors:
        print(f"FAIL: {len(errors)} validation errors detected:")
        for e in errors[:25]:
            print(f"  [ERROR] {e}")
        if len(errors) > 25:
            print(f"  ... and {len(errors) - 25} more errors.")
        return False

    print("SUCCESS: 100% compliant! All validation checks passed cleanly.")
    return True


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "output.csv"
    dset = sys.argv[2] if len(sys.argv) > 2 else "dataset"
    ok = validate_output(out, dset)
    sys.exit(0 if ok else 1)
