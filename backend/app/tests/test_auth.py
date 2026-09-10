import asyncio

import httpx
import pytest
import respx

from app.auth import token_cache
from app.auth.strategies import (
    AuthError,
    Basic,
    OAuth2,
    StaticToken,
    build_authentication,
)
from app.crypto import encrypt

TOKEN_URL = "https://auth.example.org/token"


class FakeEndpoint:
    def __init__(self, **kwargs):
        self.id = kwargs.pop("id", 1)
        self.auth_method = kwargs.pop("auth_method", "oauth2")
        self.token_field_header = kwargs.pop("token_field_header", "Authorization")
        self.client_username = kwargs.pop("client_username", "user")
        self.token_url = kwargs.pop("token_url", TOKEN_URL)
        self.client_id = kwargs.pop("client_id", "my-client")
        self.scope = kwargs.pop("scope", "")
        self.grant_type = kwargs.pop("grant_type", "password")
        self.timeout = kwargs.pop("timeout", 30)
        self.enc_client_password = encrypt(kwargs.pop("client_password", "pa'ss word"))
        self.enc_client_secret = encrypt(kwargs.pop("client_secret", "sekret"))
        self.enc_static_token = encrypt(kwargs.pop("static_token", None))
        self.enc_oauth_basic_credential = encrypt(kwargs.pop("oauth_basic_credential", None))


@pytest.fixture(autouse=True)
def _clear_cache():
    token_cache.clear()
    yield
    token_cache.clear()


class TestSimpleStrategies:
    async def test_no_auth_sends_nothing(self):
        endpoint = FakeEndpoint(auth_method="none")
        async with httpx.AsyncClient() as client:
            assert await build_authentication(endpoint).get_headers(client) == {}

    async def test_basic(self):
        endpoint = FakeEndpoint(auth_method="basic", client_username="bob",
                                client_password="hunter2")
        async with httpx.AsyncClient() as client:
            headers = await build_authentication(endpoint).get_headers(client)
        # base64("bob:hunter2")
        assert headers == {"Authorization": "Basic Ym9iOmh1bnRlcjI="}

    async def test_basic_needs_a_username(self):
        endpoint = FakeEndpoint(auth_method="basic", client_username="")
        async with httpx.AsyncClient() as client:
            with pytest.raises(AuthError):
                await build_authentication(endpoint).get_headers(client)

    async def test_static_token_is_sent_verbatim(self):
        endpoint = FakeEndpoint(auth_method="static_token", static_token="Bearer abc123")
        async with httpx.AsyncClient() as client:
            headers = await build_authentication(endpoint).get_headers(client)
        assert headers == {"Authorization": "Bearer abc123"}

    async def test_custom_header_name(self):
        endpoint = FakeEndpoint(auth_method="static_token", static_token="abc",
                                token_field_header="X-Api-Key")
        async with httpx.AsyncClient() as client:
            headers = await build_authentication(endpoint).get_headers(client)
        assert headers == {"X-Api-Key": "abc"}

    def test_unknown_method_rejected(self):
        with pytest.raises(AuthError):
            build_authentication(FakeEndpoint(auth_method="kerberos"))


