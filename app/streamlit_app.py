"""
streamlit_app.py
----------------
Interactive app for the AI Adoption ROI tool. It wraps the financial engine
(src/engine.py) so a user can edit a use case's costs and benefits and see its
economics update live.

Post-adoption framing: "Now that we've adopted AI, is it paying off?"

This piece builds the FIRST tab (Use Case). Company and Scorecard tabs come
next. Inputs start from the sample company and are fully editable; edits are
held per use case in session state so switching use cases doesn't lose them.

Run from the project root:
    streamlit run app/streamlit_app.py
"""

import sys
import os
import json
import copy

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import analyze_use_case, analyze_company


# ----------------------------------------------------------------------
# Shared chart styling — one place so every chart looks consistent & modern
# ----------------------------------------------------------------------
# A cohesive palette and a common layout applied to every figure. Keeping this
# in one helper means the whole app shares a single, deliberate visual style
# rather than matplotlib's dated defaults.
COLORS = {
    "primary": "#4F46E5",    # indigo (matches the app accent)
    "positive": "#10B981",   # emerald green
    "negative": "#EF4444",   # red
    "neutral": "#94A3B8",    # slate gray
    "grid": "rgba(148,163,184,0.18)",   # faint slate, works on any background
    "text": "#1A1A2E",
}


def style_fig(fig, title, y_title, x_title="Month", height=420):
    """Apply the shared modern styling to a Plotly figure.

    Backgrounds are transparent so the chart blends into the page rather than
    sitting on a white card. Lines, text, and grid are chosen to contrast the
    app's light background.
    """
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color=COLORS["text"])),
        xaxis_title=x_title,
        yaxis_title=y_title,
        height=height,
        font=dict(family="system-ui, -apple-system, sans-serif", size=13,
                  color=COLORS["text"]),
        margin=dict(l=60, r=30, t=60, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hovermode="x unified",
        # Transparent backgrounds so the chart melts into the page.
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False, zeroline=False,
                     linecolor=COLORS["grid"])
    fig.update_yaxes(showgrid=True, gridcolor=COLORS["grid"], zeroline=True,
                     zerolinecolor="rgba(148,163,184,0.5)", zerolinewidth=1)
    return fig


# ----------------------------------------------------------------------
# Qualitative scorecard helpers
# ----------------------------------------------------------------------
# These are deliberately kept SEPARATE from the dollar metrics. The scores
# (1-5) measure organizational readiness/health and are never converted to
# money — they sit alongside the financials as a "how much should we trust
# this?" lens.

def readiness_color(avg_score):
    """Pick a color for an average readiness score (1-5)."""
    if avg_score >= 4:
        return COLORS["positive"]
    if avg_score >= 3:
        return "#F59E0B"  # amber
    return COLORS["negative"]


def readiness_label(avg_score):
    """A short plain-language readiness label."""
    if avg_score >= 4:
        return "Healthy"
    if avg_score >= 3:
        return "Watch"
    return "At risk"


def suggested_realization(avg_score):
    """Suggest a benefit-realization % from the average readiness score (1-5).

    This is only a *suggestion* the user can accept or override — the judgment
    stays visible and user-controlled. The mapping is linear across the full
    range: the lowest readiness (1) suggests counting just 20% of benefits,
    and full readiness (5) suggests 100%. So a mid score of 3 maps to 60%.
    Returns an integer percentage.
    """
    # Linear from (score 1 -> 20%) to (score 5 -> 100%).
    pct = 20 + (avg_score - 1) / (5 - 1) * 80
    return int(round(pct))


def _slugify(name):
    """Turn a user-entered category name into a safe dict key."""
    return "_".join(name.strip().lower().split())


