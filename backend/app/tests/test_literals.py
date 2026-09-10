import pytest

from app.odata.literals import (
    LiteralError,
    escape_string,
    format_boolean,
    format_datetime,
    format_guid,
    format_key_predicate,
    format_literal,
    format_number,
    quote_string,
    validate_field,
)


class TestStringEscaping:
    def test_single_quote_is_doubled(self):
        assert escape_string("O'Brien") == "O''Brien"
        assert quote_string("O'Brien") == "'O''Brien'"

    def test_quote_cannot_break_out_of_a_filter(self):
        # The classic injection attempt: close the literal and append a clause.
        hostile = "x' or Name ne '"
        assert quote_string(hostile) == "'x'' or Name ne '''"

    def test_plain_string_untouched(self):
        assert quote_string("S1A_IW_GRDH") == "'S1A_IW_GRDH'"

    def test_empty_string(self):
        assert quote_string("") == "''"


class TestFieldValidation:
    @pytest.mark.parametrize("field", ["Name", "Id", "Collection/Name", "a/b/c", "_x1"])
    def test_valid_fields(self, field):
        assert validate_field(field) == field

    @pytest.mark.parametrize(
        "field", ["Name eq 'x'", "Name;drop", "", "1Name", "Name'", "Name Name", "a//b"]
    )
    def test_invalid_fields_rejected(self, field):
        with pytest.raises(LiteralError):
            validate_field(field)


class TestGuid:
    def test_v4_is_bare(self):
        value = "0f3a4b5c-1234-4abc-8def-1234567890ab"
        assert format_guid(value) == value

    def test_v3_is_wrapped(self):
        value = "0f3a4b5c-1234-4abc-8def-1234567890ab"
        assert format_guid(value, "v3") == f"guid'{value}'"

    def test_invalid_guid_rejected(self):
        with pytest.raises(LiteralError):
            format_guid("not-a-guid")


class TestDatetime:
    def test_v4_zulu(self):
        assert format_datetime("2024-01-31T12:30:00Z") == "2024-01-31T12:30:00.000Z"

    def test_v3_drops_the_z_and_wraps(self):
        assert format_datetime("2024-01-31T12:30:00Z", "v3") == (
            "datetime'2024-01-31T12:30:00.000'"
        )

    def test_offset_is_normalised_to_utc(self):
        assert format_datetime("2024-01-31T13:30:00+01:00") == "2024-01-31T12:30:00.000Z"

    def test_date_only(self):
        assert format_datetime("2024-01-31") == "2024-01-31T00:00:00.000Z"

    def test_garbage_rejected(self):
        with pytest.raises(LiteralError):
            format_datetime("last tuesday")


class TestScalars:
    def test_numbers(self):
        assert format_number(42) == "42"
        assert format_number("3.5") == "3.5"

    def test_non_number_rejected(self):
        with pytest.raises(LiteralError):
            format_number("12; drop")

    def test_bool_is_not_a_number(self):
        with pytest.raises(LiteralError):
            format_number(True)

    def test_booleans(self):
        assert format_boolean(True) == "true"
        assert format_boolean("false") == "false"
        with pytest.raises(LiteralError):
            format_boolean("maybe")

    def test_null(self):
        assert format_literal(None, "string") == "null"
        assert format_literal("anything", "null") == "null"

    def test_unknown_type_rejected(self):
        with pytest.raises(LiteralError):
            format_literal("x", "sqlish")


class TestKeyPredicate:
    def test_guid_detected(self):
        value = "0f3a4b5c-1234-4abc-8def-1234567890ab"
        assert format_key_predicate(value) == value

    def test_integer_detected(self):
        assert format_key_predicate("42") == "42"

    def test_anything_else_is_quoted(self):
        assert format_key_predicate("S1A_PRODUCT") == "'S1A_PRODUCT'"

    def test_quote_in_key_is_escaped(self):
        assert format_key_predicate("a'b") == "'a''b'"

    def test_explicit_type_wins(self):
        assert format_key_predicate("42", "string") == "'42'"
