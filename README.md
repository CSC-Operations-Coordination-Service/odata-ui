# OData Explorer

A self-hosted web console for querying OData interfaces. Register a service once —
base URL plus whatever it needs for authentication — then query it from the browser
instead of hand-crafting URLs and fetching OAuth tokens with `curl`.

- **Guided builder** with field autocomplete from `$metadata`, plus a raw escape hatch.
- **Parameterised templates** — get a product by id, find products whose name contains
  something, published-between, and any query you save yourself.
- **The generated URL is always visible** and copyable, so you can paste it into `curl`.
- **Credentials encrypted at rest** in SQLite; never returned to the browser.

The endpoint model mirrors `maas-collector`'s `ODataCollectorConfiguration` and its
credential-file `interfaces` block, so both systems describe an interface the same way.

## Quick start

```bash
cp .env.example .env
# generate a key and paste it into SECRET_KEY
docker run --rm python:3.12-slim sh -c \
  "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"

docker compose up --build -d
```

- UI: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>

To try it without any credentials, register the public Northwind service:

| field | value |
| --- | --- |
| Name | `northwind` |
| Base URL | `https://services.odata.org` |
| Entity location | `/V4/Northwind/Northwind.svc/` |
| Default entity set | `Products` |
| Auth method | None |

Then **Test connection**, open **Query**, add a condition
`ProductName contains Ch`, and press **Run**.

## Configuration

All backend settings come from the environment (see `.env.example`).

| variable | default | meaning |
| --- | --- | --- |
| `SECRET_KEY` | — | **Required.** Fernet key encrypting stored credentials. |
| `DB_PATH` | `/data/odata_ui.db` | SQLite file. Held in the `odata-ui-data` volume. |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Origins the API accepts. |
| `SECRET_KEY_FILE` | — | Path to a file holding the key instead, e.g. a Docker secret. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Where the **browser** reaches the API. `/` = same origin, via the Next proxy. |
| `BACKEND_INTERNAL_URL` | `http://backend:8000` | Where the **Next server** proxies `/api/*`. Build-time for the production image. |
| `HISTORY_LIMIT` | `500` | Query runs retained. |
| `METADATA_CACHE_TTL` | `600` | Seconds a parsed `$metadata` stays cached. |
| `MAX_PAGE_SIZE` | `5000` | Hard cap on `$top`. |

Two things bite people:

- `NEXT_PUBLIC_API_URL` is **inlined into the frontend bundle at build time**. Change it
  before `docker compose build`, not after. Set it to `/` to make requests relative,
  which is how the production stack avoids baking a hostname into the image.
- `localhost` and `127.0.0.1` are *different origins* to a browser. Whichever you type in
  the address bar must appear in `CORS_ORIGINS`.

Changing `SECRET_KEY` makes existing stored secrets unreadable; you would have to
re-enter the credentials for every endpoint.

## Deployment

Two self-contained compose files. Neither layers onto the other, so a change to one
cannot affect the other environment:

| file | role |
| --- | --- |
| `docker-compose.yml` | Development. `docker compose up` — published ports, bind mounts, live reload. |
| `docker-compose.prod.yml` | Production, as a Docker Swarm stack. Registry images, no build step. |

The trade-off of full isolation: a new backend setting has to be added to both files.
There is deliberately no `docker-compose.override.yml` — it would auto-load and merge
into whichever file you named, which is exactly what these files are built to avoid.

### Only the frontend is exposed

Every page is a client component, so **all API calls come from the browser**. The
frontend therefore proxies them: `rewrites()` in `frontend/next.config.mjs` forwards
`/api/*` to `backend:8000` over the internal network. The browser only ever addresses
the frontend, which means the backend publishes no port, `NEXT_PUBLIC_API_URL` is
baked in as `/` — one image, no hostname, valid in any environment — and `CORS_ORIGINS`
is empty because nothing is cross-origin.

Development goes through the same proxy, so a proxy problem surfaces locally rather
than only on deploy. The backend port is still published there for `/docs`.

Running the two natively (not in Docker) is the one case where `backend:8000` does not
resolve; set `BACKEND_INTERNAL_URL=http://localhost:8000` for the frontend.

### Deploying

```bash
# once per cluster - see .env.prod.example for generating the key
printf '%s' "<fernet key>" | docker secret create odata_ui_secret_key -

cp .env.prod.example .env      # fill in IMAGE_PREFIX, IMAGE_TAG, DB_NODE_REPLICA
set -a && . ./.env && set +a   # stack deploy does not read .env itself
docker stack deploy -c docker-compose.prod.yml odata-ui-prod
```

Deploy and roll back by tag — never `latest`, which makes the running version
unknowable and turns a restart into a deploy:

```bash
IMAGE_TAG=1.2.3 docker stack deploy -c docker-compose.prod.yml odata-ui-prod
```

Three swarm-specific things the stack file already accounts for, each of which fails
*silently* if you get it wrong:

- `depends_on`, `restart`, `security_opt` and the short `tmpfs` key are **ignored** by
  swarm, so the file uses `deploy.*` and long-syntax tmpfs mounts.
