import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.auth import token_cache
from app.db import create_db_and_tables, engine
from app.main import app
from app.odata import metadata as metadata_module
from app.models import Endpoint, QueryRun, SavedQuery
from sqlmodel import Session, delete

SERVICE = "https://prip.example.org"


@pytest.fixture
def client():
    create_db_and_tables()
    with Session(engine) as session:
        session.exec(delete(QueryRun))
        session.exec(delete(SavedQuery))
        session.exec(delete(Endpoint))
        session.commit()
    token_cache.clear()
    metadata_module.clear()
    with TestClient(app) as test_client:
        yield test_client


def make_endpoint(client, **overrides):
    payload = {
        "name": "prip",
        "base_url": SERVICE,
        "entity_location": "/odata/v1/",
        "default_entity_set": "Products",
        "odata_version": "v4",
        "auth_method": "none",
    }
    payload.update(overrides)
    response = client.post("/api/endpoints", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestEndpointCrud:
    def test_create_and_read(self, client):
        created = make_endpoint(client)
        assert created["name"] == "prip"
        assert client.get(f"/api/endpoints/{created['id']}").json()["base_url"] == SERVICE

    def test_secrets_are_never_returned(self, client):
        created = make_endpoint(
            client, auth_method="basic", client_username="bob", client_password="hunter2"
        )
        assert created["has_client_password"] is True
        assert "client_password" not in created
        assert "hunter2" not in client.get("/api/endpoints").text

    def test_secret_is_encrypted_at_rest(self, client):
        created = make_endpoint(
            client, auth_method="basic", client_username="bob", client_password="hunter2"
        )
        with Session(engine) as session:
            row = session.get(Endpoint, created["id"])
        assert row.enc_client_password and "hunter2" not in row.enc_client_password

    def test_omitted_secret_survives_a_patch(self, client):
        created = make_endpoint(client, auth_method="basic", client_password="hunter2")
        patched = client.patch(
            f"/api/endpoints/{created['id']}", json={"description": "renamed"}
        ).json()
        assert patched["has_client_password"] is True
        assert patched["description"] == "renamed"

    def test_empty_string_clears_a_secret(self, client):
        created = make_endpoint(client, auth_method="basic", client_password="hunter2")
        patched = client.patch(
            f"/api/endpoints/{created['id']}", json={"client_password": ""}
        ).json()
        assert patched["has_client_password"] is False

    def test_duplicate_name_rejected(self, client):
        make_endpoint(client)
        response = client.post(
            "/api/endpoints", json={"name": "prip", "base_url": SERVICE}
        )
        assert response.status_code == 409

    def test_bad_base_url_rejected(self, client):
        response = client.post("/api/endpoints", json={"name": "x", "base_url": "prip.org"})
        assert response.status_code == 422

    def test_delete(self, client):
        created = make_endpoint(client)
        assert client.delete(f"/api/endpoints/{created['id']}").status_code == 204
        assert client.get(f"/api/endpoints/{created['id']}").status_code == 404

    def test_missing_endpoint_is_404(self, client):
        assert client.get("/api/endpoints/999").status_code == 404


class TestProbe:
    @respx.mock
    def test_successful_probe_is_recorded(self, client):
        created = make_endpoint(client)
        respx.get(f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(200, json={"value": [{"Id": 1}]})
        )
        result = client.post(f"/api/endpoints/{created['id']}/probe").json()
        assert result["ok"] is True and result["status_code"] == 200
        assert client.get(f"/api/endpoints/{created['id']}").json()["last_probe_status"] == 200

    @respx.mock
    def test_failed_probe_reports_instead_of_raising(self, client):
        created = make_endpoint(client)
        respx.get(f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(401, text="denied")
        )
        result = client.post(f"/api/endpoints/{created['id']}/probe").json()
        assert result["ok"] is False and result["status_code"] == 401


class TestPreviewAndRun:
    def test_preview_builds_the_url_without_calling_the_service(self, client):
        created = make_endpoint(client)
        body = {
            "endpoint_id": created["id"],
            "spec": {
                "entity_set": "Products",
                "clauses": [{"field": "Name", "op": "contains", "value": "S1A"}],
                "top": 10,
            },
        }
        result = client.post("/api/query/preview", json=body).json()
        assert result["filter"] == "contains(Name,'S1A')"
        assert result["url"] == (
            f"{SERVICE}/odata/v1/Products?$filter=contains(Name,'S1A')&$top=10"
        )

    def test_preview_reports_a_bad_field(self, client):
        created = make_endpoint(client)
        body = {
            "endpoint_id": created["id"],
            "spec": {"clauses": [{"field": "Name eq 1 or 1", "value": "x"}]},
        }
        assert client.post("/api/query/preview", json=body).status_code == 400

    @respx.mock
    def test_run_returns_rows_and_columns(self, client):
        created = make_endpoint(client)
        respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(
                200,
                json={
                    "@odata.count": 42,
                    "value": [
                        {"Id": "1", "Name": "A"},
                        {"Id": "2", "Name": "B", "Extra": 3},
                    ],
                },
            )
        )
        body = {"endpoint_id": created["id"], "spec": {"entity_set": "Products", "top": 2}}
        result = client.post("/api/query/run", json=body).json()
        assert result["count"] == 2
        assert result["total_count"] == 42
        assert result["columns"] == ["Id", "Name", "Extra"]

    @respx.mock
    def test_upstream_error_becomes_502_with_detail(self, client):
        created = make_endpoint(client)
        respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(400, text="bad $filter")
        )
        body = {"endpoint_id": created["id"], "spec": {"entity_set": "Products"}}
        response = client.post("/api/query/run", json=body)
        assert response.status_code == 502
        detail = response.json()["detail"]
        assert detail["upstream_status"] == 400 and "bad $filter" in detail["upstream_body"]

    @respx.mock
    def test_run_is_logged_to_history(self, client):
        created = make_endpoint(client)
        respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(200, json={"value": [{"Id": 1}]})
        )
        body = {"endpoint_id": created["id"], "spec": {"entity_set": "Products"}}
        client.post("/api/query/run", json=body)
        history = client.get("/api/history").json()
        assert len(history) == 1 and history[0]["result_count"] == 1

    @respx.mock
    def test_failed_run_is_logged_too(self, client):
        created = make_endpoint(client)
        respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(500, text="boom")
        )
        body = {"endpoint_id": created["id"], "spec": {"entity_set": "Products"}}
        client.post("/api/query/run", json=body)
        history = client.get("/api/history").json()
        assert len(history) == 1 and history[0]["error"]

    @respx.mock
    def test_csv_export(self, client):
        created = make_endpoint(client)
        respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(
                200, json={"value": [{"Id": "1", "Name": "A", "Nested": {"k": "v"}}]}
            )
        )
        body = {"endpoint_id": created["id"], "spec": {"entity_set": "Products"}}
        response = client.post("/api/query/export?format=csv", json=body)
        assert response.status_code == 200
        assert "Id,Name,Nested" in response.text
        assert '{""k"": ""v""}' in response.text


