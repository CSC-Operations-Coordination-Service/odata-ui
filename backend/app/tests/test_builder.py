import pytest

from app.odata.builder import (
    BuildError,
    Clause,
    OrderBy,
    QuerySpec,
    build_filter,
    build_metadata_url,
    build_probe_url,
    build_url,
)


class FakeEndpoint:
    """Stand-in for the ORM row; build_url only reads these four attributes."""

    def __init__(self, version="v4", base_url="https://prip.example.org",
                 entity_location="/odata/v1/", default_entity_set="Products"):
        self.odata_version = version
        self.base_url = base_url
        self.entity_location = entity_location
        self.default_entity_set = default_entity_set


V4 = FakeEndpoint()
V3 = FakeEndpoint(version="v3")


class TestServiceRoot:
    def test_slashes_are_normalised(self):
        endpoint = FakeEndpoint(base_url="https://x.org/", entity_location="odata/v1")
        url = build_url(endpoint, QuerySpec(entity_set="Products", top=1))
        assert url.startswith("https://x.org/odata/v1/Products?")

    def test_missing_base_url_rejected(self):
        with pytest.raises(BuildError):
            build_url(FakeEndpoint(base_url=""), QuerySpec(entity_set="Products"))

    def test_missing_entity_set_rejected(self):
        with pytest.raises(BuildError):
            build_url(FakeEndpoint(default_entity_set=""), QuerySpec())

    def test_falls_back_to_default_entity_set(self):
        assert build_url(V4, QuerySpec()) == "https://prip.example.org/odata/v1/Products"


class TestByIdLookup:
    def test_guid_key_is_bare_in_v4(self):
        spec = QuerySpec(entity_id="0f3a4b5c-1234-4abc-8def-1234567890ab")
        assert build_url(V4, spec) == (
            "https://prip.example.org/odata/v1/Products"
            "(0f3a4b5c-1234-4abc-8def-1234567890ab)"
        )

    def test_guid_key_is_wrapped_in_v3(self):
        spec = QuerySpec(entity_id="0f3a4b5c-1234-4abc-8def-1234567890ab")
        assert build_url(V3, spec).endswith(
            "Products(guid'0f3a4b5c-1234-4abc-8def-1234567890ab')"
        )

    def test_string_key_is_quoted(self):
        assert build_url(V4, QuerySpec(entity_id="ABC_123")).endswith("Products('ABC_123')")

    def test_filter_is_ignored_next_to_a_key(self):
        spec = QuerySpec(entity_id="42", clauses=[Clause(field="Name", value="x")])
        assert build_url(V4, spec).endswith("Products(42)")


class TestFilters:
    def test_contains_v4(self):
        spec = QuerySpec(clauses=[Clause(field="Name", op="contains", value="S1A_IW")])
        assert build_filter(spec) == "contains(Name,'S1A_IW')"

    def test_contains_v3_uses_substringof_with_swapped_args(self):
        spec = QuerySpec(clauses=[Clause(field="Name", op="contains", value="S1A_IW")])
        assert build_filter(spec, "v3") == "substringof('S1A_IW',Name)"

    def test_startswith_and_endswith(self):
        assert build_filter(
            QuerySpec(clauses=[Clause(field="Name", op="startswith", value="S1A")])
        ) == "startswith(Name,'S1A')"
        assert build_filter(
            QuerySpec(clauses=[Clause(field="Name", op="endswith", value=".SAFE")])
        ) == "endswith(Name,'.SAFE')"

    def test_comparison_with_datetime(self):
        spec = QuerySpec(
            clauses=[
                Clause(field="PublicationDate", op="ge",
                       value="2024-01-01T00:00:00Z", value_type="datetime")
            ]
        )
        assert build_filter(spec) == "PublicationDate ge 2024-01-01T00:00:00.000Z"

    def test_multiple_clauses_joined_with_and(self):
        spec = QuerySpec(
            clauses=[
                Clause(field="Name", op="contains", value="S1A"),
                Clause(field="ContentLength", op="gt", value=1000, value_type="number"),
            ]
        )
        assert build_filter(spec) == "contains(Name,'S1A') and ContentLength gt 1000"

    def test_clause_logic_or(self):
        spec = QuerySpec(
            clause_logic="or",
            clauses=[
                Clause(field="Name", op="eq", value="a"),
                Clause(field="Name", op="eq", value="b"),
            ],
        )
        assert build_filter(spec) == "Name eq 'a' or Name eq 'b'"

    def test_in_operator_v4(self):
        spec = QuerySpec(clauses=[Clause(field="Collection/Name", op="in", value="S1,S2")])
        assert build_filter(spec) == "Collection/Name in ('S1','S2')"

    def test_in_operator_v3_expands_to_or(self):
        spec = QuerySpec(clauses=[Clause(field="Platform", op="in", value="S1,S2")])
        assert build_filter(spec, "v3") == "(Platform eq 'S1' or Platform eq 'S2')"

    def test_null_checks(self):
        assert build_filter(
            QuerySpec(clauses=[Clause(field="Footprint", op="isnull")])
        ) == "Footprint eq null"
        assert build_filter(
            QuerySpec(clauses=[Clause(field="Footprint", op="isnotnull")])
        ) == "Footprint ne null"

    def test_raw_filter_overrides_clauses(self):
        spec = QuerySpec(
            raw_filter="startswith(Name,'X') and Foo eq 1",
            clauses=[Clause(field="Name", value="ignored")],
        )
        assert build_filter(spec) == "startswith(Name,'X') and Foo eq 1"

    def test_no_clauses_gives_no_filter(self):
        assert build_filter(QuerySpec()) == ""

    def test_bad_operator_rejected(self):
        with pytest.raises(BuildError):
            build_filter(QuerySpec(clauses=[Clause(field="Name", op="LIKE", value="x")]))

    def test_bad_field_rejected(self):
        with pytest.raises(BuildError):
            build_filter(QuerySpec(clauses=[Clause(field="Name eq 1 or 1", value="x")]))

    def test_empty_in_rejected(self):
        with pytest.raises(BuildError):
            build_filter(QuerySpec(clauses=[Clause(field="Name", op="in", value="")]))

    def test_injection_through_a_value_stays_inside_the_literal(self):
        spec = QuerySpec(
            clauses=[Clause(field="Name", op="contains", value="x') or (1 eq 1")]
        )
        assert build_filter(spec) == "contains(Name,'x'') or (1 eq 1')"