- A `-` inside a `${VAR:?message}` message makes swarm's interpolator substitute the
  message text *as the value* instead of erroring. Keep those messages dash-free.
- SQLite is a node-local volume, so the backend is pinned by node label
  (`node.labels.role` + `node.labels.replicas`, matching the other stacks here) and its
  `update_config.order` is `stop-first` — two tasks must never hold the file at once.
  The role label alone is not sufficient when several nodes share it: a reschedule onto
  a sibling would come up with an *empty database*, which is why `DB_NODE_REPLICA`
  narrows it to a single node. Drop that constraint only if one node has the role.

Both services log to Loki via the `loki` driver, using the same `x-logging` anchor and
endpoint as the other stacks here, labelled `stack=odata-ui-prod,service={{.Name}}`.
That driver keeps nothing locally, so `docker service logs` will not show anything —
query Loki instead. The driver plugin has to be installed on the nodes.

`SECRET_KEY` is a swarm secret delivered at `/run/secrets/odata_ui_secret_key` and read
via `SECRET_KEY_FILE`, so it never appears in the service spec. Back it up alongside
the `odata-ui-prod_odata-ui-data` volume: the volume holds the encrypted credentials,
the key decrypts them, and either one alone is useless.

Images are `${IMAGE_PREFIX}odata-ui-backend` and `${IMAGE_PREFIX}odata-ui-frontend`,
built by the reusable `docker-build.yml` workflow. `IMAGE_PREFIX` carries its own
trailing slash, because the stack parser cannot append one conditionally; leaving it
empty runs images preloaded into each node's local store, which then needs
`docker stack deploy --resolve-image never` or swarm resolves the bare tag against
Docker Hub. The frontend build must pass `NEXT_PUBLIC_API_URL=/`.

## Authentication methods

| method | what is sent |
| --- | --- |
| `none` | nothing |
| `basic` | `Authorization: Basic base64(user:password)` |
| `static_token` | the stored token verbatim, including any `Bearer ` prefix |
| `oauth2` | `password` or `client_credentials` grant, with lazy refresh |

OAuth2 tokens are cached in memory per endpoint and renewed only when they expire; a
per-endpoint lock keeps concurrent queries from stampeding the token endpoint. Tokens
are never written to the database and never sent to the browser.

### Importing from maas-collector

**Endpoints → Import…** accepts a pasted maas-collector credential file — the
`interfaces` list, including the legacy `odata_product_url` and `odata_version` aliases.
It is a convenience: this app's database is the source of truth afterwards.

## Differences from maas-collector

Deliberate, and the reason the query-building code was not copied verbatim:

1. **Everything is URL-encoded.** maas-collector builds the OAuth body and the OData
   query by raw f-string concatenation.
2. **String literals are escaped** — a single quote is doubled, so a value typed in the
   web form cannot break out of the filter it sits in.
3. **`verify=False` is not hardcoded** on the token request; the endpoint's TLS setting
   is honoured.
4. **Configuration is validated** by pydantic rather than silently dropping unknown keys.
5. **No legacy alias pairs** — one `base_url`, one `odata_version`.

## Development

```bash
# Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
SECRET_KEY=<key> DB_PATH=./data/dev.db .venv/bin/python -m uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Tests:

```bash
cd backend
SECRET_KEY=<key> DB_PATH=":memory:" .venv/bin/python -m pytest app/tests -q
```

156 tests cover literal escaping and injection attempts, URL building for v3 and v4,
the OAuth token lifecycle, encryption, template substitution, and the API end to end
with the upstream service mocked.

## Layout

```
backend/app/
  odata/literals.py   value → OData literal, with escaping   (the security-critical bit)
  odata/builder.py    QuerySpec → URL                        (pure, heavily tested)
  odata/client.py     execution, v3/v4 response normalising
  odata/metadata.py   $metadata → entity sets + properties
  auth/strategies.py  none | basic | static_token | oauth2
  auth/token_cache.py per-endpoint token reuse and refresh locking
  templating.py       {{param}} substitution, typed and escaped
  routers/            endpoints, query, queries, history

frontend/src/
  app/query                    the workspace: builder, raw mode, live URL, results
  app/queries                  template library and run forms
  app/endpoints                CRUD, connection test, import
  app/history                  recent runs, re-openable
  components/SpaceBackdrop     decorative isometric lattice, cubes, orbits, starfield
  components/PageTransition    replays the enter animation on route change
  app/globals.css              design tokens, motion, and the reduced-motion opt-out
```

## Visual notes

The backdrop is a single fixed SVG behind the app: an isometric lattice on a 30°
projection, a few drifting cubes on that same grid, dashed orbital rings and a
starfield, all tinted from the theme tokens. Surfaces sit on top as lightly
translucent glass so it reads through the layout without competing with a table.

Two things constrain how it is built:

- The page background lives on `<html>`, not `<body>`. A `<body>` background paints
  in the block-background phase — above any negative-`z-index` layer — and would hide
  the backdrop entirely.
- The starfield is a fixed literal list, not `Math.random()`, so the server and client
  render identical markup and hydration does not mismatch.

Everything that moves is switched off under `prefers-reduced-motion: reduce`; the
shapes stay, the motion stops.
