"""Deterministic financial planning. No AI, no invented numbers.

All money is integer cents. Growth is in basis points (100 bps = 1%).
Every figure returned is derived only from the inputs the user supplied."""

MAX_MONTHS = 60
MAX_ITEMS = 50
MAX_CENTS = 10**13  # R100 billion; rejects absurd input rather than overflowing


class FinanceInputError(ValueError):
    pass


def _int(value, name, lo=0, hi=MAX_CENTS):
    if isinstance(value, bool) or not isinstance(value, int):
        raise FinanceInputError(f"{name} must be a whole number.")
    if value < lo or value > hi:
        raise FinanceInputError(f"{name} must be between {lo} and {hi}.")
    return value


def _items(value, name):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_ITEMS:
        raise FinanceInputError(f"{name} must be a list of at most {MAX_ITEMS} items.")
    out = []
    for it in value:
        if not isinstance(it, dict) or not str(it.get("item", "")).strip():
            raise FinanceInputError(f"Each entry in {name} needs an item name.")
        out.append({"item": str(it["item"]).strip()[:200],
                    "amount_cents": _int(it.get("amount_cents"), f"{name} amount_cents")})
    return out


def _round_div(n: int, d: int) -> int:
    """Integer division rounding half up (inputs are non-negative)."""
    return (n + d // 2) // d


def project(inputs: dict) -> dict:
    if not isinstance(inputs, dict):
        raise FinanceInputError("Body must be an object.")
    funding = _int(inputs.get("funding_cents", 0), "funding_cents")
    existing = _int(inputs.get("existing_cash_cents", 0), "existing_cash_cents")
    startup = _items(inputs.get("startup_costs"), "startup_costs")
    costs = _items(inputs.get("monthly_costs"), "monthly_costs")
    revenue = _int(inputs.get("monthly_revenue_cents", 0), "monthly_revenue_cents")
    growth_bps = _int(inputs.get("revenue_growth_bps", 0), "revenue_growth_bps", lo=0, hi=10000)
    months = _int(inputs.get("months", 12), "months", lo=1, hi=MAX_MONTHS)

    scenarios = {"base": {"revenue_pct": 100, "cost_pct": 100}}
    for name, adj in (inputs.get("scenarios") or {}).items():
        if name == "base" or name not in ("low", "high"):
            raise FinanceInputError("Scenarios may only be 'low' and 'high'; 'base' is your inputs unchanged.")
        if not isinstance(adj, dict):
            raise FinanceInputError(f"Scenario {name} must be an object.")
        scenarios[name] = {"revenue_pct": _int(adj.get("revenue_pct"), f"{name}.revenue_pct", lo=0, hi=1000),
                           "cost_pct": _int(adj.get("cost_pct"), f"{name}.cost_pct", lo=0, hi=1000)}

    startup_total = sum(i["amount_cents"] for i in startup)
    base_cost = sum(i["amount_cents"] for i in costs)
    opening = existing + funding - startup_total

    results = {}
    for name, adj in scenarios.items():
        rev = _round_div(revenue * adj["revenue_pct"], 100)
        cost = _round_div(base_cost * adj["cost_pct"], 100)
        cash = opening
        rows, cash_out, positive_from = [], None, None
        for m in range(1, months + 1):
            if m > 1:
                rev = _round_div(rev * (10000 + growth_bps), 10000)
            net = rev - cost
            cash += net
            rows.append({"month": m, "revenue_cents": rev, "costs_cents": cost,
                         "net_cents": net, "closing_cash_cents": cash})
            if cash < 0 and cash_out is None:
                cash_out = m
            if net >= 0 and positive_from is None:
                positive_from = m
        results[name] = {
            "assumptions": adj,
            "months": rows,
            "first_month_cash_negative": cash_out,
            "first_month_net_non_negative": positive_from,
            "closing_cash_cents": cash,
        }

    warnings = []
    if opening < 0:
        warnings.append("Startup costs exceed existing cash plus funding, so cash is negative from the start.")
    if not costs:
        warnings.append("No monthly costs were entered. Results ignore operating expenses.")
    if revenue == 0:
        warnings.append("Revenue is zero. Results show costs only.")

    return {
        "calculation_period": f"monthly, {months} months",
        "inputs_echo": {"funding_cents": funding, "existing_cash_cents": existing,
                        "startup_costs": startup, "monthly_costs": costs,
                        "monthly_revenue_cents": revenue, "revenue_growth_bps": growth_bps},
        "formulas": {
            "opening_cash": "existing_cash + funding - sum(startup_costs)",
            "revenue[m]": "revenue[m-1] x (1 + growth); revenue[1] = monthly_revenue x scenario revenue %",
            "costs[m]": "sum(monthly_costs) x scenario cost %  (held flat each month)",
            "net[m]": "revenue[m] - costs[m]",
            "closing_cash[m]": "closing_cash[m-1] + net[m]; closing_cash[0] = opening_cash",
        },
        "opening_cash_cents": opening,
        "startup_total_cents": startup_total,
        "monthly_costs_total_cents": base_cost,
        "scenarios": results,
        "warnings": warnings,
        "disclaimers": [
            "Every figure is calculated from the assumptions you entered. None has been verified.",
            "Scenario percentages are yours to choose; they are not forecasts.",
            "This does not predict profitability, funding or success.",
        ],
    }


def check_consistency(inputs: dict) -> dict:
    """Compare figures a founder states in their deck against each other."""
    if not isinstance(inputs, dict):
        raise FinanceInputError("Body must be an object.")
    findings = []

    def add(code, severity, message, **details):
        findings.append({"code": code, "severity": severity, "message": message, "details": details})

    request = inputs.get("funding_request_cents")
    uof = _items(inputs.get("use_of_funds"), "use_of_funds")
    if request is not None:
        request = _int(request, "funding_request_cents")
    if request is not None and uof:
        total = sum(i["amount_cents"] for i in uof)
        if total != request:
            add("funding_vs_use_of_funds", "conflict",
                "The use-of-funds total does not match the funding request.",
                funding_request_cents=request, use_of_funds_total_cents=total, difference_cents=total - request)
    elif request is not None and not uof:
        add("use_of_funds_missing", "missing", "A funding request is stated but no use-of-funds breakdown was given.")

    monthly = inputs.get("monthly_revenue_cents")
    annual = inputs.get("annual_revenue_cents")
    if monthly is not None:
        monthly = _int(monthly, "monthly_revenue_cents")
    if annual is not None:
        annual = _int(annual, "annual_revenue_cents")
    if monthly is not None and annual is not None:
        if annual < monthly * 12:
            add("annual_below_monthly", "conflict",
                "Annual revenue is lower than twelve times monthly revenue. Revenue would have to fall during the year.",
                monthly_revenue_cents=monthly, annual_revenue_cents=annual, twelve_months_cents=monthly * 12)
        elif annual != monthly * 12:
            add("annual_differs_from_monthly", "check",
                "Annual revenue differs from twelve times monthly revenue. This is consistent only if you assume growth; state that assumption.",
                monthly_revenue_cents=monthly, annual_revenue_cents=annual, twelve_months_cents=monthly * 12)

    costs = _items(inputs.get("monthly_costs"), "monthly_costs")
    if (monthly or annual or request) and not costs:
        add("expenses_missing", "missing", "Revenue or funding is stated but no monthly expenses were given.")

    runway = inputs.get("claimed_runway_months")
    funding = inputs.get("funding_cents", request)
    if runway is not None and funding is not None and costs:
        runway = _int(runway, "claimed_runway_months", lo=0, hi=600)
        funding = _int(funding, "funding_cents")
        burn = sum(i["amount_cents"] for i in costs) - (monthly or 0)
        if burn > 0:
            computed = funding // burn  # whole months fully covered
            if runway > computed:
                add("runway_overstated", "conflict",
                    "The stated runway is longer than the funding covers at the stated monthly net spend.",
                    claimed_runway_months=runway, computed_runway_months=computed,
                    monthly_net_burn_cents=burn, funding_cents=funding)
        else:
            add("runway_not_applicable", "info",
                "Stated revenue covers stated costs, so there is no net monthly burn to compute a runway from.")

    return {
        "findings": findings,
        "conflicts": sum(1 for f in findings if f["severity"] == "conflict"),
        "note": "Checks compare only the figures you entered. A clean result does not mean the figures are accurate.",
    }
