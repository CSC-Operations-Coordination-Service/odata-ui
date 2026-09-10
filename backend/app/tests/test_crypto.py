import pytest

from app.crypto import CryptoError, decrypt, encrypt


class TestRoundTrip:
    def test_round_trip(self):
        assert decrypt(encrypt("hunter2")) == "hunter2"

    def test_ciphertext_does_not_contain_the_plaintext(self):
        assert "hunter2" not in encrypt("hunter2")

    def test_two_encryptions_differ(self):
        # Fernet includes a random IV, so identical secrets do not produce identical rows.
        assert encrypt("same") != encrypt("same")

    def test_unicode_and_punctuation(self):
        secret = "pa'ss wörd&=?#"
        assert decrypt(encrypt(secret)) == secret

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_means_unset(self, value):
        assert encrypt(value) is None
        assert decrypt(value) is None

    def test_garbage_is_reported_clearly(self):
        with pytest.raises(CryptoError, match="SECRET_KEY has probably changed"):
            decrypt("not-a-real-token")
