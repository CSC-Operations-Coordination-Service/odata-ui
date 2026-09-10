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
| `odata-ui.stack.yml` | Production, as a Docker Swarm stack. Registry images, no build step. |

The trade-off of full isolation: a new backend setting has to be added to both files.
There is deliberately no `docker-compose.override.yml` — it would auto-load and merge
into whichever file you named, which is exactly what these files are built to avoid.

### Only the frontend is exposed

Every page is a client component, so **all API calls come from the browser**. The
frontend therefore proxies them: `rewrites()` in `frontend/next.config.mjs` forwards
`/api/*` to `backend:8000` over the internal network. The browser only ever addresses
the frontend, which means the backend publishes no port, no hostname is baked into
either image, and `CORS_ORIGINS` is empty because nothing is cross-origin.

Development goes through the same proxy, so a proxy problem surfaces locally rather
than only on deploy. The backend port is still published there for `/docs`.

Running the two natively (not in Docker) is the one case where `backend:8000` does not
resolve; set `BACKEND_INTERNAL_URL=http://localhost:8000` for the frontend.

### Deploying

```bash
# once per cluster - see .env.prod.example for generating the key
printf '%s' "<fernet key>" | docker secret create odata_ui_secret_key -
# once per cluster - the overlay the Traefik ingress stack shares with its backends
docker network create --driver overlay traefik

cp .env.prod.example .env      # fill in IMAGE_PREFIX, IMAGE_TAG, DB_NODE_REPLICA
set -a && . ./.env && set +a   # stack deploy does not read .env itself
docker stack deploy -c odata-ui.stack.yml odata-ui-prod
```

The stack publishes **no port**. The UI is served by the swarm Traefik ingress at
<http://NODE_IP/odata-ui/frontend> — any node IP answers, since Traefik itself is
published through the routing mesh. See *Ingress* below.

Deploy and roll back by tag — never `latest`, which makes the running version
unknowable and turns a restart into a deploy:

