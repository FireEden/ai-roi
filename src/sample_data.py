"""
sample_data.py
--------------
Defines the data model for the AI adoption ROI tool and builds a realistic
sample company with six AI use cases.

The tool answers a post-adoption question: "Now that we've adopted AI, is it
actually paying off?" So the inputs are framed as things a company would
actually have data on a few months in — real token spend, license invoices,
hours logged, hours saved, and so on.

Two tiers of information are modeled (kept deliberately separate):

  1. FINANCIAL (dollars) — every cost and benefit that can honestly be put in
     dollars. These drive ROI, payback, and NPV.

  2. QUALITATIVE (scores) — the human/organizational factors that shouldn't be
     faked into dollars (learning curve, change fatigue, etc.). These are rated
     on intuitive scales and shown as a separate readiness scorecard.

Running this file writes the sample company to: data/sample_company.json
"""

import json
import os


# ----------------------------------------------------------------------
# The data model, described in plain terms
# ----------------------------------------------------------------------
# A "use case" is one area where the company applies AI (e.g. a coding
# assistant for engineering). Each use case is a dictionary with:
#
#   name            : display name
#   team            : which part of the business it serves
#   start_month     : month index (0-based) when adoption began, so different
#                     use cases can have started at different times
#   monthly_costs   : recurring dollar costs each month it's active, broken
#                     into named line items (tokens, licenses, infra)
#   one_time_costs  : upfront dollar costs in the month adoption began
#                     (setup/integration hours, initial training), as line items
#   monthly_benefits: recurring dollar benefits each month, as line items, each
#                     with a "realization" fraction (defaults to 1.0 = 100%).
#                     The realization field is the hook for a future "soft-factor
#                     haircut" feature; at 1.0 it has no effect.
#   ramp_months     : how many months benefits take to reach full value. During
#                     ramp, benefits scale linearly from 0% up to 100%. This is
#                     what creates the realistic "J-curve" (costs first, benefits
#                     later).
#   qualitative     : the non-dollar scores (see QUALITATIVE_SCALES below)
#
# Keeping benefits and costs as named line items (not single totals) means the
# app can show a breakdown and the user can edit any single line.


# ----------------------------------------------------------------------
# Qualitative scales: each factor rated 1-5, with human-readable labels
# ----------------------------------------------------------------------
# These are intentionally NOT dollars. Higher is always "better/healthier" so
# the scorecard reads consistently (5 = great, 1 = concerning).
QUALITATIVE_SCALES = {
    "learning_curve": {
        "label": "Learning curve",
        "levels": {
            1: "Very challenging to learn",
            2: "Challenging",
            3: "Moderate",
            4: "Easy to pick up",
            5: "Easy peasy lemon squeezy",
        },
    },
    "change_fatigue": {
        "label": "Change fatigue",
        "levels": {
            1: "Very fatigued",
            2: "Fatigued",
            3: "Neutral",
            4: "Adjusting well",
            5: "Very well adjusted",
        },
    },
    "job_security_sentiment": {
        "label": "Job-security sentiment",
        "levels": {
            1: "Very anxious",
            2: "Anxious",
            3: "Uncertain",
            4: "Reassured",
            5: "Confident & secure",
        },
    },
    "leadership_buyin": {
        "label": "Leadership buy-in",
        "levels": {
            1: "Actively skeptical",
            2: "Hesitant",
            3: "Neutral",
            4: "Supportive",
            5: "Strong champion",
        },
    },
    "workflow_disruption": {
        "label": "Workflow fit",
        "levels": {
            1: "Highly disruptive",
            2: "Disruptive",
            3: "Some friction",
            4: "Fits well",
            5: "Seamless fit",
        },
    },
}


def _benefit(amount, realization=1.0):
    """Helper to build a benefit line item with a realization fraction."""
    return {"amount": amount, "realization": realization}