def add_remove_controls(uc_name, container_dict, kind_label, key_prefix,
                        is_benefit=False):
    """Render an add-category form and per-item remove buttons.

    container_dict is the dict to mutate (e.g. uc['monthly_costs']).
    Returns nothing; it mutates container_dict in place. The caller is
    responsible for rendering the actual value inputs.
    """
    # Add form: a text box for the name + an Add button.
    with st.popover(f"➕ Add {kind_label}"):
        new_name = st.text_input(
            f"New {kind_label} name", key=f"addname_{key_prefix}_{uc_name}",
            placeholder="e.g. Vendor support",
        )
        if st.button(f"Add", key=f"addbtn_{key_prefix}_{uc_name}"):
            cleaned = new_name.strip()
            if cleaned:
                slug = _slugify(cleaned)
                if slug not in container_dict:
                    # Benefits are dicts with amount+realization; costs are plain.
                    container_dict[slug] = (
                        {"amount": 0, "realization": 1.0} if is_benefit else 0
                    )
                st.rerun()


def render_radar(scores, scales, title):
    """Draw a radar (spider) chart of the 1-5 qualitative scores."""
    factor_keys = list(scales.keys())
    labels = [scales[k]["label"] for k in factor_keys]
    values = [scores[k] for k in factor_keys]

    # Close the loop so the radar polygon connects back to the start.
    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]

    avg = sum(values) / len(values)
    color = readiness_color(avg)

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed, theta=labels_closed, fill="toself",
        fillcolor=color, opacity=0.25,
        line=dict(color=color, width=2),
        marker=dict(size=6, color=color),
        hovertemplate="%{theta}: %{r}/5<extra></extra>",
        name="Score",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color=COLORS["text"])),
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 5], tickvals=[1, 2, 3, 4, 5],
                            gridcolor=COLORS["grid"], linecolor=COLORS["grid"]),
            angularaxis=dict(gridcolor=COLORS["grid"], linecolor=COLORS["grid"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=400, showlegend=False,
        font=dict(family="system-ui, -apple-system, sans-serif", size=12,
                  color=COLORS["text"]),
        margin=dict(l=70, r=70, t=60, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig, avg


# ----------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------
st.set_page_config(page_title="AI Adoption ROI", page_icon="🤖", layout="wide")

# --- Light visual polish via CSS ---
# Streamlit's number inputs show the typed value and the -/+ stepper buttons in
# separate bordered boxes, which looks disjointed. This unifies them into one
# clean bordered control with seamless stepper buttons.
st.markdown(
    """
    <style>
    /* Unify the number-input field and its +/- stepper into one border */
    div[data-testid="stNumberInput"] > div {
        border: 1px solid rgba(148,163,184,0.4);
        border-radius: 8px;
        overflow: hidden;
    }
    div[data-testid="stNumberInput"] > div > div {
        border: none !important;
    }
    /* Stepper buttons: no separate border, subtle hover */
    div[data-testid="stNumberInput"] button {
        border: none !important;
        background: transparent;
    }
    div[data-testid="stNumberInput"] button:hover {
        background: rgba(79,70,229,0.08);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("AI Adoption ROI Model")
st.caption(
    "Is our AI adoption paying off? Model the costs and benefits of each AI "
    "use case, with realistic ramp-up, and see ROI, payback, and NPV."
)


# ----------------------------------------------------------------------
# Load the sample company once, then keep an editable copy in session state
# ----------------------------------------------------------------------
@st.cache_data
def load_sample():
    path = os.path.join(PROJECT_ROOT, "data", "sample_company.json")
    with open(path) as f:
        return json.load(f)


sample = load_sample()

# "company" is the user's working copy — starts as the sample, gets edited.
if "company" not in st.session_state:
    st.session_state.company = copy.deepcopy(sample)

company = st.session_state.company


# ----------------------------------------------------------------------
# Sidebar: global settings (apply to every use case)
# ----------------------------------------------------------------------
st.sidebar.header("Global settings")

horizon = st.sidebar.slider(
    "Time horizon (months)", min_value=12, max_value=36,
    value=company["settings"]["horizon_months"], step=1,
    help="How far out to model. AI tooling decisions are usually evaluated "
         "over 1-3 years.",
)
company["settings"]["horizon_months"] = horizon

discount_pct = st.sidebar.slider(
    "Discount rate (annual %)", min_value=0.0, max_value=20.0,
    value=company["settings"]["discount_rate_annual"] * 100, step=0.5,
    help="Used for NPV — the rate at which future dollars are worth less today. "
         "A typical corporate rate is around 8-10%.",
)
company["settings"]["discount_rate_annual"] = discount_pct / 100

if st.sidebar.button("Reset all to sample data"):
    st.session_state.company = copy.deepcopy(sample)
    st.rerun()


# ----------------------------------------------------------------------
# Helper: format a dollar figure compactly
# ----------------------------------------------------------------------
def fmt_money(x):
    if abs(x) >= 1e6:
        return f"${x/1e6:,.2f}M"
    if abs(x) >= 1e3:
        return f"${x/1e3:,.0f}K"
    return f"${x:,.0f}"


# ----------------------------------------------------------------------
# Helper: the J-curve cash flow chart for one use case (Plotly)
# ----------------------------------------------------------------------
def render_jcurve(cashflow, name):
    # Color each monthly-net bar green (positive) or red (negative).
    bar_colors = [
        COLORS["positive"] if n >= 0 else COLORS["negative"]
        for n in cashflow["net"]
    ]

    fig = go.Figure()
    # Monthly net as semi-transparent bars (shows the early cost pain).
    fig.add_trace(go.Bar(
        x=cashflow["month"], y=cashflow["net"],
        name="Monthly net", marker_color=bar_colors, opacity=0.45,
        hovertemplate="Month %{x}<br>Net: $%{y:,.0f}<extra></extra>",
    ))
    # Cumulative net as the headline J-curve line.
    fig.add_trace(go.Scatter(
        x=cashflow["month"], y=cashflow["cumulative_net"],
        name="Cumulative net", mode="lines+markers",
        line=dict(color=COLORS["primary"], width=3),
        marker=dict(size=5),
        hovertemplate="Month %{x}<br>Cumulative: $%{y:,.0f}<extra></extra>",
    ))
    style_fig(fig, f"{name}: Cash Flow Over Time (the J-curve)", "Dollars")
    st.plotly_chart(fig, use_container_width=True)


# ======================================================================
# TABS
# ======================================================================
tab_usecase, tab_company = st.tabs(["📊 Use Case", "🏢 Company (consolidated)"])


with tab_usecase:
    # --- Pick a use case ---
    names = [uc["name"] for uc in company["use_cases"]]
    selected_name = st.selectbox("Use case", names, key="uc_picker")
    # Find the actual dict we'll edit in place.
    uc = next(u for u in company["use_cases"] if u["name"] == selected_name)

    st.caption(f"Team: {uc['team']}")

    # --- Editable inputs, grouped in a bordered container ---
    with st.container(border=True):
        st.markdown("##### Inputs")
        st.caption("Edit any figure to match your own numbers. Changes are kept as you go.")

        timing_col, cost_col, benefit_col = st.columns([1, 1, 1.2])

    with timing_col:
        st.markdown("**Timing**")
        uc["start_month"] = st.number_input(
            "Start month", min_value=0, max_value=horizon - 1,
            value=uc["start_month"], step=1, key=f"start_{selected_name}",
            help="Month the use case began (0 = first month of the horizon).",
        )
        uc["ramp_months"] = st.number_input(
            "Ramp months", min_value=1, max_value=18,
            value=uc["ramp_months"], step=1, key=f"ramp_{selected_name}",
            help="How long benefits take to reach full value.",
        )

    with cost_col:
        st.markdown("**Monthly costs ($)**")
        for item in list(uc["monthly_costs"].keys()):
            row = st.columns([4, 1])
            with row[0]:
                uc["monthly_costs"][item] = st.number_input(
                    item.replace("_", " ").title(),
                    min_value=0, value=int(uc["monthly_costs"][item]), step=100,
                    key=f"mc_{selected_name}_{item}",
                )
            with row[1]:
                st.markdown("<div style='height:1.8em'></div>", unsafe_allow_html=True)
                if st.button("✕", key=f"delmc_{selected_name}_{item}",
                             help=f"Remove {item}"):
                    del uc["monthly_costs"][item]
                    st.rerun()
        add_remove_controls(selected_name, uc["monthly_costs"],
                            "monthly cost", "mc")

        st.markdown("**One-time costs ($)**")
        for item in list(uc["one_time_costs"].keys()):
            row = st.columns([4, 1])
            with row[0]:
                uc["one_time_costs"][item] = st.number_input(
                    item.replace("_", " ").title(),
                    min_value=0, value=int(uc["one_time_costs"][item]), step=500,
                    key=f"otc_{selected_name}_{item}",
                )
            with row[1]:
                st.markdown("<div style='height:1.8em'></div>", unsafe_allow_html=True)
                if st.button("✕", key=f"delotc_{selected_name}_{item}",
                             help=f"Remove {item}"):
                    del uc["one_time_costs"][item]
                    st.rerun()
        add_remove_controls(selected_name, uc["one_time_costs"],
                            "one-time cost", "otc")

    with benefit_col:
        st.markdown("**Monthly benefits ($)**")
        st.caption(
            "For each benefit, set how much you're realistically capturing "
            "(the realization %). Low adoption means you may not get the full "
            "benefit yet."
        )
        for item in list(uc["monthly_benefits"].keys()):
            current = uc["monthly_benefits"][item]
            row = st.columns([4, 1])
            with row[0]:
                uc["monthly_benefits"][item]["amount"] = st.number_input(
                    item.replace("_", " ").title(),
                    min_value=0, value=int(current["amount"]), step=500,
                    key=f"mb_{selected_name}_{item}",
                )
            with row[1]:
                st.markdown("<div style='height:1.8em'></div>", unsafe_allow_html=True)
                if st.button("✕", key=f"delmb_{selected_name}_{item}",
                             help=f"Remove {item}"):
                    del uc["monthly_benefits"][item]
                    st.rerun()
            # Realization slider (0-100%). Stored as a 0-1 fraction.
            real_key = f"real_{selected_name}_{item}"
            if real_key not in st.session_state:
                st.session_state[real_key] = int(round(current.get("realization", 1.0) * 100))
            real_pct = st.slider(
                "Realization %", min_value=0, max_value=100, step=5,
                key=real_key,
                help="What fraction of this benefit you're actually capturing. "
                     "100% = full benefit; lower discounts it.",
            )
            uc["monthly_benefits"][item]["realization"] = real_pct / 100
            effective = uc["monthly_benefits"][item]["amount"] * (real_pct / 100)
            if real_pct < 100:
                st.caption(f"   → counting {fmt_money(effective)}/mo "
                           f"(of {fmt_money(current['amount'])})")
        add_remove_controls(selected_name, uc["monthly_benefits"],
                            "monthly benefit", "mb", is_benefit=True)

    # --- Pre-seed readiness inputs from session state before analyzing ---
    # The readiness widgets are rendered lower on the page, but Streamlit holds
    # their values in session state by key. Reading them here (before we run the
    # engine) ensures the metrics, J-curve, and detail table reflect the current
    # readiness scores and dollar impacts in the same render — no one-step lag.
    if "readiness_dollar_impacts" not in uc:
        uc["readiness_dollar_impacts"] = {}
    for key in company["qualitative_scales"].keys():
        q_key = f"q_{selected_name}_{key}"
        if q_key in st.session_state:
            uc["qualitative"][key] = st.session_state[q_key]
        d_key = f"dimp_{selected_name}_{key}"
        if d_key in st.session_state:
            uc["readiness_dollar_impacts"][key] = st.session_state[d_key]

    # --- Run the engine on this (possibly edited) use case ---
    result = analyze_use_case(uc, company["settings"])
    metrics = result["metrics"]
    cashflow = result["cashflow"]

    # --- Headline metrics, grouped in a bordered container ---
    st.markdown("")  # small spacer
    with st.container(border=True):
        st.markdown(f"##### {selected_name}: results")
        c1, c2, c3, c4 = st.columns(4)
        roi_str = f"{metrics['roi']:.0%}" if metrics["roi"] is not None else "n/a"
        c1.metric("ROI", roi_str,
                  help="(Total benefits - total costs) / total costs over the horizon.")
        if metrics["payback_month"] is not None:
            c2.metric("Payback", f"Month {metrics['payback_month']}")
        else:
            c2.metric("Payback", "Never", help="Does not pay back within the horizon.")
        c3.metric("NPV", fmt_money(metrics["npv"]),
                  help="Net present value: future dollars discounted to today.")
        c4.metric("Net total", fmt_money(metrics["net_total"]),
                  help="Total benefits minus total costs (undiscounted).")

        # A plain-language verdict line.
        if metrics["npv"] > 0 and metrics["payback_month"] is not None:
            st.success(
                f"This use case is paying off: it pays back around month "
                f"{metrics['payback_month']} and has a positive NPV of "
                f"{fmt_money(metrics['npv'])}."
            )
        else:
            st.warning(
                "This use case is underwater over the chosen horizon — costs "
                "outweigh discounted benefits so far."
            )

    # --- The J-curve ---
    render_jcurve(cashflow, selected_name)

    # --- Qualitative readiness scorecard (kept separate from the dollars) ---
    scales = company["qualitative_scales"]
    with st.container(border=True):
        st.markdown("##### Readiness scorecard (the human side)")
        st.caption(
            "These factors are **not** converted to dollars. They're a "
            "health check on how well the organization is absorbing this tool "
            "— a lens on how much to trust the financial result above."
        )

        # Ensure the dollar-impacts dict exists on this use case.
        if "readiness_dollar_impacts" not in uc:
            uc["readiness_dollar_impacts"] = {}

        st.markdown("**Rate each factor (1-5)**")
        st.caption(
            "Set each factor's score on the left. Optionally add a known "
            "**monthly $ impact** on the right (negative = a cost like lost "
            "productivity; positive = a benefit). The $ impacts add to the net "
            "on top of the % haircut."
        )
        # Each factor: score slider on the left, dollar impact on the right.
        for key in scales.keys():
            levels = scales[key]["levels"]
            current = uc["qualitative"][key]
            srow = st.columns([2, 1])
            with srow[0]:
                new_val = st.select_slider(
                    scales[key]["label"],
                    options=[1, 2, 3, 4, 5],
                    value=current,
                    format_func=lambda v, lv=levels: f"{v} — {lv[str(v)]}",
                    key=f"q_{selected_name}_{key}",
                )
                uc["qualitative"][key] = new_val
            with srow[1]:
                dollar = st.number_input(
                    "$ impact / mo",
                    value=int(uc["readiness_dollar_impacts"].get(key, 0)),
                    step=500,
                    key=f"dimp_{selected_name}_{key}",
                    help="Known recurring monthly dollar effect of this factor. "
                         "Negative for a cost, positive for a benefit. Leave 0 "
                         "if none.",
                )
                uc["readiness_dollar_impacts"][key] = dollar

        # Radar chart below the factor rows, centered.
        radar_fig, avg_score = render_radar(
            uc["qualitative"], scales, f"{selected_name}: Readiness"
        )
        st.plotly_chart(radar_fig, use_container_width=True)

        # Readiness summary + the "trust" framing tying tiers together.
        avg = sum(uc["qualitative"].values()) / len(uc["qualitative"])
        label = readiness_label(avg)
        st.markdown(
            f"**Overall readiness: {avg:.1f}/5 — {label}**"
        )

        # --- The bridge: suggest a benefit realization % from readiness ---
        # This connects the two tiers WITHOUT hiding the judgment: it proposes
        # a haircut, but the user must click to apply it, and can still adjust
        # each benefit's realization slider by hand afterward.
        suggestion = suggested_realization(avg)
        bcol1, bcol2 = st.columns([2, 1])
        with bcol1:
            st.caption(
                f"Based on this readiness score, a realization of about "
                f"**{suggestion}%** on benefits would be reasonable. You stay "
                f"in control — applying this just sets the benefit sliders "
                f"above, which you can still fine-tune."
            )
        with bcol2:
            # Use an on_click callback so the session-state updates happen
            # BEFORE the sliders are re-instantiated on the next run (Streamlit
            # forbids modifying a widget's state after it's been created).
            def _apply_suggestion(uc_name=selected_name, items=list(uc["monthly_benefits"].keys()),
                                  pct=suggestion):
                for it in items:
                    st.session_state[f"real_{uc_name}_{it}"] = pct

            st.button(
                f"Apply {suggestion}% to all benefits",
                key=f"apply_real_{selected_name}",
                on_click=_apply_suggestion,
            )

        # Combine the two tiers into one honest sentence.
        financially_good = metrics["npv"] > 0 and metrics["payback_month"] is not None
        if financially_good and avg >= 4:
            st.success(
                "Strong on both fronts: the financials are positive and the "
                "organization is absorbing the tool well. High confidence."
            )
        elif financially_good and avg < 3:
            st.warning(
                "The numbers look good, but readiness is low — the projected "
                "benefits are at risk until adoption issues improve. Treat the "
                "financial result with caution."
            )
        elif not financially_good and avg >= 4:
            st.info(
                "Readiness is strong even though the financials aren't there "
                "yet — this may be an early-stage case worth giving more time."
            )
        else:
            st.warning(
                "Weak on both fronts: financials are underwater and readiness "
                "is low. This use case needs attention or reconsideration."
            )

    # --- Detail table + download ---
    with st.expander("See month-by-month detail"):
        st.caption(
            "‘Monthly Benefit’ is the total benefit after the realization "
            "haircut. ‘Overall readiness adj %’ is that realization % (from the "
            "readiness suggestion or your manual setting). ‘Overall readiness "
            "adj $’ is the sum of the per-factor dollar impacts you entered. "
            "‘Net’ includes all of these."
        )
        display_cf = cashflow.rename(columns={
            "month": "Month",
            "costs": "Cost",
            "benefits": "Monthly Benefit",
            "adjustment_pct": "Overall readiness adj %",
            "readiness_impact": "Overall readiness adj $",
            "net": "Net",
            "cumulative_net": "Cumulative net",
        }).drop(columns=["impact_positive", "impact_negative"], errors="ignore")
        col_order = ["Month", "Cost", "Monthly Benefit", "Overall readiness adj %",
                     "Overall readiness adj $", "Net", "Cumulative net"]
        display_cf = display_cf[[c for c in col_order if c in display_cf.columns]]
        st.dataframe(display_cf, width="stretch")
        csv = display_cf.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download this cash flow as CSV", data=csv,
            file_name=f"{selected_name.replace(' ', '_')}_cashflow.csv",
            mime="text/csv",
        )


# ----------------------------------------------------------------------
# COMPANY TAB (consolidated rollup of all use cases)
# ----------------------------------------------------------------------
with tab_company:
    st.subheader("Company-wide view (all AI use cases combined)")
    st.write(
        "This consolidates every use case using your current inputs. The "
        "totals and J-curve below reflect any edits you've made on the Use "
        "Case tab."
    )

    # Run the full company analysis (per use case + consolidated).
    analysis = analyze_company(company)
    cm = analysis["company_metrics"]
    company_cf = analysis["company_cashflow"]

    # --- Company headline metrics, grouped in a bordered container ---
    with st.container(border=True):
        st.markdown("##### Company totals")
        c1, c2, c3, c4 = st.columns(4)
        roi_str = f"{cm['roi']:.0%}" if cm["roi"] is not None else "n/a"
        c1.metric("Company ROI", roi_str,
                  help="(Total benefits - total costs) / total costs across all use cases.")
        if cm["payback_month"] is not None:
            c2.metric("Payback", f"Month {cm['payback_month']}")
        else:
            c2.metric("Payback", "Never")
        c3.metric("NPV", fmt_money(cm["npv"]),
                  help="Net present value of the whole AI program.")
        c4.metric("Net total", fmt_money(cm["net_total"]),
                  help="Total benefits minus total costs across all use cases (undiscounted).")

    # --- The consolidated J-curve ---
    render_jcurve(company_cf, "Company (all use cases)")

    # --- Per-use-case verdict table (the key insight) ---
    st.subheader("How each use case is doing")
    st.write(
        "The company total can hide trouble. This table breaks the result down "
        "by use case, so winners and laggards are visible side by side."
    )

    rows = []
    for r in analysis["use_cases"]:
        m = r["metrics"]
        # A simple verdict label based on NPV and payback.
        if m["npv"] > 0 and m["payback_month"] is not None:
            verdict = "✅ Paying off"
        elif m["npv"] > 0:
            verdict = "🟡 Positive, slow payback"
        else:
            verdict = "🔴 Underwater"

        rows.append({
            "Use case": r["name"],
            "Team": r["team"],
            "ROI": f"{m['roi']:.0%}" if m["roi"] is not None else "n/a",
            "Payback": f"Month {m['payback_month']}" if m["payback_month"] is not None else "Never",
            "NPV": fmt_money(m["npv"]),
            "Verdict": verdict,
        })

    verdict_df = pd.DataFrame(rows)
    st.table(verdict_df)

    # --- A simple NPV-by-use-case bar chart for quick comparison ---
    st.subheader("NPV by use case")
    uc_names = [r["name"] for r in analysis["use_cases"]]
    npvs = [r["metrics"]["npv"] / 1000 for r in analysis["use_cases"]]  # in $K
    bar_colors = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in npvs]

    fig = go.Figure(go.Bar(
        x=uc_names, y=npvs, marker_color=bar_colors,
        hovertemplate="%{x}<br>NPV: $%{y:,.0f}K<extra></extra>",
    ))
    style_fig(fig, "Net Present Value by Use Case", "NPV ($ thousands)", x_title="")
    fig.update_xaxes(tickangle=-20)
    st.plotly_chart(fig, use_container_width=True)

    # --- Company readiness scorecard: financial vs. readiness side by side ---
    st.subheader("Financial result vs. organizational readiness")
    st.write(
        "Each use case plotted by its financial outcome (NPV) against its "
        "readiness score. The healthiest bets are high on both; watch the ones "
        "that look good financially but have weak readiness."
    )

    scales = company["qualitative_scales"]
    # Build a per-use-case readiness average alongside NPV.
    scatter_x = []   # readiness avg
    scatter_y = []   # NPV in $K
    scatter_names = []
    scatter_colors = []
    for r, src_uc in zip(analysis["use_cases"], company["use_cases"]):
        avg = sum(src_uc["qualitative"].values()) / len(src_uc["qualitative"])
        scatter_x.append(avg)
        scatter_y.append(r["metrics"]["npv"] / 1000)
        scatter_names.append(r["name"])
        scatter_colors.append(readiness_color(avg))

    fig_sc = go.Figure(go.Scatter(
        x=scatter_x, y=scatter_y, mode="markers+text",
        text=scatter_names, textposition="top center",
        marker=dict(size=14, color=scatter_colors,
                    line=dict(width=1, color="white")),
        hovertemplate="%{text}<br>Readiness: %{x:.1f}/5<br>NPV: $%{y:,.0f}K<extra></extra>",
    ))
    fig_sc.add_hline(y=0, line_color="#9CA3AF", line_width=1)
    fig_sc.add_vline(x=3, line_color="#9CA3AF", line_width=1, line_dash="dot")
    style_fig(fig_sc, "Use Cases: Readiness vs. Financial Outcome",
              "NPV ($ thousands)", x_title="Readiness score (1-5)")
    fig_sc.update_xaxes(range=[1, 5], showgrid=True, gridcolor=COLORS["grid"])
    st.plotly_chart(fig_sc, use_container_width=True)
    st.caption(
        "Top-right = healthy (good returns, well-absorbed). Top-left = financial "
        "upside but adoption risk. Bottom = financially underwater."
    )

    # --- Consolidated detail + download ---
    with st.expander("See consolidated month-by-month detail"):
        display_co = company_cf.rename(columns={
            "month": "Month", "costs": "Costs", "benefits": "Benefits (after %)",
            "readiness_impact": "Readiness $ impact", "net": "Net",
            "cumulative_net": "Cumulative net",
        }).drop(columns=["impact_positive", "impact_negative"], errors="ignore")
        co_order = ["Month", "Costs", "Benefits (after %)", "Readiness $ impact",
                    "Net", "Cumulative net"]
        display_co = display_co[[c for c in co_order if c in display_co.columns]]
        st.dataframe(display_co, width="stretch")
        csv_co = display_co.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download company cash flow as CSV", data=csv_co,
            file_name="company_cashflow.csv", mime="text/csv",
        )
