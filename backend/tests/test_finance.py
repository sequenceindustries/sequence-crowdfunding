import pytest

from app.services.finance import FinanceInputError, check_consistency, project


def rows(result, scenario="base"):
    return result["scenarios"][scenario]["months"]


def test_flat_projection_matches_hand_calculation():
    # opening = 0 + 1,000,000 - 400,000 = 600,000; net = 150,000 - 100,000 = +50,000/month
    r = project({"funding_cents": 1_000_000, "startup_costs": [{"item": "Kiosks", "amount_cents": 400_000}],
                 "monthly_costs": [{"item": "Rent", "amount_cents": 100_000}],
                 "monthly_revenue_cents": 150_000, "months": 3})
    assert r["opening_cash_cents"] == 600_000
    assert [m["closing_cash_cents"] for m in rows(r)] == [650_000, 700_000, 750_000]
    assert r["scenarios"]["base"]["first_month_net_non_negative"] == 1
    assert r["scenarios"]["base"]["first_month_cash_negative"] is None


def test_growth_compounds_monthly_and_finds_break_even():
    # revenue 100,000 -> 110,000 -> 121,000 against costs 120,000
    r = project({"funding_cents": 100_000, "monthly_costs": [{"item": "Ops", "amount_cents": 120_000}],
                 "monthly_revenue_cents": 100_000, "revenue_growth_bps": 1000, "months": 3})
    assert [m["revenue_cents"] for m in rows(r)] == [100_000, 110_000, 121_000]
    assert [m["net_cents"] for m in rows(r)] == [-20_000, -10_000, 1_000]
    assert [m["closing_cash_cents"] for m in rows(r)] == [80_000, 70_000, 71_000]
    assert r["scenarios"]["base"]["first_month_net_non_negative"] == 3


def test_cash_out_month_detected():
    r = project({"funding_cents": 100_000, "monthly_costs": [{"item": "Ops", "amount_cents": 60_000}], "months": 4})
    assert [m["closing_cash_cents"] for m in rows(r)] == [40_000, -20_000, -80_000, -140_000]
    assert r["scenarios"]["base"]["first_month_cash_negative"] == 2


def test_low_and_high_scenarios_use_only_user_percentages():
    r = project({"funding_cents": 0, "existing_cash_cents": 500_000,
                 "monthly_costs": [{"item": "Ops", "amount_cents": 100_000}],
                 "monthly_revenue_cents": 150_000, "months": 1,
                 "scenarios": {"low": {"revenue_pct": 50, "cost_pct": 120},
                               "high": {"revenue_pct": 120, "cost_pct": 100}}})
    assert rows(r, "base")[0]["net_cents"] == 50_000
    assert rows(r, "low")[0]["revenue_cents"] == 75_000 and rows(r, "low")[0]["costs_cents"] == 120_000
    assert rows(r, "low")[0]["net_cents"] == -45_000
    assert rows(r, "high")[0]["net_cents"] == 80_000
    assert set(r["scenarios"]) == {"base", "low", "high"}


def test_no_scenarios_unless_requested():
    assert set(project({"funding_cents": 1})["scenarios"]) == {"base"}


def test_rounding_is_half_up_and_deterministic():
    r = project({"monthly_revenue_cents": 1, "revenue_growth_bps": 5000, "months": 3})
    assert [m["revenue_cents"] for m in rows(r)] == [1, 2, 3]  # 1 -> 1.5->2 -> 3
    assert project({"monthly_revenue_cents": 1, "revenue_growth_bps": 5000, "months": 3}) == r


def test_shows_formulas_inputs_and_period_and_warnings():
    r = project({"funding_cents": 100_000, "months": 6})
    assert r["calculation_period"] == "monthly, 6 months"
    assert "closing_cash[m]" in r["formulas"] and r["inputs_echo"]["funding_cents"] == 100_000
    assert any("No monthly costs" in w for w in r["warnings"])
    assert any("Revenue is zero" in w for w in r["warnings"])
    assert any("None has been verified" in d for d in r["disclaimers"])


def test_startup_costs_exceeding_cash_warns():
    r = project({"funding_cents": 100, "startup_costs": [{"item": "Big", "amount_cents": 500}], "months": 1})
    assert r["opening_cash_cents"] == -400
    assert any("negative from the start" in w for w in r["warnings"])