class TestOAuthEndToEnd:
    @respx.mock
    def test_token_is_fetched_and_sent(self, client):
        created = make_endpoint(
            client,
            auth_method="oauth2",
            token_url="https://auth.example.org/token",
            client_id="cid",
            client_secret="csec",
            client_username="user",
            client_password="pass",
        )
        token_route = respx.post("https://auth.example.org/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "tok", "token_type": "Bearer", "expires_in": 3600}
            )
        )
        data_route = respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(200, json={"value": []})
        )
        body = {"endpoint_id": created["id"], "spec": {"entity_set": "Products"}}
        assert client.post("/api/query/run", json=body).status_code == 200
        assert token_route.called
        assert data_route.calls.last.request.headers["Authorization"] == "Bearer tok"

    @respx.mock
    def test_auth_failure_is_reported_as_502(self, client):
        created = make_endpoint(
            client, auth_method="oauth2", token_url="https://auth.example.org/token",
            client_username="user", client_password="bad",
        )
        respx.post("https://auth.example.org/token").mock(
            return_value=httpx.Response(401, text="nope")
        )
        body = {"endpoint_id": created["id"], "spec": {"entity_set": "Products"}}
        response = client.post("/api/query/run", json=body)
        assert response.status_code == 502
        assert "Authentication failed" in response.json()["detail"]["message"]


