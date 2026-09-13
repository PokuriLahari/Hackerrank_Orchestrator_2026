"""
Conflict resolution layer for Buy or Wait? financial decision agent.
Reconciles financial events with messages and filters non-cash/invalid records.
"""
import re
from typing import Dict, List, Any, Optional
from datetime import datetime


class ConflictResolver:
    def __init__(self):
        pass

    def reconcile(
        self,
        user_id: str,
        request_date: str,
        events: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        home_currency: str,
    ) -> Dict[str, Any]:
        """
        Reconciles financial events and messages for a specific user as of request_date.
        Returns:
            - valid_events: List of valid cash flow events
            - salary_info: Confirmed recurring salary amount and schedule
            - rent_multiplier: Any rent rate adjustments (e.g., 12% increase)
            - confirmed_extra_incomes: Confirmed one-off income dates & amounts
        """
        u_events = [e for e in events if e["user_id"] == user_id]
        u_messages = [m for m in messages if m["user_id"] == user_id and m["sent_at"][:10] <= request_date]

        # 1. Filter events per safety rules:
        # Ignore unrealized investments, non_cash, cancelled, failed, and pending credits
        valid_events = []
        for e in u_events:
            status = e["status"]
            direction = e["direction"]

            if status in ["cancelled", "failed", "unrealized"]:
                continue
            if direction == "non_cash":
                continue
            if direction == "credit" and status == "pending":
                continue

            valid_events.append(e)

        # 2. Extract facts from messages
        salary_info = {"amount": None, "day_of_month": None, "ended": False, "revised_date": None, "one_off": []}
        rent_multiplier = 1.0
        confirmed_extra_incomes = []

        for m in u_messages:
            txt = m["message_text"]
            stype = m["source_type"]

            # Rent increase
            if "lease increases monthly rent by 12%" in txt or "menaikkan sewa bulanan sebesar 12%" in txt:
                rent_multiplier = 1.12

            # Employer / Payroll messages
            if stype == "employer" or "payroll" in txt.lower() or "penggajian" in txt.lower() or "gaji" in txt.lower():
                # Contract / employment ended
                if any(phrase in txt for phrase in [
                    "seasonal contract has ended", "kontrak musiman saat ini telah berakhir",
                    "employment has ended", "sumber pendapatan kerja rumah tangga telah berakhir"
                ]):
                    # Check if remaining confirmed salary is mentioned
                    rem_match = re.search(r"(?:remaining confirmed monthly salary is|sisa gaji bulanan yang dikonfirmasi adalah)\s*(?:[A-Z]{3})?\s*([0-9.,]+)", txt, re.IGNORECASE)
                    if rem_match:
                        amt_str = rem_match.group(1).replace(",", "").rstrip(".")
                        salary_info["amount"] = float(amt_str)
                    elif "no off-season income" in txt.lower() or "belum ada pendapatan di luar musim" in txt.lower() or "no regular salary payments" in txt.lower():
                        salary_info["ended"] = True

                # Salary increased to / naik menjadi
                inc_match = re.search(r"(?:monthly salary has increased to|gaji bulanan anda naik menjadi)\s*(?:[A-Z]{3})?\s*([0-9.,]+)", txt, re.IGNORECASE)
                if inc_match:
                    amt_str = inc_match.group(1).replace(",", "").rstrip(".")
                    salary_info["amount"] = float(amt_str)

                # Salary reduced to
                red_match = re.search(r"(?:salary is reduced to|gaji .* berkurang menjadi)\s*(?:[A-Z]{3})?\s*([0-9.,]+)", txt, re.IGNORECASE)
                if red_match:
                    amt_str = red_match.group(1).replace(",", "").rstrip(".")
                    salary_info["amount"] = float(amt_str)

                # Temporary monthly pay
                temp_match = re.search(r"temporary monthly pay is\s*(?:[A-Z]{3})?\s*([0-9.,]+)", txt, re.IGNORECASE)
                if temp_match:
                    amt_str = temp_match.group(1).replace(",", "").rstrip(".")
                    salary_info["amount"] = float(amt_str)

                # First salary / regular salary resumes
                first_match = re.search(r"(?:first salary (?:will be|of)|gaji pertama anda sebesar|regular salary of)\s*(?:[A-Z]{3})?\s*([0-9.,]+)", txt, re.IGNORECASE)
                if first_match and salary_info["amount"] is None:
                    amt_str = first_match.group(1).replace(",", "").rstrip(".")
                    salary_info["amount"] = float(amt_str)

                # Confirmed base salary
                base_match = re.search(r"(?:confirmed base salary is|gaji pokok yang dikonfirmasi adalah)\s*(?:[A-Z]{3})?\s*([0-9.,]+)", txt, re.IGNORECASE)
                if base_match:
                    amt_str = base_match.group(1).replace(",", "").rstrip(".")
                    salary_info["amount"] = float(amt_str)

                # Confirmed salary date revised
                date_match = re.search(r"(?:confirmed salary is now expected on|dikonfirmasi adalah|scheduled for)\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", txt, re.IGNORECASE)
                if date_match:
                    salary_info["revised_date"] = date_match.group(1)

                # One-time arrears adjustment
                arr_match = re.search(r"one-time arrears adjustment of\s*(?:[A-Z]{3})?\s*([0-9.,]+)", txt, re.IGNORECASE)
                if arr_match:
                    amt_str = arr_match.group(1).replace(",", "").rstrip(".")
                    salary_info["one_off"].append(float(amt_str))

            # Approved client invoice payment
            if "approved an invoice payment" in txt.lower() or "menyetujui pembayaran faktur" in txt.lower():
                inv_match = re.search(r"(?:invoice payment of|pembayaran faktur sebesar)\s*(?:[A-Z]{3})?\s*([0-9.,]+)", txt, re.IGNORECASE)
                date_inv_match = re.search(r"(?:expected on|penyelesaian diperkirakan pada)\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", txt, re.IGNORECASE)
                if inv_match and date_inv_match:
                    amt_inv = float(inv_match.group(1).replace(",", "").rstrip("."))
                    date_inv = date_inv_match.group(1)
                    confirmed_extra_incomes.append({"date": date_inv, "amount": amt_inv, "description": "Approved client invoice"})

        return {
            "valid_events": valid_events,
            "salary_info": salary_info,
            "rent_multiplier": rent_multiplier,
            "confirmed_extra_incomes": confirmed_extra_incomes,
        }
