"""
Data loader module for Buy or Wait? financial decision agent.
Parses CSVs, populates missing amounts via images/vision cache, and normalizes foreign currencies.
"""
import os
import csv
from typing import Dict, List, Any, Optional
from vision_extractor import VisionExtractor


class DataLoader:
    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir
        self.vision = VisionExtractor()

    def load_all(self, use_samples: bool = False) -> Dict[str, Any]:
        profiles = self.load_profiles()
        exchange_rates = self.load_exchange_rates()
        events = self.load_financial_events(profiles, exchange_rates)
        messages = self.load_messages()
        payment_options = self.load_payment_options()
        requests = self.load_requests(use_samples=use_samples)

        return {
            "profiles": profiles,
            "exchange_rates": exchange_rates,
            "events": events,
            "messages": messages,
            "payment_options": payment_options,
            "requests": requests,
        }

    def load_profiles(self) -> Dict[str, Dict[str, Any]]:
        path = os.path.join(self.dataset_dir, "financial_profiles.csv")
        profiles = {}
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                uid = row["user_id"]
                profiles[uid] = {
                    "user_id": uid,
                    "home_currency": row["home_currency"],
                    "current_available_balance": float(row["current_available_balance"]),
                    "minimum_balance_to_keep": float(row["minimum_balance_to_keep"]),
                    "financial_priorities": [x for x in row["financial_priorities"].split("|") if x],
                    "expense_categories_to_protect": [x for x in row["expense_categories_to_protect"].split("|") if x],
                    "expense_categories_user_is_willing_to_reduce": [x for x in row["expense_categories_user_is_willing_to_reduce"].split("|") if x],
                    "expense_categories_user_is_willing_to_stop": [x for x in row["expense_categories_user_is_willing_to_stop"].split("|") if x],
                    "payment_methods_user_will_consider": [x for x in row["payment_methods_user_will_consider"].split("|") if x],
                    "max_installment_months": int(row["max_installment_months"]) if row["max_installment_months"].strip() else None,
                }
        return profiles

    def load_exchange_rates(self) -> Dict[tuple, float]:
        path = os.path.join(self.dataset_dir, "exchange_rates.csv")
        rates = {}
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row["rate_date"], row["from_currency"], row["to_currency"])
                rates[key] = float(row["rate"])
        return rates

    def load_images_map(self) -> Dict[str, str]:
        path = os.path.join(self.dataset_dir, "images.csv")
        image_map = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    rel_id = row.get("related_event_id", "").strip()
                    if rel_id:
                        image_map[rel_id] = row["image_id"]
        return image_map

    def load_financial_events(self, profiles: Dict[str, Any], exchange_rates: Dict[tuple, float]) -> List[Dict[str, Any]]:
        path = os.path.join(self.dataset_dir, "financial_events.csv")
        images_map = self.load_images_map()
        events = []

        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                eid = row["event_id"]
                uid = row["user_id"]
                home_curr = profiles[uid]["home_currency"]
                raw_amt_str = row["amount"].strip()

                # Extract missing amount from image if blank
                if not raw_amt_str:
                    img_id = images_map.get(eid)
                    if img_id:
                        img_path = os.path.join(self.dataset_dir, "media", "images", f"{img_id}.png")
                        extracted = self.vision.extract_amount(img_id, eid, img_path)
                        if extracted is not None:
                            raw_amt_str = str(extracted)
                        else:
                            raise ValueError(f"Missing amount for event {eid} could not be extracted from {img_id}")
                    else:
                        raise ValueError(f"Event {eid} has blank amount but no linked image")

                raw_amt = float(raw_amt_str)
                event_curr = row["currency"]
                settle_date = row["settlement_date"]

                # Currency conversion to home_currency
                if event_curr != home_curr:
                    rate_key = (settle_date, event_curr, home_curr)
                    if rate_key not in exchange_rates:
                        raise KeyError(f"No exchange rate found for {rate_key}")
                    rate = exchange_rates[rate_key]
                    amt_home = raw_amt * rate
                else:
                    amt_home = raw_amt

                min_allowed = None
                if row["minimum_allowed_amount"].strip():
                    raw_min = float(row["minimum_allowed_amount"])
                    if event_curr != home_curr:
                        min_allowed = raw_min * exchange_rates[(settle_date, event_curr, home_curr)]
                    else:
                        min_allowed = raw_min

                events.append({
                    "event_id": eid,
                    "user_id": uid,
                    "event_type": row["event_type"],
                    "description": row["description"],
                    "category": row["category"],
                    "direction": row["direction"],
                    "amount": amt_home,
                    "original_amount": raw_amt,
                    "currency": home_curr,
                    "original_currency": event_curr,
                    "event_date": row["event_date"],
                    "settlement_date": settle_date,
                    "status": row["status"],
                    "linked_event_id": row["linked_event_id"].strip(),
                    "flexibility": row["flexibility"],
                    "minimum_allowed_amount": min_allowed,
                })

        return events

    def load_messages(self) -> List[Dict[str, Any]]:
        path = os.path.join(self.dataset_dir, "messages.csv")
        messages = []
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                messages.append({
                    "message_id": row["message_id"],
                    "user_id": row["user_id"],
                    "request_id": row["request_id"].strip(),
                    "related_event_id": row["related_event_id"].strip(),
                    "sent_at": row["sent_at"],
                    "source_type": row["source_type"],
                    "message_text": row["message_text"],
                })
        return messages

    def load_payment_options(self) -> List[Dict[str, Any]]:
        path = os.path.join(self.dataset_dir, "request_payment_options.csv")
        options = []
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                options.append({
                    "payment_option_id": row["payment_option_id"],
                    "request_id": row["request_id"],
                    "payment_method": row["payment_method"],
                    "payment_amount": float(row["payment_amount"]),
                    "number_of_payments": int(row["number_of_payments"]),
                    "first_payment_date": row["first_payment_date"],
                    "payment_frequency_days": int(row["payment_frequency_days"]) if row["payment_frequency_days"].strip() else 0,
                    "financing_fee": float(row["financing_fee"]) if row["financing_fee"].strip() else 0.0,
                    "total_payable_amount": float(row["total_payable_amount"]),
                })
        return options

    def load_requests(self, use_samples: bool = False) -> List[Dict[str, Any]]:
        filename = "sample_requests.csv" if use_samples else "requests.csv"
        path = os.path.join(self.dataset_dir, filename)
        reqs = []
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                item = {
                    "request_id": row["request_id"],
                    "user_id": row["user_id"],
                    "request_date": row["request_date"],
                    "request_type": row["request_type"],
                    "requested_amount": float(row["requested_amount"]),
                    "desired_completion_date": row["desired_completion_date"],
                    "allows_partial_payment": row["allows_partial_payment"].strip().lower() == "true",
                    "request_text": row["request_text"],
                }
                if use_samples:
                    item["expected_amount_safe_to_pay"] = float(row["amount_safe_to_pay"])
                    item["expected_affordability_status"] = row["affordability_status"]
                    item["expected_recommended_payment_method"] = row["recommended_payment_method"]
                    item["expected_payment_plan"] = row["payment_plan"]
                    item["expected_earliest_date_for_full_payment"] = row["earliest_date_for_full_payment"]
                    item["expected_spending_changes_needed"] = row["spending_changes_needed"]
                    item["expected_decision_explanation"] = row["decision_explanation"]
                reqs.append(item)
        return reqs
