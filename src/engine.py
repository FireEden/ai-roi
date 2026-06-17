"""
engine.py
---------
The financial engine for the AI adoption ROI tool. It takes the data model
(see sample_data.py) and computes month-by-month cash flows, then derives the
headline metrics: ROI, payback period, and NPV.

Everything here is plain arithmetic with exact definitions, so the numbers can
be checked by hand. The app and any notebook import from this one module.

Key modeling choices (agreed during design):
  - COSTS hit at full value from the month a use case starts (you pay for
    licenses and tokens immediately).
  - BENEFITS ramp up linearly from 0% to 100% over `ramp_months`, because value
    takes time to materialize. This asymmetry creates the realistic "J-curve":
    money goes out first, benefits catch up later.
  - One-time costs land entirely in the use case's start month.
  - Each benefit has a `realization` fraction (default 1.0). It scales the
    benefit down if set below 1.0 — the hook for a future soft-factor "haircut".
"""

import pandas as pd


# ----------------------------------------------------------------------
# Per-use-case monthly cash flow
# ----------------------------------------------------------------------
def use_case_cashflow(use_case, horizon_months):
    """Build a month-by-month cash flow table for ONE use case.

    Returns a DataFrame with one row per month (0 .. horizon-1) and columns:
      month, costs, benefits, net, cumulative_net
    plus a breakdown of cost and benefit components.
    """
    start = use_case["start_month"]
    ramp = max(int(use_case["ramp_months"]), 1)  # avoid divide-by-zero

    monthly_costs = use_case["monthly_costs"]
    one_time_costs = use_case.get("one_time_costs", {})
    monthly_benefits = use_case["monthly_benefits"]
    # Optional recurring monthly dollar impacts from readiness factors, each a
    # SIGNED value (negative = a cost like lost productivity, positive = a
    # benefit). Stored as {factor_key: amount}. Defaults to empty.
    readiness_impacts = use_case.get("readiness_dollar_impacts", {})

    total_monthly_cost = sum(monthly_costs.values())
    total_one_time = sum(one_time_costs.values())

    # Full (un-ramped) monthly benefit, and the same WITHOUT the realization
    # haircut — we keep both so we can report the effective adjustment %.
    total_benefit_full_unadjusted = sum(
        b["amount"] for b in monthly_benefits.values()
    )
    total_monthly_benefit_full = sum(
        b["amount"] * b.get("realization", 1.0) for b in monthly_benefits.values()
    )
    # The net signed dollar impact from readiness factors (applied flat each
    # active month). We also keep the gross positive and negative parts so ROI
    # can treat them correctly (positive = benefit, negative = cost).
    total_readiness_impact = sum(readiness_impacts.values())
    gross_positive_impact = sum(v for v in readiness_impacts.values() if v > 0)
    gross_negative_impact = sum(v for v in readiness_impacts.values() if v < 0)

    # The effective realization % across all benefits (for transparency in the
    # detail table). If there are no benefits, treat it as 100%.
    if total_benefit_full_unadjusted > 0:
        effective_realization = total_monthly_benefit_full / total_benefit_full_unadjusted
    else:
        effective_realization = 1.0

    rows = []
    for m in range(horizon_months):
        if m < start:
            # Use case hasn't started yet: no costs, no benefits.
            cost = 0.0
            benefit = 0.0
            readiness_impact = 0.0
            impact_positive = 0.0
            impact_negative = 0.0
        else:
            months_active = m - start  # 0 in the first active month

            # Costs: full monthly cost every active month, plus the one-time
            # cost in the very first active month.
            cost = total_monthly_cost
            if months_active == 0:
                cost += total_one_time

            # Benefits: ramp linearly from 0% up to 100% over `ramp` months.
            # In active month 0 we count the first fractional step; by the time
            # months_active reaches `ramp`, benefits are at full value.
            ramp_fraction = min((months_active + 1) / ramp, 1.0)
            benefit = total_monthly_benefit_full * ramp_fraction

            # Readiness dollar impacts apply flat each active month.
            readiness_impact = total_readiness_impact
            impact_positive = gross_positive_impact
            impact_negative = gross_negative_impact

        # Net = adjusted benefits - costs + signed readiness dollar impacts.
        net = benefit - cost + (readiness_impact if m >= start else 0.0)
        rows.append({
            "month": m,
            "costs": cost,
            "benefits": benefit,
            "readiness_impact": readiness_impact if m >= start else 0.0,
            "impact_positive": impact_positive if m >= start else 0.0,
            "impact_negative": impact_negative if m >= start else 0.0,
            "adjustment_pct": round(effective_realization * 100, 1) if m >= start else 0.0,
            "net": net,
        })

    df = pd.DataFrame(rows)
    df["cumulative_net"] = df["net"].cumsum()
    return df


