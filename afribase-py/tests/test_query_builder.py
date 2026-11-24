from urllib.parse import parse_qsl, urlsplit

from afribase import create_client, db, eq, explain, gte, lte, order, range as qrange, select, text_search

URL = "https://proj.example.com"


def q(req):
    return parse_qsl(urlsplit(str(req.url)).query, keep_blank_values=True)


def test_repeated_filters_and_orders_are_kept(server):
    server.on("GET", "/rest/v1/people", json_body=[])
    c = create_client(URL, "anon")
    c.from_("people").select("id").gte("age", 18).lte("age", 65).order("age").order("name", desc=True).execute()
    assert q(server.last) == [("select", "id"), ("age", "gte.18"), ("age", "lte.65"),
                              ("order", "age.asc.nullslast"), ("order", "name.desc.nullslast")]


def test_values_are_encoded_and_formatted(server):
    server.on("GET", "/rest/v1/t", json_body=[])
    c = create_client(URL, "anon")
    c.from_("t").select().eq("at", "2026-01-01T00:00:00+01:00").eq("note", "a&b #c").is_("deleted", None) \
        .eq("ok", True).in_("tag", ["x y", 1, None]).execute()
    assert q(server.last)[1:] == [("at", "eq.2026-01-01T00:00:00+01:00"), ("note", "eq.a&b #c"),
                                  ("deleted", "is.null"), ("ok", "eq.true"), ("tag", 'in.("x y",1,null)')]
    assert "%2B01" in str(server.last.url)


def test_text_search_default_is_fts_and_range_headers(server):
    server.on("GET", "/rest/v1/t", json_body=[])
    c = create_client(URL, "anon")
    c.from_("t").select().text_search("body", "cat").text_search("body", "dog", type="websearch", config="english") \
        .range(10, 19).execute()
    assert ("body", "fts.cat") in q(server.last) and ("body", "wfts(english).dog") in q(server.last)
    assert ("offset", "10") in q(server.last) and ("limit", "10") in q(server.last)
    assert server.last.headers["range"] == "10-19" and server.last.headers["range-unit"] == "items"


def test_count_only_when_asked(server):
    server.on("GET", "/rest/v1/t", json_body=[{"id": 1}], headers={"content-range": "0-0/42"})
    c = create_client(URL, "anon")
    assert c.from_("t").select("*").execute().count is None
    r = c.from_("t").select("*", count="exact").execute()
    assert r.count == 42 and server.last.headers["prefer"] == "count=exact"


def test_maybe_single_no_rows_is_not_an_error(server):
    server.on("GET", "/rest/v1/t", status=406, json_body={"code": "PGRST116", "message": "JSON object requested, multiple (or no) rows returned", "details": None, "hint": None})
    c = create_client(URL, "anon")
    r = c.from_("t").select().eq("id", 9).maybe_single().execute()
    assert r.data is None and r.error is None and r.status == 200
    r = c.from_("t").select().eq("id", 9).single().execute()
    assert r.error.code == "PGRST116" and r.error.details == "" and r.error.hint == ""


def test_error_defaults_and_non_object_bodies(server):
    c = create_client(URL, "anon")
    server.on("GET", "/rest/v1/a", status=500, text="")
    e = c.from_("a").select().execute().error
    assert e.message == "Request failed with status 500" and e.code == "500"
    server.on("GET", "/rest/v1/b", status=400, json_body=["weird"])
    assert c.from_("b").select().execute().error.code == "400"
    server.on("POST", "/rpc/f", status=503, text="")
    assert c.rpc("f").execute().error.message == "RPC failed with status 503"


def test_geojson_csv_explain_return_text(server):
    c = create_client(URL, "anon")
    server.on("GET", "/rest/v1/geo", text='{"type":"FeatureCollection"}', headers={"content-type": "application/geo+json"})
    assert c.from_("geo").select().geojson().execute().data == '{"type":"FeatureCollection"}'
    assert server.last.headers["accept"] == "application/geo+json"
    server.on("GET", "/rest/v1/p", text="Seq Scan", headers={"content-type": "application/vnd.pgrst.plan+text"})
    assert c.from_("p").select().explain(analyze=True, format="text").execute().data == "Seq Scan"
    assert server.last.headers["accept"] == "application/vnd.pgrst.plan+analyze+text"


def test_rpc_chain_and_get(server):
    server.on("POST", "/rpc/search", json_body=[{"id": 1}], headers={"content-range": "0-0/3"})
    c = create_client(URL, "anon")
    r = c.rpc("search", {"q": "a b"}, count="exact").select("id").eq("kind", "x").order("id", ascending=False).limit(5).execute()
    assert r.count == 3 and r.data == [{"id": 1}]
    assert q(server.last) == [("select", "id"), ("kind", "eq.x"), ("order", "id.desc"), ("limit", "5")]
    assert server.last_json() == {"q": "a b"}
    server.on("GET", "/rpc/search", json_body=[])
    c.rpc("search", {"q": "a&b", "flag": True}, get=True).execute()
    assert q(server.last) == [("q", "a&b"), ("flag", "true")]
    server.on("POST", "/rpc/plain", json_body=1)
    c.rpc("plain").execute()
    assert server.last.headers["prefer"] == "return=representation"


def test_modular_ops(server):
    server.on("GET", "/rest/v1/people", json_body=[])
    c = create_client(URL, "anon")
    db(c.from_("people"), select("id", count="exact"), gte("age", 18), lte("age", 65),
       text_search("bio", "x"), order("age", ascending=False, nulls_first=True), qrange(0, 9))
    assert ("order", "age.desc.nullsfirst") in q(server.last) and ("age", "lte.65") in q(server.last)
    db(c.from_("people"), select(), eq("id", 1), explain(format="json"))
    assert server.last.headers["accept"] == "application/vnd.pgrst.plan+json"