class TestOAuth2:
    @respx.mock
    async def test_password_grant_is_form_encoded(self):
        route = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "tok1", "token_type": "Bearer", "expires_in": 3600}
            )
        )
        endpoint = FakeEndpoint()
        async with httpx.AsyncClient() as client:
            headers = await OAuth2(endpoint).get_headers(client)

        assert headers == {"Authorization": "Bearer tok1"}
        body = route.calls.last.request.content.decode()
        # The password contains a space and a quote; both must be encoded, not
        # concatenated raw as maas-collector does.
        assert "password=pa%27ss+word" in body
        assert "grant_type=password" in body
        assert "client_id=my-client" in body
        assert "client_secret=sekret" in body

    @respx.mock
    async def test_client_credentials_grant_sends_no_username(self):
        route = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "t", "token_type": "Bearer"})
        )
        endpoint = FakeEndpoint(grant_type="client_credentials")
        async with httpx.AsyncClient() as client:
            await OAuth2(endpoint).get_headers(client)
        body = route.calls.last.request.content.decode()
        assert "grant_type=client_credentials" in body
        assert "username" not in body and "password" not in body

    @respx.mock
    async def test_non_bearer_token_type_is_not_prefixed(self):
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "raw", "token_type": "mac"})
        )
        async with httpx.AsyncClient() as client:
            headers = await OAuth2(FakeEndpoint()).get_headers(client)
        assert headers == {"Authorization": "raw"}

    @respx.mock
    async def test_basic_credential_goes_on_the_token_request(self):
        route = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "t", "token_type": "Bearer"})
        )
        endpoint = FakeEndpoint(oauth_basic_credential="Y2lkOmNzZWM=")
        async with httpx.AsyncClient() as client:
            await OAuth2(endpoint).get_headers(client)
        assert route.calls.last.request.headers["Authorization"] == "Basic Y2lkOmNzZWM="

    @respx.mock
    async def test_valid_token_is_reused(self):
        route = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
            )
        )
        auth = OAuth2(FakeEndpoint())
        async with httpx.AsyncClient() as client:
            await auth.get_headers(client)
            await auth.get_headers(client)
            await auth.get_headers(client)
        assert route.call_count == 1

    @respx.mock
    async def test_expired_token_triggers_a_new_grant(self):
        respx.post(TOKEN_URL).mock(
            side_effect=[
                httpx.Response(200, json={"access_token": "old", "token_type": "Bearer",
                                          "expires_in": 0}),
                httpx.Response(200, json={"access_token": "new", "token_type": "Bearer",
                                          "expires_in": 3600}),
            ]
        )
        auth = OAuth2(FakeEndpoint())
        async with httpx.AsyncClient() as client:
            assert (await auth.get_headers(client))["Authorization"] == "Bearer old"
            assert (await auth.get_headers(client))["Authorization"] == "Bearer new"

    @respx.mock
    async def test_refresh_token_is_preferred_over_a_full_grant(self):
        route = respx.post(TOKEN_URL).mock(
            side_effect=[
                httpx.Response(200, json={"access_token": "a1", "token_type": "Bearer",
                                          "expires_in": 0, "refresh_token": "r1",
                                          "refresh_expires_in": 7200}),
                httpx.Response(200, json={"access_token": "a2", "token_type": "Bearer",
                                          "expires_in": 3600}),
            ]
        )
        auth = OAuth2(FakeEndpoint())
        async with httpx.AsyncClient() as client:
            await auth.get_headers(client)
            assert (await auth.get_headers(client))["Authorization"] == "Bearer a2"
        body = route.calls.last.request.content.decode()
        assert "grant_type=refresh_token" in body and "refresh_token=r1" in body

    @respx.mock
    async def test_rejected_refresh_falls_back_to_a_full_grant(self):
        respx.post(TOKEN_URL).mock(
            side_effect=[
                httpx.Response(200, json={"access_token": "a1", "token_type": "Bearer",
                                          "expires_in": 0, "refresh_token": "r1",
                                          "refresh_expires_in": 7200}),
                httpx.Response(400, json={"error": "invalid_grant"}),
                httpx.Response(200, json={"access_token": "a3", "token_type": "Bearer",
                                          "expires_in": 3600}),
            ]
        )
        auth = OAuth2(FakeEndpoint())
        async with httpx.AsyncClient() as client:
            await auth.get_headers(client)
            assert (await auth.get_headers(client))["Authorization"] == "Bearer a3"

    @respx.mock
    async def test_error_from_token_endpoint_is_reported(self):
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(401, text="bad credentials")
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(AuthError, match="401"):
                await OAuth2(FakeEndpoint()).get_headers(client)

    @respx.mock
    async def test_missing_access_token_is_reported(self):
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"foo": "bar"}))
        async with httpx.AsyncClient() as client:
            with pytest.raises(AuthError, match="no access_token"):
                await OAuth2(FakeEndpoint()).get_headers(client)

    async def test_missing_token_url_is_reported(self):
        async with httpx.AsyncClient() as client:
            with pytest.raises(AuthError, match="token URL"):
                await OAuth2(FakeEndpoint(token_url="")).get_headers(client)

    @respx.mock
    async def test_unreachable_token_endpoint_is_reported(self):
        respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("boom"))
        async with httpx.AsyncClient() as client:
            with pytest.raises(AuthError, match="Could not reach"):
                await OAuth2(FakeEndpoint()).get_headers(client)


class TestTokenCache:
    @respx.mock
    async def test_concurrent_requests_fetch_one_token(self):
        route = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
            )
        )
        endpoint = FakeEndpoint()
        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *[token_cache.get_headers(endpoint, client) for _ in range(10)]
            )
        assert route.call_count == 1
        assert all(r == {"Authorization": "Bearer t"} for r in results)

    @respx.mock
    async def test_changing_credentials_invalidates_the_cache(self):
        route = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
            )
        )
        endpoint = FakeEndpoint()
        async with httpx.AsyncClient() as client:
            await token_cache.get_headers(endpoint, client)
            endpoint.enc_client_secret = encrypt("a-different-secret")
            await token_cache.get_headers(endpoint, client)
        assert route.call_count == 2

    @respx.mock
    async def test_explicit_invalidate(self):
        route = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
            )
        )
        endpoint = FakeEndpoint()
        async with httpx.AsyncClient() as client:
            await token_cache.get_headers(endpoint, client)
            token_cache.invalidate(endpoint.id)
            await token_cache.get_headers(endpoint, client)
        assert route.call_count == 2