@pytest.mark.parametrize("bad", [
    {"funding_cents": 1.5}, {"funding_cents": -1}, {"funding_cents": True}, {"funding_cents": "100"},
    {"months": 0}, {"months": 61}, {"revenue_growth_bps": 10001},
    {"startup_costs": [{"item": "", "amount_cents": 1}]}, {"startup_costs": [{"item": "x", "amount_cents": -5}]},
    {"startup_costs": "nope"}, {"monthly_costs": [1, 2]},
    {"scenarios": {"base": {"revenue_pct": 1, "cost_pct": 1}}}, {"scenarios": {"extreme": {}}},
    {"scenarios": {"low": {"revenue_pct": 5000, "cost_pct": 100}}},
    {"funding_cents": 10**15},
])
def test_projection_rejects_bad_input(bad):
    with pytest.raises(FinanceInputError):
        project(bad)


def test_projection_rejects_non_object():
    with pytest.raises(FinanceInputError):
        project([1, 2])


def codes(r):
    return {f["code"] for f in r["findings"]}


def test_funding_request_must_match_use_of_funds():
    r = check_consistency({"funding_request_cents": 1_000_000,
                           "use_of_funds": [{"item": "A", "amount_cents": 600_000}, {"item": "B", "amount_cents": 300_000}]})
    f = [x for x in r["findings"] if x["code"] == "funding_vs_use_of_funds"][0]
    assert f["severity"] == "conflict" and f["details"]["difference_cents"] == -100_000
    ok = check_consistency({"funding_request_cents": 900_000,
                            "use_of_funds": [{"item": "A", "amount_cents": 600_000}, {"item": "B", "amount_cents": 300_000}]})
    assert "funding_vs_use_of_funds" not in codes(ok)


def test_request_without_breakdown_flagged_missing():
    assert "use_of_funds_missing" in codes(check_consistency({"funding_request_cents": 5}))


def test_annual_vs_monthly_revenue():
    low = check_consistency({"monthly_revenue_cents": 100_000, "annual_revenue_cents": 900_000})
    assert [f for f in low["findings"] if f["code"] == "annual_below_monthly"][0]["severity"] == "conflict"
    higher = check_consistency({"monthly_revenue_cents": 100_000, "annual_revenue_cents": 1_500_000})
    assert [f for f in higher["findings"] if f["code"] == "annual_differs_from_monthly"][0]["severity"] == "check"
    equal = check_consistency({"monthly_revenue_cents": 100_000, "annual_revenue_cents": 1_200_000,
                               "monthly_costs": [{"item": "x", "amount_cents": 1}]})
    assert not ({"annual_below_monthly", "annual_differs_from_monthly"} & codes(equal))


def test_missing_expenses_flagged():
    assert "expenses_missing" in codes(check_consistency({"monthly_revenue_cents": 100}))
    assert "expenses_missing" not in codes(
        check_consistency({"monthly_revenue_cents": 100, "monthly_costs": [{"item": "x", "amount_cents": 1}]}))


def test_runway_overstated_detected_and_boundary():
    base = {"funding_cents": 600_000, "monthly_revenue_cents": 20_000,
            "monthly_costs": [{"item": "Ops", "amount_cents": 100_000}]}  # burn 80,000 -> 7 whole months
    over = check_consistency({**base, "claimed_runway_months": 12})
    f = [x for x in over["findings"] if x["code"] == "runway_overstated"][0]
    assert f["details"]["computed_runway_months"] == 7 and over["conflicts"] == 1
    assert "runway_overstated" not in codes(check_consistency({**base, "claimed_runway_months": 7}))
    assert "runway_overstated" in codes(check_consistency({**base, "claimed_runway_months": 8}))


def test_runway_not_applicable_when_revenue_covers_costs():
    r = check_consistency({"funding_cents": 100, "claimed_runway_months": 12, "monthly_revenue_cents": 200,
                           "monthly_costs": [{"item": "Ops", "amount_cents": 100}]})
    assert "runway_not_applicable" in codes(r)


def test_clean_input_has_no_findings_and_a_caveat():
    r = check_consistency({})
    assert r["findings"] == [] and "does not mean" in r["note"]


def test_consistency_rejects_bad_input():
    with pytest.raises(FinanceInputError):
        check_consistency({"funding_request_cents": -1})


def test_api_access_control_and_statelessness(client, founder, make_client):
    body = {"funding_cents": 100_000, "monthly_costs": [{"item": "Ops", "amount_cents": 10_000}], "months": 2}
    r = founder.post("/api/finance/projection", body)
    assert r.status_code == 200 and r.json["scenarios"]["base"]["closing_cash_cents"] == 80_000
    assert founder.post("/api/finance/consistency", {"funding_request_cents": 5}).status_code == 200
    assert founder.post("/api/finance/projection", {"funding_cents": -1}).status_code == 400
    assert founder.post("/api/finance/projection", None).status_code == 400
    assert client.post("/api/finance/projection", body).status_code == 401
    supporter = make_client()
    supporter.register("s@example.com", role="supporter")
    assert supporter.post("/api/finance/projection", body).status_code == 403
