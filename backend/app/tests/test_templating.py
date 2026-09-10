import pytest

from app.odata.builder import QuerySpec, build_filter, build_url
from app.templating import (
    QueryParam,
    TemplateError,
    find_placeholders,
    resolve_spec,
    substitute,
)


class FakeEndpoint:
    odata_version = "v4"
    base_url = "https://prip.example.org"
    entity_location = "/odata/v1/"
    default_entity_set = "Products"


TEXT = [QueryParam(name="text", type="string")]


class TestPlaceholderDiscovery:
    def test_finds_in_order_without_duplicates(self):
        assert find_placeholders("{{a}} and {{b}}", "{{a}} {{c}}") == ["a", "b", "c"]

    def test_tolerates_inner_whitespace(self):
        assert find_placeholders("{{ spaced }}") == ["spaced"]

    def test_none_is_safe(self):
        assert find_placeholders(None, "") == []


class TestSubstitution:
    def test_string_becomes_a_quoted_literal_in_an_expression(self):
        assert substitute("contains(Name,{{text}})", TEXT, {"text": "S1A"}) == (
            "contains(Name,'S1A')"
        )

    def test_string_stays_bare_where_the_builder_will_quote_it(self):
        assert substitute("{{text}}", TEXT, {"text": "S1A"}, quote_strings=False) == "S1A"

    def test_typed_params(self):
        params = [
            QueryParam(name="n", type="number"),
            QueryParam(name="d", type="datetime"),
            QueryParam(name="g", type="guid"),
            QueryParam(name="b", type="boolean"),
        ]
        values = {
            "n": 5,
            "d": "2024-01-01T00:00:00Z",
            "g": "0f3a4b5c-1234-4abc-8def-1234567890ab",
            "b": "true",
        }
        assert substitute("{{n}}|{{d}}|{{g}}|{{b}}", params, values) == (
            "5|2024-01-01T00:00:00.000Z|0f3a4b5c-1234-4abc-8def-1234567890ab|true"
        )

    def test_default_is_used_when_no_value_given(self):
        params = [QueryParam(name="n", type="number", default=20)]
        assert substitute("$top={{n}}", params, {}) == "$top=20"

    def test_explicit_value_beats_the_default(self):
        params = [QueryParam(name="n", type="number", default=20)]
        assert substitute("$top={{n}}", params, {"n": 5}) == "$top=5"

    def test_missing_required_param_is_reported(self):
        with pytest.raises(TemplateError) as excinfo:
            substitute("contains(Name,{{text}}) and {{other}}",
                       TEXT + [QueryParam(name="other")], {})
        assert excinfo.value.missing == ["other", "text"]

    def test_optional_param_renders_null(self):
        params = [QueryParam(name="maybe", required=False)]
        assert substitute("Foo eq {{maybe}}", params, {}) == "Foo eq null"

    def test_bad_typed_value_is_reported(self):
        params = [QueryParam(name="d", type="datetime")]
        with pytest.raises(TemplateError, match="Parameter 'd'"):
            substitute("{{d}}", params, {"d": "not a date"})

    def test_injection_through_a_param_cannot_escape_the_literal(self):
        hostile = "x') or (1 eq 1"
        rendered = substitute("contains(Name,{{text}})", TEXT, {"text": hostile})
        assert rendered == "contains(Name,'x'') or (1 eq 1')"


class TestResolveSpec:
    def test_clause_value_is_left_for_the_builder_to_quote(self):
        spec_dict = {
            "clauses": [
                {"field": "Name", "op": "contains", "value": "{{text}}",
                 "value_type": "string"}
            ]
        }
        resolved = resolve_spec(spec_dict, TEXT, {"text": "S1A"})
        assert build_filter(QuerySpec(**resolved)) == "contains(Name,'S1A')"

    def test_no_double_quoting_of_a_clause_value(self):
        spec_dict = {
            "clauses": [{"field": "Name", "op": "eq", "value": "{{text}}",
                         "value_type": "string"}]
        }
        resolved = resolve_spec(spec_dict, TEXT, {"text": "abc"})
        assert build_filter(QuerySpec(**resolved)) == "Name eq 'abc'"

    def test_raw_filter_gets_a_full_literal(self):
        params = [QueryParam(name="start", type="datetime"),
                  QueryParam(name="end", type="datetime")]
        spec_dict = {
            "raw_filter": "PublicationDate ge {{start}} and PublicationDate le {{end}}"
        }
        resolved = resolve_spec(spec_dict, params,
                                {"start": "2024-01-01", "end": "2024-01-31"})
        assert resolved["raw_filter"] == (
            "PublicationDate ge 2024-01-01T00:00:00.000Z and "
            "PublicationDate le 2024-01-31T00:00:00.000Z"
        )

    def test_entity_id_is_not_pre_quoted(self):
        params = [QueryParam(name="id", type="string")]
        resolved = resolve_spec({"entity_id": "{{id}}"}, params, {"id": "ABC_1"})
        url = build_url(FakeEndpoint(), QuerySpec(**resolved))
        assert url.endswith("Products('ABC_1')")

    def test_guid_entity_id_stays_bare(self):
        params = [QueryParam(name="id", type="string")]
        guid = "0f3a4b5c-1234-4abc-8def-1234567890ab"
        resolved = resolve_spec({"entity_id": "{{id}}"}, params, {"id": guid})
        assert build_url(FakeEndpoint(), QuerySpec(**resolved)).endswith(f"Products({guid})")

    def test_top_placeholder_coerces_to_int(self):
        params = [QueryParam(name="n", type="number", default=20)]
        resolved = resolve_spec({"top": "{{n}}"}, params, {})
        assert QuerySpec(**resolved).top == 20

    def test_untouched_spec_survives(self):
        spec_dict = {"entity_set": "Products", "top": 10, "count": True}
        assert resolve_spec(spec_dict, [], {}) == spec_dict