class TestMetadata:
    METADATA_XML = """<?xml version="1.0" encoding="utf-8"?>
    <edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
      <edmx:DataServices>
        <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="OData.CSC">
          <EntityType Name="Product">
            <Key><PropertyRef Name="Id"/></Key>
            <Property Name="Id" Type="Edm.Guid" Nullable="false"/>
            <Property Name="Name" Type="Edm.String"/>
            <NavigationProperty Name="Attributes" Type="Collection(OData.CSC.Attribute)"/>
          </EntityType>
          <EntityContainer Name="Container">
            <EntitySet Name="Products" EntityType="OData.CSC.Product"/>
          </EntityContainer>
        </Schema>
      </edmx:DataServices>
    </edmx:Edmx>"""

    @respx.mock
    def test_entity_sets_and_properties_are_parsed(self, client):
        created = make_endpoint(client)
        respx.get(f"{SERVICE}/odata/v1/$metadata").mock(
            return_value=httpx.Response(200, text=self.METADATA_XML)
        )
        result = client.get(f"/api/endpoints/{created['id']}/metadata").json()
        assert result["error"] is None
        entity_set = result["entity_sets"][0]
        assert entity_set["name"] == "Products"
        assert [p["name"] for p in entity_set["properties"]] == ["Id", "Name"]
        assert entity_set["properties"][0]["is_key"] is True
        assert entity_set["properties"][0]["type"] == "Guid"
        assert entity_set["navigation_properties"] == ["Attributes"]

    @respx.mock
    def test_unavailable_metadata_degrades_gracefully(self, client):
        created = make_endpoint(client)
        respx.get(f"{SERVICE}/odata/v1/$metadata").mock(
            return_value=httpx.Response(404, text="nope")
        )
        result = client.get(f"/api/endpoints/{created['id']}/metadata").json()
        assert result["entity_sets"] == [] and "404" in result["error"]


