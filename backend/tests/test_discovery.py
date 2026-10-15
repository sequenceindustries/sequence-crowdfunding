from conftest import complete_campaign_payload, make_profile


def publish_one(founder, admin, name, title, description, **extra):
    p = make_profile(founder, name)
    payload = {**complete_campaign_payload(p["id"], extra.pop("goal", 1_000_000)), "title": title,
               "description": description, **extra}
    cid = founder.post("/api/campaigns", payload).json["campaign"]["id"]
    assert founder.post(f"/api/campaigns/{cid}/submit").status_code == 200
    assert admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve", "reason": "ok"}).status_code == 200
    assert founder.post(f"/api/campaigns/{cid}/publish").status_code == 200
    return cid


FILL = " We serve local customers every single day with care and attention to detail." * 3


def seed(founder, admin):
    a = publish_one(founder, admin, "Bright Spark", "Solar phone chargers", "Kiosks for taxi ranks." + FILL,
                    category="Energy", location="Soweto", goal=500_000)
    b = publish_one(founder, admin, "Green Bakes", "Community bakery", "We use solar ovens to bake bread." + FILL,
                    category="Food", location="Durban", goal=900_000)
    c = publish_one(founder, admin, "Cape Tutors", "Maths tutoring", "After school lessons." + FILL,
                    category="Education", location="Cape Town", goal=200_000)
    return a, b, c


def titles(client, qs):
    return [x["title"] for x in client.get("/api/public/campaigns?" + qs).json["campaigns"]]


def test_all_terms_must_match_and_stopwords_ignored(founder, admin, client):
    seed(founder, admin)
    assert titles(client, "q=solar") == ["Solar phone chargers", "Community bakery"]
    assert titles(client, "q=solar+soweto") == ["Solar phone chargers"]          # AND narrows
    assert titles(client, "q=solar+in+the+soweto") == ["Solar phone chargers"]   # stopwords dropped
    assert titles(client, "q=solar+cape") == []
    assert client.get("/api/public/campaigns?q=the+of").json["total"] == 3       # only stopwords = no filter


def test_relevance_ranks_title_above_description(founder, admin, client):
    seed(founder, admin)
    assert titles(client, "q=solar")[0] == "Solar phone chargers"  # title hit beats description hit
    assert titles(client, "q=solar&sort=title") == ["Community bakery", "Solar phone chargers"]


def test_matches_business_name_category_and_location(founder, admin, client):
    seed(founder, admin)
    assert titles(client, "q=cape+tutors") == ["Maths tutoring"]       # business name
    assert titles(client, "q=education") == ["Maths tutoring"]         # category
    assert titles(client, "q=durban") == ["Community bakery"]          # location


def test_match_explanation_lists_only_fields_that_contain_terms(founder, admin, client):
    seed(founder, admin)
    r = client.get("/api/public/campaigns?q=solar+soweto").json["campaigns"][0]
    assert r["match"]["terms"] == ["solar", "soweto"]
    assert set(r["match"]["fields"]) == {"title", "location"}
    assert "match" not in client.get("/api/public/campaigns").json["campaigns"][0]


def test_wildcards_and_odd_input_are_inert(founder, admin, client):
    seed(founder, admin)
    for q in ("%25", "_", "%25%25", "'%3B+DROP+TABLE+campaigns%3B--", "a" * 300):
        assert client.get(f"/api/public/campaigns?q={q}").status_code == 200
    # punctuation is not a search term, and '%' / '_' are never passed to LIKE as wildcards
    assert client.get("/api/public/campaigns?q=%25").json["total"] == 3
    assert client.get("/api/public/campaigns?q=s_lar").json["total"] == 0


def test_goal_sorts_and_invalid_sort(founder, admin, client):
    seed(founder, admin)
    assert titles(client, "sort=goal_asc") == ["Maths tutoring", "Solar phone chargers", "Community bakery"]
    assert titles(client, "sort=goal_desc")[0] == "Community bakery"
    assert client.get("/api/public/campaigns?sort=banana").status_code == 400


def test_categories_count_only_published(founder, admin, client):
    seed(founder, admin)
    p = make_profile(founder, "Hidden")
    founder.post("/api/campaigns", {**complete_campaign_payload(p["id"]), "category": "Secret"})  # draft
    cats = {c["category"]: c["count"] for c in client.get("/api/public/categories").json["categories"]}
    assert cats == {"Energy": 1, "Food": 1, "Education": 1}


def test_unpublished_and_suspended_never_surface_in_search(founder, admin, client):
    a, _, _ = seed(founder, admin)
    admin.post(f"/api/admin/campaigns/{a}/decision", {"action": "suspend", "reason": "complaint"})
    assert titles(client, "q=solar") == ["Community bakery"]
    assert "Energy" not in {c["category"] for c in client.get("/api/public/categories").json["categories"]}