# ----------------------------------------------------------------------
# The sample company: six use cases with deliberately different shapes
# ----------------------------------------------------------------------
def build_sample_company():
    """Return the sample company as a plain dictionary.

    The numbers are illustrative but chosen to behave realistically:
    a couple of clear winners, a couple still ramping, and at least one
    that's underwater early (security & compliance).
    """
    use_cases = [
        # --- Coding assistant: strong winner, fast ramp ---
        {
            "name": "Coding Assistant",
            "team": "Engineering",
            "start_month": 0,
            "ramp_months": 3,
            "monthly_costs": {
                "tokens_api": 4200,       # heavy usage by many engineers
                "licenses": 9500,         # per-seat subscriptions
                "infrastructure": 800,
            },
            "one_time_costs": {
                "setup_integration": 18000,   # wiring into CI, IDEs, repos
                "initial_training": 12000,
            },
            "monthly_benefits": {
                "engineering_hours_saved": _benefit(52000),  # big time savings
                "faster_delivery_value": _benefit(15000),
                "reduced_bug_rework": _benefit(8000),
            },
            "qualitative": {
                "learning_curve": 4,
                "change_fatigue": 4,
                "job_security_sentiment": 3,
                "leadership_buyin": 5,
                "workflow_disruption": 4,
            },
        },
        # --- Customer support: positive, moderate ---
        {
            "name": "Customer Support AI",
            "team": "Customer Support",
            "start_month": 1,
            "ramp_months": 4,
            "monthly_costs": {
                "tokens_api": 3800,
                "licenses": 6000,
                "infrastructure": 700,
            },
            "one_time_costs": {
                "setup_integration": 22000,   # knowledge base, CRM integration
                "initial_training": 9000,
            },
            "monthly_benefits": {
                "ticket_deflection_savings": _benefit(28000),
                "faster_handle_time": _benefit(14000),
            },
            "qualitative": {
                "learning_curve": 4,
                "change_fatigue": 3,
                "job_security_sentiment": 2,   # support staff most anxious
                "leadership_buyin": 4,
                "workflow_disruption": 3,
            },
        },
        # --- Marketing / Ad: positive but fuzzier ---
        {
            "name": "Marketing & Ad Content",
            "team": "Marketing",
            "start_month": 2,
            "ramp_months": 3,
            "monthly_costs": {
                "tokens_api": 2100,
                "licenses": 4500,
                "infrastructure": 400,
            },
            "one_time_costs": {
                "setup_integration": 8000,
                "initial_training": 6000,
            },
            "monthly_benefits": {
                "content_velocity_value": _benefit(19000),
                "agency_cost_avoided": _benefit(11000),
            },
            "qualitative": {
                "learning_curve": 5,
                "change_fatigue": 4,
                "job_security_sentiment": 3,
                "leadership_buyin": 4,
                "workflow_disruption": 4,
            },
        },
        # --- Accounting: marginal early, heavy setup, slow ramp ---
        {
            "name": "Accounting Automation",
            "team": "Finance & Accounting",
            "start_month": 1,
            "ramp_months": 6,            # slow, careful ramp
            "monthly_costs": {
                "tokens_api": 1500,
                "licenses": 7000,
                "infrastructure": 600,
            },
            "one_time_costs": {
                "setup_integration": 30000,   # ERP integration, controls
                "initial_training": 11000,
            },
            "monthly_benefits": {
                "reconciliation_hours_saved": _benefit(16000),
                "faster_close_value": _benefit(7000),
            },
            "qualitative": {
                "learning_curve": 2,
                "change_fatigue": 3,
                "job_security_sentiment": 2,
                "leadership_buyin": 3,
                "workflow_disruption": 2,    # disrupts established controls
            },
        },
        # --- Talent Acquisition: mixed, smaller scale ---
        {
            "name": "Talent Acquisition AI",
            "team": "People / HR",
            "start_month": 3,
            "ramp_months": 4,
            "monthly_costs": {
                "tokens_api": 900,
                "licenses": 3500,
                "infrastructure": 300,
            },
            "one_time_costs": {
                "setup_integration": 7000,
                "initial_training": 5000,
            },
            "monthly_benefits": {
                "screening_hours_saved": _benefit(9000),
                "faster_time_to_hire_value": _benefit(6000),
            },
            "qualitative": {
                "learning_curve": 3,
                "change_fatigue": 3,
                "job_security_sentiment": 3,
                "leadership_buyin": 3,
                "workflow_disruption": 3,
            },
        },
        # --- Corporate Security & Compliance: underwater early ---
        {
            "name": "Security & Compliance AI",
            "team": "Corporate Security & Compliance",
            "start_month": 2,
            "ramp_months": 8,            # very slow ramp, heavy governance
            "monthly_costs": {
                "tokens_api": 2600,
                "licenses": 11000,       # expensive enterprise/security tooling
                "infrastructure": 1500,
            },
            "one_time_costs": {
                "setup_integration": 45000,   # heaviest setup of all
                "initial_training": 14000,
            },
            "monthly_benefits": {
                "threat_triage_hours_saved": _benefit(13000),
                "audit_prep_savings": _benefit(6000),
            },
            "qualitative": {
                "learning_curve": 2,
                "change_fatigue": 2,
                "job_security_sentiment": 3,
                "leadership_buyin": 3,
                "workflow_disruption": 2,
            },
        },
    ]

    company = {
        # Global assumptions that apply across all use cases.
        "settings": {
            "horizon_months": 24,        # default 2-year view (1-3 yr range)
            "discount_rate_annual": 0.09,  # 9% default, user-adjustable
            "currency": "USD",
        },
        "use_cases": use_cases,
        # Store the scales with the data so the app always has the labels.
        "qualitative_scales": QUALITATIVE_SCALES,
    }
    return company


if __name__ == "__main__":
    company = build_sample_company()

    os.makedirs("data", exist_ok=True)
    out_path = os.path.join("data", "sample_company.json")
    with open(out_path, "w") as f:
        json.dump(company, f, indent=2)

    # Quick summary so we can sanity-check when running the script.
    print(f"Sample company written to: {out_path}\n")
    print(f"Use cases: {len(company['use_cases'])}")
    print(f"Horizon: {company['settings']['horizon_months']} months, "
          f"discount rate: {company['settings']['discount_rate_annual']:.0%}\n")
    print(f"{'Use case':<28} {'Team':<32} {'Mo. cost':>10} {'Mo. benefit':>12}")
    print("-" * 84)
    for uc in company["use_cases"]:
        mo_cost = sum(uc["monthly_costs"].values())
        mo_benefit = sum(b["amount"] for b in uc["monthly_benefits"].values())
        print(f"{uc['name']:<28} {uc['team']:<32} {mo_cost:>10,} {mo_benefit:>12,}")