# ----------------------------------------------------------------------
# Metrics: ROI, payback, NPV
# ----------------------------------------------------------------------
def _roi(total_benefits, total_costs):
    """Return on investment = (benefits - costs) / costs, as a fraction.

    e.g. 0.5 means +50% (you got back 1.5x what you spent). Returns None if
    there are no costs (ROI undefined).
    """
    if total_costs == 0:
        return None
    return (total_benefits - total_costs) / total_costs


def _payback_month(cashflow_df):
    """The first month index where cumulative net turns positive, counting only
    from when the use case is actually active.

    This is when the use case has "paid back" its investment. We ignore any
    leading months where nothing has happened yet (cumulative net sitting at
    exactly 0 before the use case starts), otherwise a delayed-start use case
    would look like it "paid back" in month 0. Returns None if it never pays
    back within the horizon.
    """
    # Find the first month with any activity (a non-zero cost or benefit).
    active = cashflow_df[(cashflow_df["costs"] != 0) | (cashflow_df["benefits"] != 0)]
    if active.empty:
        return None
    first_active = int(active["month"].iloc[0])

    # From the first active month onward, find where cumulative net is >= 0.
    from_active = cashflow_df[cashflow_df["month"] >= first_active]
    positive = from_active[from_active["cumulative_net"] >= 0]
    if positive.empty:
        return None
    return int(positive["month"].iloc[0])


def _npv(net_series, annual_discount_rate):
    """Net present value of a monthly net cash-flow series.

    Future dollars are worth less today, so each month's net is discounted by
    the monthly equivalent of the annual rate. Month 0 is not discounted.
    """
    # Convert the annual rate to a monthly rate: (1+annual)^(1/12) - 1.
    monthly_rate = (1 + annual_discount_rate) ** (1 / 12) - 1
    npv = 0.0
    for m, net in enumerate(net_series):
        npv += net / ((1 + monthly_rate) ** m)
    return npv


def compute_metrics(cashflow_df, annual_discount_rate):
    """Compute the headline metrics from a cash-flow table."""
    base_costs = cashflow_df["costs"].sum()
    base_benefits = cashflow_df["benefits"].sum()

    # Readiness dollar impacts: positive parts count as benefits, negative
    # parts (entered as negatives) count as costs, so ROI stays meaningful.
    pos = cashflow_df.get("impact_positive")
    neg = cashflow_df.get("impact_negative")
    positive_impact = pos.sum() if pos is not None else 0.0
    negative_impact = -neg.sum() if neg is not None else 0.0  # flip sign -> positive cost

    total_costs = base_costs + negative_impact
    total_benefits = base_benefits + positive_impact
    # Net total uses the actual net column, which already includes all impacts.
    net_total = cashflow_df["net"].sum()

    return {
        "total_costs": total_costs,
        "total_benefits": total_benefits,
        "net_total": net_total,
        "roi": _roi(total_benefits, total_costs),
        "payback_month": _payback_month(cashflow_df),
        "npv": _npv(cashflow_df["net"].tolist(), annual_discount_rate),
    }


# ----------------------------------------------------------------------
# Top-level: analyze one use case, or the whole company
# ----------------------------------------------------------------------
def analyze_use_case(use_case, settings):
    """Return both the cash-flow table and the metrics for one use case."""
    horizon = settings["horizon_months"]
    rate = settings["discount_rate_annual"]
    cf = use_case_cashflow(use_case, horizon)
    metrics = compute_metrics(cf, rate)
    return {"name": use_case["name"], "team": use_case["team"],
            "cashflow": cf, "metrics": metrics}


def analyze_company(company):
    """Analyze every use case and the consolidated company total.

    Returns a dict with:
      - "use_cases": list of per-use-case results
      - "company_cashflow": summed monthly cash flow across all use cases
      - "company_metrics": metrics on the consolidated cash flow
    """
    settings = company["settings"]
    horizon = settings["horizon_months"]
    rate = settings["discount_rate_annual"]

    results = [analyze_use_case(uc, settings) for uc in company["use_cases"]]

    # Consolidate: sum the monthly cost/benefit/impact across all use cases.
    combined = pd.DataFrame({"month": range(horizon)})
    combined["costs"] = 0.0
    combined["benefits"] = 0.0
    combined["readiness_impact"] = 0.0
    combined["impact_positive"] = 0.0
    combined["impact_negative"] = 0.0
    for r in results:
        combined["costs"] += r["cashflow"]["costs"].values
        combined["benefits"] += r["cashflow"]["benefits"].values
        combined["readiness_impact"] += r["cashflow"]["readiness_impact"].values
        combined["impact_positive"] += r["cashflow"]["impact_positive"].values
        combined["impact_negative"] += r["cashflow"]["impact_negative"].values
    # Net includes the signed readiness impacts, matching the per-use-case math.
    combined["net"] = combined["benefits"] - combined["costs"] + combined["readiness_impact"]
    combined["cumulative_net"] = combined["net"].cumsum()

    company_metrics = compute_metrics(combined, rate)

    return {
        "use_cases": results,
        "company_cashflow": combined,
        "company_metrics": company_metrics,
    }
