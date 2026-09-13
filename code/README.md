# Buy or Wait? — AI Financial Affordability Agent

Autonomous, deterministic financial affordability agent for the **HackerRank Orchestrate** hackathon challenge.

For every purchase or payment request in `dataset/requests.csv`, the agent decides whether the user should:
- Pay in full (`full_payment`)
- Pay partially (`partial_payment`)
- Use an available installment plan (`installments`)
- Wait until safe (`wait`)
- Not proceed (`not_recommended`)

The solution reconstructs the user's daily financial position across a 90-day simulation horizon from structured profiles, dated historical events, foreign exchange rates, recurring commitments, minimum balance constraints, provider payment options, and supporting messages/images.

---

## Architecture Overview

The system is constructed with strict separation between multimodal evidence extraction, cash flow reconciliation, deterministic simulation, and candidate plan optimization:

1. **Multimodal Vision Extractor (`vision_extractor.py`, `image_cache.json`)**:
   - Resolves missing event amounts from receipt and invoice images in `dataset/media/images/`.
   - Incorporates a verified persistent cache with graceful VLM fallback (`gemini-2.5-flash`).

2. **Data Loader & Normalizer (`data_loader.py`)**:
   - Parses `financial_profiles.csv`, `financial_events.csv`, `exchange_rates.csv`, `requests.csv`, `request_payment_options.csv`, `messages.csv`, and `images.csv`.
   - Converts all foreign-currency cash events to the user's `home_currency` using fixed dated exchange rates matching `(settlement_date, from_currency, to_currency)`.

3. **Conflict Resolution Layer (`conflict_resolver.py`)**:
   - Filters out non-cash records, unrealized investments, cancelled events, failed transactions, and unconfirmed pending credits.
   - Reconciles messages up to `request_date` to detect employer payroll revisions, contract expirations, rent increases (e.g. 12% escalation), and approved client invoices.

4. **Cash Flow Forecast Engine (`forecast_engine.py`)**:
   - Detects recurring expenses, cadence intervals (weekly, bi-weekly, monthly), and day-of-month salary credits.
   - Computes daily balances over a 90-day horizon from `request_date`.
   - Calculates `amount_safe_to_pay` as the maximum immediate spend that keeps projected balance above `minimum_balance_to_keep`.
   - Identifies `earliest_date_for_full_payment` on conservative salary settlement dates.

5. **Decision & Plan Optimization Engine (`decision_engine.py`)**:
   - Generates candidate plans across all eligible payment methods:
     - `full_payment` today (safe or with spending changes)
     - `installments` from `request_payment_options.csv` (respecting `max_installment_months`)
     - `partial_payment` (safe amount today + remainder on earliest date)
     - `wait` (full payment on earliest date)
     - `not_recommended` (when unsafe)
   - Searches for permitted spending adjustments (`stop:<event_id>` or `reduce_to:<event_id>:<new_amount>`) up to 3 actions in flexible categories.
   - Applies the 6-rule tie-breaking ranking to select the optimal plan.

6. **Grounded Explanation Generator (`explanation_generator.py`)**:
   - Synthesizes concise, grounded explanations quoting verified amounts, dates, and minimum balance protections.

---

## Setup & Dependencies

The solution requires Python 3.9+ and uses standard library components with optional `numpy` for cadence statistics:

```bash
pip install -r requirements.txt
```

### Environment Variables
Optional Gemini API key for dynamic VLM fallback if evaluating against new/unseen images:

```bash
cp .env.example .env
# Set GEMINI_API_KEY if needed (not required for standard evaluation run)
```

---

## How to Run

### 1. Generate Full Evaluation Output
Run the agent from the repo root to evaluate all 250 requests in `dataset/requests.csv` and write `output.csv`:

```bash
python code/main.py --output output.csv
```

### 2. Validate Output Schema & Rules
Validate the output format, bounds, enums, dates, and consistency:

```bash
python code/evaluation/validate_output.py output.csv dataset
```

### 3. Run Benchmark on Sample Requests
Evaluate against public `dataset/sample_requests.csv`:

```bash
python code/evaluation/benchmark_samples.py
```

---

## Output Contract Compliance

The produced `output.csv` conforms strictly to the required 8 columns in order:
```text
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```
- Exactly 250 rows matching evaluation request order.
- Deterministic execution without non-reproducible LLM randomness.
- No secrets logged or committed.