class TestSavedQueries:
    def test_builtin_templates_are_seeded(self, client):
        names = [q["name"] for q in client.get("/api/queries").json()]
        assert "Product by Id" in names and "Name contains" in names

    def test_placeholders_become_declared_params(self, client):
        created = client.post(
            "/api/queries",
            json={
                "name": "mine",
                "entity_set": "Products",
                "spec": {"raw_filter": "Name eq {{who}}"},
            },
        ).json()
        assert [p["name"] for p in created["params"]] == ["who"]

    @respx.mock
    def test_running_the_name_contains_template(self, client):
        endpoint = make_endpoint(client)
        route = respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(200, json={"value": [{"Id": 1}]})
        )
        template = next(
            q for q in client.get("/api/queries").json() if q["name"] == "Name contains"
        )
        response = client.post(
            f"/api/queries/{template['id']}/run",
            json={"endpoint_id": endpoint["id"], "params": {"text": "S1A_IW"}},
        )
        assert response.status_code == 200
        assert "contains(Name,'S1A_IW')" in str(route.calls.last.request.url)

    @respx.mock
    def test_running_the_product_by_id_template(self, client):
        endpoint = make_endpoint(client)
        guid = "0f3a4b5c-1234-4abc-8def-1234567890ab"
        route = respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(200, json={"Id": guid, "Name": "A"})
        )
        template = next(
            q for q in client.get("/api/queries").json() if q["name"] == "Product by Id"
        )
        response = client.post(
            f"/api/queries/{template['id']}/run",
            json={"endpoint_id": endpoint["id"], "params": {"id": guid}},
        )
        assert response.status_code == 200
        assert str(route.calls.last.request.url).endswith(f"Products({guid})")
        # A single entity is normalised into a one-row table.
        assert response.json()["count"] == 1

    def test_missing_param_is_422_and_names_it(self, client):
        endpoint = make_endpoint(client)
        template = next(
            q for q in client.get("/api/queries").json() if q["name"] == "Name contains"
        )
        response = client.post(
            f"/api/queries/{template['id']}/run",
            json={"endpoint_id": endpoint["id"], "params": {}},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["missing"] == ["text"]

    def test_template_without_an_endpoint_needs_one_at_run_time(self, client):
        template = next(
            q for q in client.get("/api/queries").json() if q["name"] == "Name contains"
        )
        response = client.post(
            f"/api/queries/{template['id']}/run", json={"params": {"text": "x"}}
        )
        assert response.status_code == 400

    def test_preview_a_template(self, client):
        endpoint = make_endpoint(client)
        template = next(
            q for q in client.get("/api/queries").json() if q["name"] == "Published between"
        )
        result = client.post(
            f"/api/queries/{template['id']}/preview",
            json={
                "endpoint_id": endpoint["id"],
                "params": {"start": "2024-01-01", "end": "2024-01-31"},
            },
        ).json()
        assert "PublicationDate%20ge%202024-01-01T00:00:00.000Z" in result["url"]

    def test_update_and_delete(self, client):
        created = client.post(
            "/api/queries", json={"name": "mine", "spec": {"top": 5}}
        ).json()
        patched = client.patch(
            f"/api/queries/{created['id']}", json={"name": "renamed"}
        ).json()
        assert patched["name"] == "renamed" and patched["spec"]["top"] == 5
        assert client.delete(f"/api/queries/{created['id']}").status_code == 204

    def test_list_filtered_by_endpoint_includes_global_templates(self, client):
        endpoint = make_endpoint(client)
        client.post(
            "/api/queries", json={"name": "endpoint-specific", "endpoint_id": endpoint["id"]}
        )
        names = [
            q["name"] for q in client.get(f"/api/queries?endpoint_id={endpoint['id']}").json()
        ]
        assert "endpoint-specific" in names and "Name contains" in names


class TestImport:
    CREDENTIALS = """{
      "interfaces": [
        {"name": "oauth_if", "auth_method": "OAuth", "token_field_header": "Authorization",
         "odata_product_url": "https://prip.example.org", "token_url": "https://a.org/token",
         "client_id": "cid", "client_secret": "csec", "client_username": "u",
         "client_password": "p"},
        {"name": "basic_if", "auth_method": "Basic", "product_url": "https://b.example.org",
         "client_username": "u", "client_password": "p"},
        {"name": "no_url_if"}
      ]
    }"""

    def test_import_maps_legacy_aliases_and_auth(self, client):
        result = client.post(
            "/api/endpoints/import", json={"content": self.CREDENTIALS}
        ).json()
        actions = {item["name"]: item["action"] for item in result["imported"]}
        assert actions == {"oauth_if": "created", "basic_if": "created",
                           "no_url_if": "skipped"}

        endpoints = {e["name"]: e for e in client.get("/api/endpoints").json()}
        assert endpoints["oauth_if"]["base_url"] == "https://prip.example.org"
        assert endpoints["oauth_if"]["auth_method"] == "oauth2"
        assert endpoints["oauth_if"]["has_client_secret"] is True
        assert endpoints["basic_if"]["auth_method"] == "basic"

    def test_reimport_skips_without_overwrite(self, client):
        client.post("/api/endpoints/import", json={"content": self.CREDENTIALS})
        result = client.post(
            "/api/endpoints/import", json={"content": self.CREDENTIALS}
        ).json()
        assert all(
            item["action"] == "skipped" for item in result["imported"]
        )

    def test_overwrite_updates(self, client):
        client.post("/api/endpoints/import", json={"content": self.CREDENTIALS})
        result = client.post(
            "/api/endpoints/import", json={"content": self.CREDENTIALS, "overwrite": True}
        ).json()
        actions = {item["name"]: item["action"] for item in result["imported"]}
        assert actions["oauth_if"] == "updated"

    def test_bad_json_rejected(self, client):
        assert client.post(
            "/api/endpoints/import", json={"content": "{not json"}
        ).status_code == 400

    def test_wrong_shape_rejected(self, client):
        assert client.post(
            "/api/endpoints/import", json={"content": '{"collectors": []}'}
        ).status_code == 400


class TestHistory:
    @respx.mock
    def test_clear(self, client):
        created = make_endpoint(client)
        respx.get(url__startswith=f"{SERVICE}/odata/v1/Products").mock(
            return_value=httpx.Response(200, json={"value": []})
        )
        client.post("/api/query/run",
                    json={"endpoint_id": created["id"], "spec": {"entity_set": "Products"}})
        assert client.delete("/api/history").status_code == 204
        assert client.get("/api/history").json() == []
