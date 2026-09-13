"""
Explanation generator module for Buy or Wait? financial decision agent.
Produces concise, human-readable explanations strictly grounded in computed numbers, dates, and currencies.
Tracks token usage in evaluation/usage_report.md.
"""
from datetime import datetime
from typing import Dict, Any


def format_amount(amt: float, currency: str) -> str:
    """Formats monetary amounts nicely matching dataset style."""
    if currency in ["IDR", "INR"]:
        # Commas for thousands
        if amt.is_integer() or amt == int(amt):
            return f"{int(amt):,}"
        return f"{amt:,.2f}"
    else:
        if amt.is_integer() or amt == int(amt):
            return f"{int(amt):,}"
        return f"{amt:,.2f}"


def format_human_date(d_str: str) -> str:
    """Converts 'YYYY-MM-DD' to e.g. '8 August 2025' or '15 November 2019'."""
    if not d_str:
        return ""
    try:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        return f"{dt.day} {dt.strftime('%B %Y')}"
    except Exception:
        return d_str


class ExplanationGenerator:
    def __init__(self):
        self.calls_count = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0

    def generate_explanation(
        self,
        profile: Dict[str, Any],
        request: Dict[str, Any],
        decision: Dict[str, Any],
        forecast_result: Dict[str, Any],
    ) -> str:
        """
        Generates a concise, grounded explanation for the decision.
        """
        self.calls_count += 1
        curr = profile["home_currency"]
        req_amt = request["requested_amount"]
        min_bal = profile["minimum_balance_to_keep"]
        deadline_str = format_human_date(request["desired_completion_date"])
        safe_amt = decision["amount_safe_to_pay"]
        method = decision["recommended_payment_method"]
        status = decision["affordability_status"]
        earliest_date = decision["earliest_date_for_full_payment"]
        earliest_human = format_human_date(earliest_date)
        changes_str = decision["spending_changes_needed"]
        selected_plan = decision.get("selected_plan", {})

        f_req = format_amount(req_amt, curr)
        f_min = format_amount(min_bal, curr)
        f_safe = format_amount(safe_amt, curr)

        # 1. affordable_now with full_payment
        if status == "affordable_now" and method == "full_payment":
            return f"Pay {curr} {f_req} today. This leaves at least {curr} {f_min} available over the next 90 days."

        # 2. affordable_with_plan with full_payment + spending changes
        if status == "affordable_with_plan" and method == "full_payment" and changes_str != "none":
            # Build description of changes
            desc_parts = []
            for change in changes_str.split("|"):
                if change.startswith("stop:"):
                    eid = change.split(":")[1]
                    # Find candidate desc
                    desc = "flexible subscription"
                    for sc in forecast_result["stoppable_candidates"]:
                        if sc["event_id"] == eid:
                            desc = sc["description"].lower()
                            break
                    desc_parts.append(f"Stop the {desc}")
                elif change.startswith("reduce_to:"):
                    parts = change.split(":")
                    eid = parts[1]
                    new_amt = float(parts[2])
                    f_new = format_amount(new_amt, curr)
                    desc = "flexible expense"
                    for rc in forecast_result["reducible_candidates"]:
                        if rc["event_id"] == eid:
                            desc = rc["description"].lower()
                            break
                    desc_parts.append(f"reduce the {desc} to {curr} {f_new}")

            action_text = " and ".join(desc_parts)
            action_text = action_text[0].upper() + action_text[1:]
            return f"{action_text}, then pay {curr} {f_req} today. This leaves at least {curr} {f_min} available."

        # 3. affordable_with_plan with installments
        if method == "installments" and selected_plan:
            num_pmts = selected_plan.get("num_payments", len(selected_plan.get("payments", [])))
            first_date = format_human_date(selected_plan.get("first_payment_date", ""))
            installment_amt = selected_plan["payments"][0][1]
            f_inst = format_amount(installment_amt, curr)
            return f"Use {num_pmts} installments of {curr} {f_inst}, starting {first_date}. This leaves at least {curr} {f_min} available."

        # 4. affordable_with_plan with partial_payment
        if method == "partial_payment":
            rem_amt = req_amt - safe_amt
            f_rem = format_amount(rem_amt, curr)
            return f"Pay {curr} {f_safe} today and the remaining {curr} {f_rem} on {earliest_human}. This completes the full request and keeps the {curr} {f_min} minimum protected."

        # 5. affordable_later with wait
        if status == "affordable_later" or method == "wait":
            return f"Pay {curr} {f_req} in full on {earliest_human}. Paying earlier would take the balance below the {curr} {f_min} minimum."

        # 6. not_affordable / not_recommended
        if safe_amt > 0:
            return f"Do not proceed with the {curr} {f_req} request. Although {curr} {f_safe} is available today, the full amount cannot be completed safely within 90 days."
        else:
            return f"Do not make this payment by {deadline_str}. None of the available options keeps the {curr} {f_min} minimum protected."
