"""
Decision engine for Buy or Wait? financial decision agent.
Generates candidate payment plans, evaluates spending reductions,
applies the 6-rule tie-breaking ranking, and assigns affordability_status.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple


def parse_date(d_str: str) -> datetime.date:
    return datetime.strptime(d_str, "%Y-%m-%d").date()


def format_date(d: datetime.date) -> str:
    return d.strftime("%Y-%m-%d")


class DecisionEngine:
    def __init__(self, forecast_engine):
        self.fe = forecast_engine

    def evaluate(
        self,
        profile: Dict[str, Any],
        request: Dict[str, Any],
        forecast_result: Dict[str, Any],
        payment_options: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Evaluates all eligible plans and selects the best recommendation.
        Returns dictionary matching required output fields:
            - amount_safe_to_pay: float
            - affordability_status: str
            - recommended_payment_method: str
            - payment_plan: str
            - earliest_date_for_full_payment: str
            - spending_changes_needed: str
        """
        req_id = request["request_id"]
        req_date_str = request["request_date"]
        req_date = parse_date(req_date_str)
        deadline_str = request["desired_completion_date"]
        deadline = parse_date(deadline_str)
        req_amt = request["requested_amount"]
        allows_partial = request["allows_partial_payment"]

        considered = profile["payment_methods_user_will_consider"]
        max_months = profile["max_installment_months"]
        willing_stop = set(profile["expense_categories_user_is_willing_to_stop"])
        willing_reduce = set(profile["expense_categories_user_is_willing_to_reduce"])

        amount_safe = forecast_result["amount_safe_to_pay"]
        earliest_date_str = forecast_result["earliest_date_for_full_payment"]

        options_for_req = [o for o in payment_options if o["request_id"] == req_id]

        candidates = []

        # -------------------------------------------------------------
        # Plan Candidate 1: full_payment (on request_date)
        # -------------------------------------------------------------
        if "full_payment" in considered:
            # 1a. Safe today without spending changes
            if amount_safe == req_amt:
                candidates.append({
                    "method": "full_payment",
                    "status": "affordable_now",
                    "payments": [(req_date_str, req_amt)],
                    "spending_changes": [],
                    "total_paid": req_amt,
                    "first_payment_date": req_date_str,
                    "last_payment_date": req_date_str,
                    "num_payments": 1,
                    "payment_option_id": "full_payment",
                    "meets_deadline": req_date_str <= deadline_str,
                })
            else:
                # 1b. Test with spending changes
                best_changes = self._find_spending_changes(
                    forecast_result,
                    [(req_date, req_amt)],
                    willing_stop,
                    willing_reduce,
                )
                if best_changes is not None:
                    candidates.append({
                        "method": "full_payment",
                        "status": "affordable_with_plan",
                        "payments": [(req_date_str, req_amt)],
                        "spending_changes": best_changes,
                        "total_paid": req_amt,
                        "first_payment_date": req_date_str,
                        "last_payment_date": req_date_str,
                        "num_payments": 1,
                        "payment_option_id": "full_payment",
                        "meets_deadline": req_date_str <= deadline_str,
                    })

        # -------------------------------------------------------------
        # Plan Candidate 2: installments (from request_payment_options.csv)
        # -------------------------------------------------------------
        if "installments" in considered:
            for opt in options_for_req:
                if opt["payment_method"] != "installments":
                    continue
                if max_months is not None and opt["number_of_payments"] > max_months:
                    continue

                # Build installment dates
                first_d = parse_date(opt["first_payment_date"])
                freq = opt["payment_frequency_days"]
                n = opt["number_of_payments"]
                amt = opt["payment_amount"]
                dates = [first_d + timedelta(days=i * freq) for i in range(n)]
                sched = [(format_date(d), amt) for d in dates]
                last_d_str = format_date(dates[-1])
                meets_dead = last_d_str <= deadline_str

                # Check safety without spending changes
                is_safe = self.fe.simulate_plan(
                    forecast_result,
                    [(d, amt) for d in dates],
                    []
                )
                if is_safe:
                    candidates.append({
                        "method": "installments",
                        "status": "affordable_with_plan",
                        "payments": sched,
                        "spending_changes": [],
                        "total_paid": opt["total_payable_amount"],
                        "first_payment_date": opt["first_payment_date"],
                        "last_payment_date": last_d_str,
                        "num_payments": n,
                        "payment_option_id": opt["payment_option_id"],
                        "meets_deadline": meets_dead,
                    })
                else:
                    # Test with spending changes
                    best_changes = self._find_spending_changes(
                        forecast_result,
                        [(d, amt) for d in dates],
                        willing_stop,
                        willing_reduce,
                    )
                    if best_changes is not None:
                        candidates.append({
                            "method": "installments",
                            "status": "affordable_with_plan",
                            "payments": sched,
                            "spending_changes": best_changes,
                            "total_paid": opt["total_payable_amount"],
                            "first_payment_date": opt["first_payment_date"],
                            "last_payment_date": last_d_str,
                            "num_payments": n,
                            "payment_option_id": opt["payment_option_id"],
                            "meets_deadline": meets_dead,
                        })

        # -------------------------------------------------------------
        # Plan Candidate 3: partial_payment
        # -------------------------------------------------------------
        if "partial_payment" in considered and allows_partial:
            if 0 < amount_safe < req_amt and earliest_date_str and earliest_date_str <= deadline_str:
                p1 = (req_date_str, amount_safe)
                p2 = (earliest_date_str, round(req_amt - amount_safe, 2))
                candidates.append({
                    "method": "partial_payment",
                    "status": "affordable_with_plan",
                    "payments": [p1, p2],
                    "spending_changes": [],
                    "total_paid": req_amt,
                    "first_payment_date": req_date_str,
                    "last_payment_date": earliest_date_str,
                    "num_payments": 2,
                    "payment_option_id": "partial_payment",
                    "meets_deadline": True,
                })

        # -------------------------------------------------------------
        # Plan Candidate 4: wait
        # -------------------------------------------------------------
        if "full_payment" in considered and earliest_date_str:
            meets_dead = earliest_date_str <= deadline_str
            candidates.append({
                "method": "wait",
                "status": "affordable_later" if meets_dead else "not_affordable",
                "payments": [(earliest_date_str, req_amt)],
                "spending_changes": [],
                "total_paid": req_amt,
                "first_payment_date": earliest_date_str,
                "last_payment_date": earliest_date_str,
                "num_payments": 1,
                "payment_option_id": "wait",
                "meets_deadline": meets_dead,
            })

        # Filter and rank candidates
        selected_plan = self._rank_candidates(candidates)

        if selected_plan is None:
            # Fallback: not_affordable / not_recommended
            return {
                "amount_safe_to_pay": amount_safe,
                "affordability_status": "not_affordable",
                "recommended_payment_method": "not_recommended",
                "payment_plan": "none",
                "earliest_date_for_full_payment": "",
                "spending_changes_needed": "none",
            }

        # Format output
        def fmt_amt(amt):
            rounded = round(float(amt), 2)
            if rounded == int(rounded):
                return f"{int(rounded)}"
            else:
                return f"{rounded:.2f}"

        plan_str = "|".join(f"{d}:{fmt_amt(amt)}" for d, amt in selected_plan["payments"])
        changes_str = "|".join(selected_plan["spending_changes"]) if selected_plan["spending_changes"] else "none"

        # Final earliest_date rule:
        # For affordable_now, earliest_date_for_full_payment must equal request_date
        out_earliest = earliest_date_str
        if selected_plan["status"] == "affordable_now":
            out_earliest = req_date_str
        elif selected_plan["status"] == "not_affordable":
            out_earliest = ""

        return {
            "amount_safe_to_pay": amount_safe,
            "affordability_status": selected_plan["status"],
            "recommended_payment_method": selected_plan["method"],
            "payment_plan": plan_str,
            "earliest_date_for_full_payment": out_earliest,
            "spending_changes_needed": changes_str,
            "selected_plan": selected_plan,
        }

    def _rank_candidates(self, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Ranks candidate plans according to problem_statement.md:
        1. Complete by desired_completion_date
        2. Require no spending changes
        3. Minimize total amount paid
        4. Start earlier
        5. Use fewer payments
        6. Lowest payment_option_id
        """
        if not candidates:
            return None

        # Filter out plans that do not meet deadline unless all do not
        valid_plans = [c for c in candidates if c["meets_deadline"] and c["method"] != "wait"]
        if not valid_plans:
            # Check wait plan if it meets deadline
            wait_plans = [c for c in candidates if c["method"] == "wait" and c["meets_deadline"]]
            if wait_plans:
                return wait_plans[0]
            return None

        def sort_key(c):
            return (
                0 if c["meets_deadline"] else 1,
                len(c["spending_changes"]),
                round(c["total_paid"], 2),
                c["first_payment_date"],
                c["num_payments"],
                c["payment_option_id"],
            )

        valid_plans.sort(key=sort_key)
        return valid_plans[0]

    def _find_spending_changes(
        self,
        forecast_result: Dict[str, Any],
        payments: List[Tuple[datetime.date, float]],
        willing_stop: set,
        willing_reduce: set,
    ) -> Optional[List[str]]:
        """
        Searches for up to 3 permitted spending changes to make payments safe.
        Mutually exclusive: cannot stop and reduce the same event.
        """
        stoppable = [c for c in forecast_result["stoppable_candidates"] if c["category"] in willing_stop]
        reducible = [c for c in forecast_result["reducible_candidates"] if c["category"] in willing_reduce]

        # Try 1 change
        for s in stoppable:
            changes = [("stop", s["event_id"], s["current_amount"])]
            if self.fe.simulate_plan(forecast_result, payments, changes):
                return [f"stop:{s['event_id']}"]

        for r in reducible:
            changes = [("reduce_to", r["event_id"], r["savings"])]
            if self.fe.simulate_plan(forecast_result, payments, changes):
                amt_str = f"{r['minimum_allowed_amount']:g}" if r["minimum_allowed_amount"].is_integer() else f"{r['minimum_allowed_amount']:.2f}"
                return [f"reduce_to:{r['event_id']}:{amt_str}"]

        # Try 2 changes
        for s in stoppable:
            for r in reducible:
                if s["event_id"] == r["event_id"]:
                    continue
                changes = [("stop", s["event_id"], s["current_amount"]), ("reduce_to", r["event_id"], r["savings"])]
                if self.fe.simulate_plan(forecast_result, payments, changes):
                    amt_str = f"{r['minimum_allowed_amount']:g}" if r["minimum_allowed_amount"].is_integer() else f"{r['minimum_allowed_amount']:.2f}"
                    return [f"stop:{s['event_id']}", f"reduce_to:{r['event_id']}:{amt_str}"]

        return None