```bash
IMAGE_TAG=1.2.3 docker stack deploy -c odata-ui.stack.yml odata-ui-prod
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
Docker Hub. The frontend build must pass `BASE_PATH` and `NEXT_PUBLIC_API_URL`, both
set to the ingress path — see *Ingress*.

### Ingress

The frontend is exposed through the shared Traefik ingress (the `ingress` stack in
`maas-deploy`), on the convention that stack uses — `/<stack>/<service>/`:

```
http://<NODE_IP>/odata-ui/frontend
```

Three labels under `deploy.labels` do it, and `deploy` is not optional: labels set at
service level are *container* labels and Traefik's swarm provider ignores them. The
service also joins the external `traefik` overlay, because Traefik can only reach a
backend it shares a network with.

Two things about this route are worth knowing before changing it:

- **The prefix is not stripped, by design.** Next.js emits absolute asset URLs, so a
  stripped prefix gives the classic blank page with no CSS: the HTML loads, then the
  browser asks for `/_next/static/...` at the host root and Traefik has no route for
  it. Instead the app is *told* its sub-path via `basePath` in
  `frontend/next.config.mjs` — the same approach Grafana's `serve_from_sub_path` and
  RabbitMQ's `management.path_prefix` take in the sibling stacks.
- **The path is baked into the image, not configured at deploy time.** `basePath` is
  inlined by Next at build time into every asset URL, every `<Link>` and the `/api/*`
  rewrite, and `NEXT_PUBLIC_API_URL` is inlined into the `fetch()` calls, which Next
  does *not* prefix for you. Both are build args set by CI. Changing the route means
  rebuilding the image and updating the router rule together — editing only the label
  leaves a UI whose assets 404.

The router and service are both named `odata-ui-frontend`: once any
`traefik.http.routers.<name>.*` label is present the router takes that name and binds
to the service of the same name, so the two must match.

The rule is spelled out rather than inherited. The ingress generates
`PathPrefix(/<stack>/<service>)` from the stack namespace on its own, which would be
`/odata-ui-prod/frontend` for this file — deploying it as `odata-ui` instead would
produce `/odata-ui/frontend` with no rule label at all.

## CI/CD

[`.github/workflows/odata-ui.yml`](.github/workflows/odata-ui.yml) is a thin caller: it
owns the triggers and delegates every step of real work to the reusable workflows in
[workflow-catalog](https://github.com/CSC-Operations-Coordination-Service/workflow-catalog)
— `gitleaks.yml`, `node-workflow.yml` and `docker-build.yml`.

| trigger | what runs | what is pushed |
| --- | --- | --- |
| pull request | gitleaks, backend pytest, frontend `next build` | nothing |
| push to `main` or `develop` | the above + both images | **dev** Nexus registry, tagged with the branch and `sha-<short>` |
| tag `x.y.z` | the above + SBOMs + Cosign signatures | **prod** Nexus registry, tagged `x.y.z`, `x.y`, `latest` |

Nothing is pushed from a pull request by design: `docker-build.yml` always pushes what
it builds, so it is not called there at all.

Two deviations from the catalog's usual shape, both deliberate:

- **The backend tests run in a local job**, not via `python-ci.yml`. That primitive is
  shaped for a Nexus-published package — tox, `setuptools_scm`, twine — and this
  backend is a deployed application that is never published as a wheel. The job still
  reuses the catalog's `nexus-context` action, so pip installs from the same index as
  every other build.
- **`node-workflow.yml` is called with `build-image: false`** and the frontend image is
  built by the same `docker-build.yml` call as the backend's. `node-workflow`'s own
  image job exposes neither `insecure-registry` — the dev Nexus connector is plain
  HTTP, so BuildKit would fail the push on TLS — nor any of the image scanners.

### From a release tag to a running stack

The git tag *is* the image tag, so a release deploys with the string it was tagged with:

```bash
git tag 1.2.3 && git push origin 1.2.3   # CI builds, scans and signs the prod images

# then on the swarm manager, in .env:
#   IMAGE_PREFIX=<NEXUS_DOCKER_REGISTRY_PROD>/   (the trailing slash is part of the value)
#   IMAGE_TAG=1.2.3
set -a && . ./.env && set +a
docker stack deploy -c odata-ui.stack.yml odata-ui-prod
```

`latest` is pushed too, for tooling that expects it — do not deploy it. Pinning
`IMAGE_TAG` is what keeps the running version knowable and a rollback a one-line change.
For a staging deploy, point `IMAGE_PREFIX` at the **dev** registry and `IMAGE_TAG` at
the branch name or a `sha-<short>` build.

The frontend image job passes `BASE_PATH=/odata-ui/frontend` and
`NEXT_PUBLIC_API_URL=/odata-ui/frontend` as build args — a path, never a hostname, so
one image stays valid on any node. Both must agree with the router rule in
`odata-ui.stack.yml`; see *Ingress*.

### Security gates

| gate | tool | today |
| --- | --- | --- |
| Committed secrets | Gitleaks | **blocking**, every trigger |
| Dockerfile misconfiguration | Checkov | report-only |
| Image CVEs (`high` and above) | Grype | report-only → `grype-<image>-scan` artifact |
| Image hardening (CIS) | Dockle | report-only → `dockle-<image>-report` artifact |
| Dependency inventory | Syft → Dependency-Track | release tags only |
| Provenance | Cosign | release tags only, signed by digest |

Only the secret scan blocks today. The other three are report-only on purpose: their
baseline on `python:3.12-slim` and `node:22-alpine` is not yet known, and turning them
blocking blind would stop the first release on findings inherited from a base image
rather than on anything this repo wrote. Read one run's artifacts, then flip
`scan-fail-build`, `lint-image-fail-build` and `scan-dockerfile-soft-fail` in the
caller, one at a time.

One Checkov finding is already known: `CKV_DOCKER_3` on `backend/Dockerfile` — the
backend runs as root. Fixing it means adding a non-root `USER` *and* chowning `/data`
in the image, so the named volume inherits that ownership on first creation; the
frontend image already runs as `nextjs`.

SBOMs are generated on release tags only, so Dependency-Track gets one project version
per release instead of one per commit: `odata-ui-frontend` (npm inventory),
`odata-ui-backend-image` and `odata-ui-frontend-image` (image inventories), each
versioned by the tag. Verify a release image with:

```bash
cosign verify --key cosign.pub <registry>/odata-ui-backend@<digest>
```

### Secrets

Organization-level, passed to every called workflow with `secrets: inherit`. The full
catalog list is in
[SECRETS.md](https://github.com/CSC-Operations-Coordination-Service/workflow-catalog/blob/develop/.github/SECRETS.md);
this repo consumes:

| secret | used for |
| --- | --- |
| `NEXUS_HOST`, `NEXUS_PORT`, `NEXUS_USERNAME`, `NEXUS_PASSWORD` | pip index for the backend tests; Docker registry login |
| `NEXUS_DOCKER_REGISTRY_DEV` / `_PROD` | where images are pushed, per context |
| `DEPENDENCYTRACK_URL`, `DEPENDENCYTRACK_API_KEY` | SBOM upload (release only) |
| `COSIGN_PRIVATE_KEY`, `COSIGN_PASSWORD` | image signing (release only) |
| `GITLEAKS_LICENSE` | required by gitleaks-action on organization repos |

`SONAR_*` and `DOCKERHUB_*` are not used here: there is no SonarQube project for this
repo yet, and release images go to Nexus only.

### Not wired yet

- **ESLint.** `run-lint` is off because the repo has no eslint config — `next lint`
  would try to install one interactively and fail on a runner. `next build` still
  type-checks the whole project, so a type error fails the frontend job today. Add
  `eslint-config-next` and flip `run-lint` back on.
- **Frontend tests.** `run-tests` is off; there is no suite.
- **SonarQube.** Would need a `sonar-project.properties` and a project on the server.

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
