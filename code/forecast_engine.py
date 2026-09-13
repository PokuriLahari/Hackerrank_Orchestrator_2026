"""
Forecast engine for Buy or Wait? financial decision agent.
Builds day-by-day cash flow simulation over a 90-day horizon from request_date,
detects recurrence patterns, and computes amount_safe_to_pay and earliest_date_for_full_payment.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import numpy as np


def parse_date(d_str: str) -> datetime.date:
    return datetime.strptime(d_str, "%Y-%m-%d").date()


def format_date(d: datetime.date) -> str:
    return d.strftime("%Y-%m-%d")


class ForecastEngine:
    def __init__(self):
        pass

    def build_forecast(
        self,
        profile: Dict[str, Any],
        request: Dict[str, Any],
        recon_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Reconstructs the 90-day cash flow baseline for a user starting on request_date.
        Returns:
            - baseline_daily_balance: Dict[datetime.date, float]
            - amount_safe_to_pay: float
            - earliest_date_for_full_payment: str
            - stoppable_candidates: List[Dict]
            - reducible_candidates: List[Dict]
            - recurring_events: List of scheduled recurring events
        """
        user_id = profile["user_id"]
        home_curr = profile["home_currency"]
        req_date = parse_date(request["request_date"])
        end_date = req_date + timedelta(days=90)
        cur_bal = profile["current_available_balance"]
        min_bal = profile["minimum_balance_to_keep"]
        req_amt = request["requested_amount"]

        valid_events = recon_data["valid_events"]
        salary_info = recon_data["salary_info"]
        rent_multiplier = recon_data["rent_multiplier"]
        extra_incomes = recon_data["confirmed_extra_incomes"]

        # 1. Identify recurring streams from valid historical/scheduled events
        by_cat_dir = defaultdict(list)
        for e in valid_events:
            if e["status"] in ["settled", "scheduled"]:
                by_cat_dir[(e["category"], e["direction"])].append(e)

        # Check for unconfirmed gig earnings messages or final payroll
        has_final_payroll = any(
            e["category"] == "salary" and "final employer payroll" in e["description"].lower()
            for e in valid_events
        )

        projected_events = []

        # 2. Salary handling
        sal_events = by_cat_dir.get(("salary", "credit"), [])
        # Check if salary is regular confirmed employment vs variable platform gig
        is_gig = any(
            any(w in e["description"].lower() for w in ["delivery platform", "marketplace", "app earnings", "driver platform"])
            for e in sal_events
        )

        salary_eligible = (not salary_info["ended"]) and (not has_final_payroll) and (not is_gig)

        if salary_eligible and (sal_events or salary_info["amount"] is not None):
            if salary_info["amount"] is not None:
                sal_amt = salary_info["amount"]
            else:
                sal_amt = sal_events[-1]["amount"]

            # Salary day of month
            if salary_info["revised_date"]:
                rev_d = parse_date(salary_info["revised_date"])
                sal_day = rev_d.day
            elif sal_events:
                from collections import Counter
                day_counts = Counter(parse_date(e["event_date"]).day for e in sal_events)
                sal_day = day_counts.most_common(1)[0][0]
            else:
                sal_day = 15

            # Project salary monthly across the 90 days
            for m_offset in range(4):
                y = req_date.year
                m = req_date.month + m_offset
                while m > 12:
                    y += 1
                    m -= 12
                max_d = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
                s_date = datetime(y, m, min(sal_day, max_d)).date()
                if req_date <= s_date <= end_date:
                    amt_to_add = sal_amt
                    if m_offset == 0 and salary_info["one_off"]:
                        amt_to_add += sum(salary_info["one_off"])
                    projected_events.append({
                        "date": s_date,
                        "amount": amt_to_add,
                        "direction": "credit",
                        "category": "salary",
                        "flexibility": "fixed",
                        "event_id": "",
                        "minimum_allowed_amount": None,
                        "description": "Projected salary credit"
                    })

        # Extra confirmed incomes (approved invoices)
        for extra in extra_incomes:
            ed = parse_date(extra["date"])
            if req_date <= ed <= end_date:
                projected_events.append({
                    "date": ed,
                    "amount": extra["amount"],
                    "direction": "credit",
                    "category": "income",
                    "flexibility": "fixed",
                    "event_id": "",
                    "minimum_allowed_amount": None,
                    "description": extra["description"]
                })

        # 3. Recurring Debits
        stoppable_candidates = []
        reducible_candidates = []

        for (cat, direction), elist in by_cat_dir.items():
            if direction != "debit" or cat == "salary":
                continue
            if len(elist) < 2:
                continue

            dates = sorted([parse_date(e["event_date"]) for e in elist])
            intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            avg_int = sum(intervals) / len(intervals)

            amts = [e["amount"] for e in elist]
            last_e = elist[-1]
            flex = last_e["flexibility"]
            min_allowed = last_e["minimum_allowed_amount"]
            eid = last_e["event_id"]
            desc = last_e["description"]

            # Rent adjustment
            mult = rent_multiplier if cat == "rent" else 1.0

            if len(set(amts)) == 1:
                proj_amt = amts[-1] * mult
            else:
                mean_val = float(np.mean(amts)) * mult
                if home_curr in ["IDR", "INR"]:
                    proj_amt = round(mean_val)
                else:
                    proj_amt = round(mean_val, 2)

            # Record candidates for spending changes
            if flex in ["stoppable", "reducible_or_stoppable"]:
                stoppable_candidates.append({
                    "event_id": eid,
                    "category": cat,
                    "description": desc,
                    "current_amount": proj_amt,
                })
            if flex in ["reducible", "reducible_or_stoppable"] and min_allowed is not None:
                reducible_candidates.append({
                    "event_id": eid,
                    "category": cat,
                    "description": desc,
                    "current_amount": proj_amt,
                    "minimum_allowed_amount": min_allowed,
                    "savings": proj_amt - min_allowed,
                })

            # Project forward
            if 26 <= avg_int <= 33:  # Monthly
                day_of_month = dates[-1].day
                for m_offset in range(4):
                    y = req_date.year
                    m = req_date.month + m_offset
                    while m > 12:
                        y += 1
                        m -= 12
                    max_d = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
                    p_date = datetime(y, m, min(day_of_month, max_d)).date()
                    if req_date <= p_date <= end_date:
                        projected_events.append({
                            "date": p_date,
                            "amount": proj_amt,
                            "direction": "debit",
                            "category": cat,
                            "flexibility": flex,
                            "event_id": eid,
                            "minimum_allowed_amount": min_allowed,
                            "description": desc
                        })
            else:
                # Fixed cadence
                period = round(avg_int)
                cur_p = dates[-1] + timedelta(days=period)
                while cur_p <= end_date:
                    if cur_p >= req_date:
                        projected_events.append({
                            "date": cur_p,
                            "amount": proj_amt,
                            "direction": "debit",
                            "category": cat,
                            "flexibility": flex,
                            "event_id": eid,
                            "minimum_allowed_amount": min_allowed,
                            "description": desc
                        })
                    cur_p += timedelta(days=period)

        # 4. Pending debits (reserve immediately or on settlement date)
        for e in valid_events:
            if e["status"] == "pending" and e["direction"] == "debit":
                sd = parse_date(e["settlement_date"])
                p_date = max(req_date, sd)
                if p_date <= end_date:
                    projected_events.append({
                        "date": p_date,
                        "amount": e["amount"],
                        "direction": "debit",
                        "category": e["category"],
                        "flexibility": e["flexibility"],
                        "event_id": e["event_id"],
                        "minimum_allowed_amount": e["minimum_allowed_amount"],
                        "description": e["description"]
                    })

        # 5. Scheduled debits in future
        for e in valid_events:
            if e["status"] == "scheduled" and e["direction"] == "debit":
                sd = parse_date(e["settlement_date"])
                if req_date <= sd <= end_date:
                    projected_events.append({
                        "date": sd,
                        "amount": e["amount"],
                        "direction": "debit",
                        "category": e["category"],
                        "flexibility": e["flexibility"],
                        "event_id": e["event_id"],
                        "minimum_allowed_amount": e["minimum_allowed_amount"],
                        "description": e["description"]
                    })

        # Sort projected events by date
        projected_events.sort(key=lambda x: x["date"])

        # 6. Run Baseline Day-by-Day Simulation
        daily_flows = defaultdict(float)
        for pe in projected_events:
            if pe["direction"] == "credit":
                daily_flows[pe["date"]] += pe["amount"]
            else:
                daily_flows[pe["date"]] -= pe["amount"]

        baseline_daily_balance = {}
        bal = cur_bal
        min_balance_reached = bal

        for day_idx in range(91):
            d = req_date + timedelta(days=day_idx)
            bal += daily_flows[d]
            baseline_daily_balance[d] = bal
            if bal < min_balance_reached:
                min_balance_reached = bal

        # Compute amount_safe_to_pay
        raw_safe = max(0.0, min_balance_reached - min_bal)
        amount_safe_to_pay = min(req_amt, raw_safe)
        if home_curr in ["IDR", "INR"]:
            amount_safe_to_pay = round(amount_safe_to_pay, 2)
        else:
            amount_safe_to_pay = round(amount_safe_to_pay, 2)

        # Compute earliest_date_for_full_payment
        earliest_date = ""
        if amount_safe_to_pay == req_amt:
            earliest_date = format_date(req_date)
        else:
            # Check candidate dates where salary or other income credits arrive
            # Scan all days in [req_date, end_date]
            for day_idx in range(91):
                test_date = req_date + timedelta(days=day_idx)
                # Check if paying req_amt on test_date is safe for all days from test_date to end_date
                # Balance on test_date must be >= req_amt + min_bal
                is_safe = True
                for future_idx in range(day_idx, 91):
                    future_date = req_date + timedelta(days=future_idx)
                    # Baseline balance at future_date minus req_amt
                    if baseline_daily_balance[future_date] - req_amt < min_bal:
                        is_safe = False
                        break
                if is_safe:
                    earliest_date = format_date(test_date)
                    break

        return {
            "req_date": req_date,
            "end_date": end_date,
            "cur_bal": cur_bal,
            "min_bal": min_bal,
            "req_amt": req_amt,
            "baseline_daily_balance": baseline_daily_balance,
            "daily_flows": daily_flows,
            "projected_events": projected_events,
            "amount_safe_to_pay": amount_safe_to_pay,
            "earliest_date_for_full_payment": earliest_date,
            "stoppable_candidates": stoppable_candidates,
            "reducible_candidates": reducible_candidates,
        }

    def simulate_plan(
        self,
        forecast_result: Dict[str, Any],
        payments: List[Tuple[datetime.date, float]],
        applied_spending_changes: List[Tuple[str, str, float]] = None,
    ) -> bool:
        """
        Simulates applying a set of payments and optional spending changes.
        applied_spending_changes: List of ('stop'|'reduce_to', event_id, savings_per_occurrence)
        Returns True if min_bal is satisfied throughout the 90 days.
        """
        if applied_spending_changes is None:
            applied_spending_changes = []

        req_date = forecast_result["req_date"]
        min_bal = forecast_result["min_bal"]
        cur_bal = forecast_result["cur_bal"]

        # Build adjusted daily flows
        adjusted_flows = defaultdict(float, forecast_result["daily_flows"])

        # Apply spending changes savings to recurring events
        if applied_spending_changes:
            change_map = {eid: (action, savings) for action, eid, savings in applied_spending_changes}
            for pe in forecast_result["projected_events"]:
                eid = pe["event_id"]
                if eid in change_map:
                    action, savings = change_map[eid]
                    # Since pe was a debit (-amt), reducing/stopping it adds savings back
                    adjusted_flows[pe["date"]] += savings

        # Apply proposed payments
        for p_date, p_amt in payments:
            adjusted_flows[p_date] -= p_amt

        # Run simulation
        bal = cur_bal
        for day_idx in range(91):
            d = req_date + timedelta(days=day_idx)
            bal += adjusted_flows[d]
            if bal < min_bal:
                return False

        return True