class TestSystemOptions:
    def test_select_expand_orderby(self):
        spec = QuerySpec(
            select=["Id", "Name"],
            expand=["Attributes"],
            orderby=[OrderBy(field="PublicationDate", direction="desc")],
        )
        url = build_url(V4, spec)
        assert "$select=Id,Name" in url
        assert "$expand=Attributes" in url
        assert "$orderby=PublicationDate%20desc" in url

    def test_top_and_skip(self):
        url = build_url(V4, QuerySpec(top=50, skip=100))
        assert "$top=50" in url and "$skip=100" in url

    def test_top_is_capped(self):
        url = build_url(V4, QuerySpec(top=100000), max_page_size=5000)
        assert "$top=5000" in url

    def test_negative_top_rejected(self):
        with pytest.raises(BuildError):
            build_url(V4, QuerySpec(top=-1))

    def test_count_v4(self):
        assert "$count=true" in build_url(V4, QuerySpec(count=True))

    def test_count_v3_uses_inlinecount(self):
        assert "$inlinecount=allpages" in build_url(V3, QuerySpec(count=True))

    def test_custom_suffix_appended(self):
        url = build_url(V4, QuerySpec(top=1, custom_suffix="&$deltatoken=abc"))
        assert url.endswith("$top=1&$deltatoken=abc")


class TestEncoding:
    def test_spaces_are_percent_encoded_quotes_are_not(self):
        spec = QuerySpec(clauses=[Clause(field="Name", op="contains", value="a b")])
        url = build_url(V4, spec)
        assert "$filter=contains(Name,'a%20b')" in url
        assert " " not in url

    def test_ampersand_in_a_value_is_encoded(self):
        spec = QuerySpec(clauses=[Clause(field="Name", op="eq", value="a&b=c")])
        url = build_url(V4, spec)
        assert "%26" in url and "a&b=c" not in url

    def test_plus_in_a_value_is_encoded_not_turned_into_space(self):
        spec = QuerySpec(clauses=[Clause(field="Name", op="eq", value="a+b")])
        assert "%2B" in build_url(V4, spec)


class TestRawQuery:
    def test_raw_query_bypasses_the_builder(self):
        spec = QuerySpec(raw_query="?$filter=Name eq 'x'&$top=3")
        assert build_url(V4, spec) == (
            "https://prip.example.org/odata/v1/Products?$filter=Name eq 'x'&$top=3"
        )

    def test_raw_query_still_honours_the_key_predicate(self):
        spec = QuerySpec(entity_id="42", raw_query="$expand=Attributes")
        assert build_url(V4, spec).endswith("Products(42)?$expand=Attributes")


class TestHelperUrls:
    def test_probe_url_asks_for_one_row(self):
        assert build_probe_url(V4) == "https://prip.example.org/odata/v1/Products?$top=1"

    def test_metadata_url(self):
        assert build_metadata_url(V4) == "https://prip.example.org/odata/v1/$metadata"
