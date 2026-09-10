"""Authentication strategies for outbound OData requests.

Same shape as maas-collector's AUTH_METHOD_DICT -- each strategy just produces the
headers for a request -- but async, properly URL-encoded, and honouring verify_ssl on
the token request instead of hardcoding verify=False.
"""

import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.crypto import decrypt

# Fallback lifetime when the token endpoint omits expires_in. Matches maas-collector.
DEFAULT_TOKEN_LIFETIME = 86400
# Renew slightly early so a token cannot expire in flight.
EXPIRY_MARGIN = timedelta(seconds=30)


class AuthError(RuntimeError):
    """Raised when credentials are incomplete or the token endpoint refuses them."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def basic_header_value(username: str, password: str) -> str:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {encoded}"


class Authentication:
    """No-auth default; also the base class holding the header-name convention."""

    def __init__(self, endpoint: Any) -> None:
        self.endpoint = endpoint
        self.token_field_header = endpoint.token_field_header or "Authorization"

    async def get_headers(self, client: httpx.AsyncClient) -> dict:
        return {}

    def invalidate(self) -> None:
        """Drop any cached credential material."""


class StaticToken(Authentication):
    """A pre-issued token stored verbatim, including any 'Bearer ' prefix."""

    async def get_headers(self, client: httpx.AsyncClient) -> dict:
        token = decrypt(self.endpoint.enc_static_token)
        if not token:
            raise AuthError("No token stored for this endpoint.")
        return {self.token_field_header: token}


class Basic(Authentication):
    async def get_headers(self, client: httpx.AsyncClient) -> dict:
        username = self.endpoint.client_username or ""
        password = decrypt(self.endpoint.enc_client_password) or ""
        if not username:
            raise AuthError("Basic auth needs a username.")
        return {self.token_field_header: basic_header_value(username, password)}


class OAuth2(Authentication):
    """OAuth2 with lazy refresh, mirroring maas-collector's OAuth.get_token().

    Grant types: password and client_credentials. A refresh_token returned by the
    server is used to renew while it is still valid; otherwise we re-run the grant.
    """

    def __init__(self, endpoint: Any) -> None:
        super().__init__(endpoint)
        self.token: Optional[str] = None
        self.access_expires_at: datetime = _now()
        self.refresh_token: Optional[str] = None
        self.refresh_expires_at: Optional[datetime] = None

    def invalidate(self) -> None:
        self.token = None
        self.access_expires_at = _now()
        self.refresh_token = None
        self.refresh_expires_at = None

    async def get_headers(self, client: httpx.AsyncClient) -> dict:
        token = await self.get_token(client)
        return {self.token_field_header: token}

    async def get_token(self, client: httpx.AsyncClient) -> str:
        now = _now()
        if self.token and self.access_expires_at - EXPIRY_MARGIN > now:
            return self.token
        if (
            self.refresh_token
            and self.refresh_expires_at is not None
            and self.refresh_expires_at - EXPIRY_MARGIN > now
        ):
            await self._refresh(client)
        else:
            await self._init_token(client)
        if not self.token:  # pragma: no cover - defensive
            raise AuthError("Token endpoint returned no access token.")
        return self.token

    def _token_request_headers(self) -> dict:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        basic_credential = decrypt(self.endpoint.enc_oauth_basic_credential)
        if basic_credential:
            headers["Authorization"] = f"Basic {basic_credential}"
        return headers

    def _build_grant_data(self) -> dict:
        endpoint = self.endpoint
        grant_type = endpoint.grant_type or "password"
        data = {"grant_type": grant_type}
        if endpoint.client_id:
            data["client_id"] = endpoint.client_id
        client_secret = decrypt(endpoint.enc_client_secret)
        if client_secret:
            data["client_secret"] = client_secret
        if grant_type != "client_credentials":
            if not endpoint.client_username:
                raise AuthError("The password grant needs a username.")
            data["username"] = endpoint.client_username
            data["password"] = decrypt(endpoint.enc_client_password) or ""
        if endpoint.scope:
            data["scope"] = endpoint.scope
        return data

    async def _init_token(self, client: httpx.AsyncClient) -> None:
        if not self.endpoint.token_url:
            raise AuthError("OAuth2 is selected but no token URL is configured.")
        await self._post_token(client, self._build_grant_data())

    async def _refresh(self, client: httpx.AsyncClient) -> None:
        endpoint = self.endpoint
        data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token}
        if endpoint.client_id:
            data["client_id"] = endpoint.client_id
        client_secret = decrypt(endpoint.enc_client_secret)
        if client_secret:
            data["client_secret"] = client_secret
        if endpoint.scope:
            data["scope"] = endpoint.scope
        try:
            await self._post_token(client, data)
        except AuthError:
            # A rejected refresh token is recoverable: fall back to a full grant.
            self.refresh_token = None
            self.refresh_expires_at = None
            await self._init_token(client)

    async def _post_token(self, client: httpx.AsyncClient, data: dict) -> None:
        endpoint = self.endpoint
        try:
            response = await client.post(
                endpoint.token_url,
                data=data,
                headers=self._token_request_headers(),
                timeout=endpoint.timeout or 60,
            )
        except httpx.RequestError as exc:
            raise AuthError(f"Could not reach the token endpoint: {exc}") from exc

        if not 200 <= response.status_code < 300:
            raise AuthError(
                f"Token endpoint returned HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AuthError("Token endpoint did not return JSON.") from exc

        access_token = payload.get("access_token")
        if not access_token:
            raise AuthError("Token endpoint response has no access_token.")

        token_type = (payload.get("token_type") or "Bearer").lower()
        self.token = f"Bearer {access_token}" if token_type == "bearer" else access_token

        now = _now()
        # Careful: an explicit expires_in of 0 is meaningful, so test for None rather
        # than falsiness.
        expires_in = payload.get("expires_in")
        if expires_in is None:
            expires_in = DEFAULT_TOKEN_LIFETIME
        self.access_expires_at = now + timedelta(seconds=int(expires_in))

        self.refresh_token = payload.get("refresh_token")
        refresh_expires_in = payload.get("refresh_expires_in")
        if self.refresh_token and refresh_expires_in is not None:
            self.refresh_expires_at = now + timedelta(seconds=int(refresh_expires_in))
        else:
            self.refresh_expires_at = None


AUTH_METHODS = {
    "none": Authentication,
    "": Authentication,
    "basic": Basic,
    "static_token": StaticToken,
    "oauth2": OAuth2,
}


def build_authentication(endpoint: Any) -> Authentication:
    method = (endpoint.auth_method or "none").lower()
    try:
        return AUTH_METHODS[method](endpoint)
    except KeyError as exc:
        raise AuthError(f"Unsupported auth method {endpoint.auth_method!r}.") from exc
