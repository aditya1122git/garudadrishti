# JanNetra — Social Sentiment Watchtower

FastAPI + React/TypeScript + Bootstrap CSS + Poppins (Google Fonts) + Font Awesome + Recharts, MongoDB/Motor + Beanie, a local Hugging Face multilingual transformer, and APScheduler. The dashboard monitors aggregate conversation about Jan Suraaj Party and Prashant Kishore. It does not infer voting intentions or profile people. The product does not assert an elected office or title for any tracked entity.

## Start the complete demo

Install Docker Desktop / Docker Engine with Compose **2.24+**, then run from this directory:

```sh
docker compose up --build
```

Open http://localhost:8080. First startup creates indexes and approximately 25,000 synthetic posts across 30 reporting days.

Demo sign-in:

```text
Email: admin@jannetra.local
Password: JanNetra-Demo-2026!
```

Compose defaults to `SEED_MOCK_DATA=true`. The UI labels the dataset as synthetic. X and YouTube provide demo coverage; Facebook and Instagram remain **Not connected** and are excluded from totals. Mock labels never run or download the model. Demo mode cannot store real credentials or send notifications. Demo data lives in `jannetra_demo`, separate from the live `jannetra` database. Do not expose the demo to the public Internet.

The API and MongoDB have no published host ports. The frontend binds to loopback. MongoDB uses a persistent volume and an internal network. Its bundled development instance has no authentication; use an authenticated Atlas cluster or secured MongoDB deployment for production.

## Local development without Docker

Python 3.11+ and Node 22+ are required. Use two terminals. From `backend`:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Set these in your shell; PowerShell syntax shown:
$env:SEED_MOCK_DATA="true"
$env:DEMO_IN_MEMORY="true"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From `frontend`:

```sh
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to port 8000. `DEMO_IN_MEMORY=true` is a disposable, local-only store for machines without MongoDB. It requires demo mode. Its aggregation branch uses Python because mongomock does not implement `$dateTrunc`; Docker and all live deployments use the actual MongoDB aggregation pipeline. Restarting an in-memory demo resets changes.

## Configuration and switching to live data

A local `.env` is provided beside `docker-compose.yml`, with generated JWT/encryption secrets and demo settings. It is ignored by Git and excluded from the downloadable source ZIP. A fresh checkout can copy `.env.example` to `.env`. Never overwrite an existing encryption key. The API reads the root `.env` and then optional `backend/.env`; shell variables take precedence.

1. Set `SEED_MOCK_DATA=false` and `DEMO_IN_MEMORY=false`.
2. Set `MONGODB_URI` to an authenticated connection, preferably Atlas with TLS and a restricted network allowlist.
3. Generate two independent secrets:

   ```sh
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Set the first as `JWT_SECRET`, the second as `ENCRYPTION_KEY`. Keep the encryption key stable across restarts. Rotating it requires decrypting and re-encrypting stored secrets under maintenance; merely changing it makes existing credentials unreadable.
4. Set `BOOTSTRAP_EMAIL` and a unique `BOOTSTRAP_PASSWORD` of at least 14 characters (bcrypt maximum 72 UTF-8 bytes). These create an administrator only if that email does not already exist. Changing the environment variable does not reset an existing password.
5. Configure platform keys and restart, or enter them through **Settings → API connections**. A saved key is **pending** until a successful sync. No secret is returned by the settings API.
6. Run **Refresh**, inspect source health, and compare a sample of classifications against source material. A source failure preserves its last successful checkpoint and displays a partial-data warning.

### Environment variables

| Variable | Purpose |
|---|---|
| `MONGODB_URI`, `MONGODB_DATABASE` | Database connection/name; demo automatically uses a `_demo` suffix |
| `SEED_MOCK_DATA`, `DEMO_IN_MEMORY` | Explicit synthetic dataset / disposable development store |
| `JWT_SECRET`, `ENCRYPTION_KEY` | JWT signing and Fernet credential encryption; required in live mode |
| `BOOTSTRAP_EMAIL`, `BOOTSTRAP_PASSWORD` | Initial administrator |
| `HF_MODEL`, `HF_REVISION` | Model repository and pinned commit; default Cardiff NLP XLM-R sentiment |
| `HF_TOKEN` | Optional Hub download token; not required for the public default model |
| `HF_CACHE_DIR` | Persistent downloaded model cache; Compose supplies a named volume |
| `HF_DEVICE` | `cpu` (default), `cuda`, or `mps`; GPU runtime must be installed separately |
| `HF_BATCH_SIZE`, `HF_MAX_LENGTH` | Default 16 posts, 256 tokens per post; long posts are flagged as truncated |
| `HF_CPU_THREADS` | Default 2 CPU threads; inference runs in a background thread |
| `HF_LOCAL_FILES_ONLY` | Offline cache-only loading after downloading weights; default false |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key |
| `X_BEARER_TOKEN` | Paid public-search access token |
| `META_ACCESS_TOKEN` | Graph API token with appropriate permissions |
| `META_FACEBOOK_PAGE_ID`, `META_INSTAGRAM_ACCOUNT_ID` | Owned/managed account identifiers |
| `META_GRAPH_VERSION` | Configurable Graph API version; default `v23.0` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | STARTTLS SMTP; SES SMTP credentials work here |
| `SENDGRID_API_KEY` | Optional SendGrid HTTP delivery; takes precedence over SMTP |
| `OUTBOUND_ALLOWED_HOSTS` | Exact, comma-separated trusted webhook/adapter hostnames, no wildcard; required for custom outbound URLs |
| `ALLOWED_ORIGINS` | Exact CORS origins for the UI |
| `REPORTING_TIMEZONE` | `Asia/Kolkata` by default |
| `SCHEDULER_ENABLED`, `SYNC_INTERVAL_MINUTES` | Scheduler switch and 15-minute default interval |

### Hugging Face multilingual classifier

The primary and only classifier is `cardiffnlp/twitter-xlm-roberta-base-sentiment`, run locally with Transformers/PyTorch. Its [official model card](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment) lists Hindi and English among eight sentiment fine-tuning languages. **Hinglish, sarcasm and Bihar political discourse have not been validated here.** It predicts overall text tone, not entity-targeted stance. A negative news report can concern an issue rather than the tracked party. Validate on human-labeled examples before relying on political alerts; model probability is not calibrated accuracy.

There is no generative JSON, paid inference service, or mandatory classifier API key. Post text stays on the server. First real classification downloads about 1.1 GB of weights plus tokenizer files; demo mode skips this download. The model is cached once per API process, and serialized inference runs off the async event loop. Start deployment planning around 4 GB RAM for the API and benchmark on the actual host; this is a sizing estimate, not a measured guarantee. CPU works; GPU is optional. Linux CPU-only deployments can preinstall the matching wheel from the official PyTorch CPU index to avoid CUDA dependencies.

Only unclassified live posts are processed. Failed inference leaves posts pending and exposes `unavailable`; the next sync retries. Before first inference the status is `pending`. Model output count, named labels and probabilities are validated. Scores below 70% and truncated posts are flagged for review. The reason is a deterministic processing note, not an invented explanation. Historical labels keep their model provenance and are not overwritten.

To change models, set `HF_MODEL` and its matching `HF_REVISION` commit, then restart. Only sequence classifiers with exactly negative/neutral/positive named labels are accepted; unknown `LABEL_0` mappings fail closed. Remote repository code is disabled. The pinned official checkpoint uses restricted `weights_only=True` loading. Enable `HF_LOCAL_FILES_ONLY=true` after caching for offline operation. Keep one API worker with the built-in scheduler.

To download the model and run an explicit smoke check, from `backend` run:

```sh
python -m app.check_classifier
```

This uses built-in sample text only. It does not write posts, connect to social platforms or send alerts. It is a smoke test, not an accuracy benchmark.

## Connector coverage and limitations

| Platform | Implemented connector | Required access / coverage |
|---|---|---|
| X | Official recent-search endpoint, pagination, overlap deduplication, token replacement, retry/backoff | Paid public-search entitlement. Pricing/tier names vary. Free search is insufficient. Expired tokens can rotate; 429 limits never rotate to evade quotas. |
| YouTube | Official Data API v3 keyword video search + matching top-level comment threads | API key and quota. One combined keyword query every 2 hours, at most 3 search pages. Rechecks 30 recent discovered videos for new comments. Replies and exhaustive historical coverage are not included. |
| Facebook | Graph API owned/managed Page posts, or compliant paid-provider adapter | App review/permissions and owned/managed Page access, or a provider contract. No arbitrary public search. |
| Instagram | Graph API owned/managed account media, or compliant paid-provider adapter | Professional account permissions and owned/managed access, or a provider contract. No arbitrary public search. |

There is **no scraping and no manual upload/CSV/JSON import endpoint or UI**. CSV is export only. Missing Meta credentials show **Not connected**, never fabricated zeros. An unavailable source remains identifiable and its last observed figures are marked partial/stale. Zero engagement metrics may represent fields unavailable from the provider; “interactions” is likes + comments + shares, not views.

YouTube calls are bounded to control quota, not a guarantee of complete coverage. On any pagination cap, a connector fails explicitly and keeps the checkpoint rather than silently dropping a page. Lower the polling window / increase quota or implement a durable page cursor for high-volume accounts. The default search cadence is conservative; check the project's actual daily quota before increasing it. Short keywords such as PK are noisy; deactivate them in Settings if appropriate.

### Paid social-listening adapter contract

Brandwatch, Meltwater and Talkwalker are examples of potential licensed providers, **not preconfigured vendor integrations**. Their commercial APIs, permissions and schemas differ. JanNetra exposes one pluggable normalized connector. An organization-specific HTTPS adapter must map its licensed provider's response to this contract. Configure the adapter hostname in `OUTBOUND_ALLOWED_HOSTS`, then choose **Third-party aggregator** in Settings for Facebook or Instagram.

The connector sends an authenticated HTTPS POST:

```json
{"platform":"facebook","keywords":["Jan Suraaj Party"],"since":"2026-09-28T00:00:00+00:00","cursor":null}
```

The licensed adapter returns:

```json
{"posts":[{"id":"provider-post-id","author":"Public page name","content":"Mention text","url":"https://example.org/post","published_at":"2026-09-28T02:00:00Z","engagement":{"likes":12,"comments":3,"shares":2,"views":100}}],"next_cursor":null}
```

The adapter must enforce contracted data rights, platform policy, and provider quota. This server-to-server connector is not an import feature. No account is marked connected before credentials are configured, and no successful sync is claimed without a completed pull.

## Data flow, reporting and alerts

```text
APScheduler → connected API adapters → deduplicated raw posts
                                      ↓ only unclassified posts
                                   Hugging Face local transformer → validated sentiment
                                      ↓
MongoDB $match → $group with $dateTrunc(timezone) → daily aggregates
                                      ↓
Unique daily alert → dashboard / leased email + webhook delivery
```

Daily counts include classified posts from configured platforms only. `negativity_index = negative / classified × 100`; pending classifications are displayed separately and not counted as neutral. A reporting day is midnight-to-midnight in Asia/Kolkata, including the correct UTC boundaries. Aggregation recomputes the most recent 35 days to incorporate late-arriving posts. The dashboard shows 30 days. Weekly/monthly exports mean rolling 7/30 reporting days, including today; they do not mean calendar weeks/months.

Alert creation is idempotent on a unique `date` index, strictly **negative_count > threshold**. Evidence contains the five negative posts with highest likes + replies/comments + shares, and per-platform negative counts. Repeated syncs refresh counts/evidence without reopening resolved alerts. Resolving an alert acknowledges that reporting day; it will not create a second alert for the day. Past days can trigger if late data crosses the threshold. Changing the threshold takes effect on the next sync.

Notifications are configurable in Settings. They use per-channel atomic leases and record successful delivery; failed deliveries retry. Webhooks receive an `Idempotency-Key: jannetra:YYYY-MM-DD` header. The receiver should deduplicate it. Delivery is **at least once**, not exactly once: a crash after a remote send and before marking it delivered can duplicate an email. SMTP uses a stable Message-ID. Synthetic mode never sends external messages. Generic webhooks are supported; Slack/Telegram-specific payload mapping belongs in the receiver adapter.

## Security and deployment

- OAuth2 password form login issues a 60-minute JWT, validates audience/issuer/algorithm and loads the current user's role on every request. Tokens remain in browser memory, not local storage. Reloading signs out.
- Passwords use bcrypt. Login attempt buckets are stored in MongoDB with TTL; configure trusted proxy/rate limiting at the public edge. The bundled API ignores untrusted forwarded headers.
- Admins can change configuration, credentials, users, and alert resolution. Viewers can read and export. Create viewer accounts with authenticated `POST /api/users` (OpenAPI at `/docs` when accessing the API directly).
- Credentials and webhook secrets are encrypted with Fernet. API responses never disclose ciphertext or raw secrets. Audit logs record logins, views, exports and administrative changes; TTL is 90 days.
- Custom outbound endpoints require an environment-controlled exact hostname allowlist and public DNS resolution, checked at configuration and delivery. Redirects are disabled. Also enforce network egress rules in production to prevent DNS-rebinding and cloud-metadata access.
- Beanie models use `schema_version=1`; startup initializes all specified indexes. Native Motor updates implement idempotent upserts and aggregation. Future breaking schemas require a reviewed, versioned data migration before startup; no SQL or Alembic is used.
- Run **one API worker / one scheduler instance** with this APScheduler setup. For horizontal scaling, move ingestion/classification to dedicated workers with durable queue leases (arq/Celery) and disable the API scheduler. In-process scheduling is not a distributed queue.
- Deploy the API Dockerfile and frontend Dockerfile on a container host; provision Atlas, set private networking/service discovery, and point the frontend proxy to the API service. Terminate TLS at the edge, update CORS, keep database ports private, configure secrets, backups and retention/deletion policy. No hosting account has been provisioned by this project.
- Motor/Beanie 1.x are deliberately pinned to honor the requested stack. Motor is a legacy driver; assess its maintenance status and plan a Beanie/PyMongo Async migration before long-term production operation.

## Verification

```sh
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm run build
```

Tests cover IST boundaries, strict threshold semantics, daily alert deduplication, encrypted secrets, batch-length fallback, invalid confidence, Hindi/PK matching, X token failover without quota evasion, demo isolation, authentication, viewer restrictions, filtering/sorting and exports. The default suite runs with the explicit in-memory demo store. See `VERIFICATION.md` for checks actually performed in the build environment and checks still requiring real infrastructure/credentials.

Official references: [Hugging Face model card](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment), [YouTube API](https://developers.google.com/youtube/v3/docs), [YouTube comment threads](https://developers.google.com/youtube/v3/docs/commentThreads/list), [Beanie documentation](https://beanie-odm.dev/).

### UI assets

Bootstrap CSS and Font Awesome SVG icons are bundled locally. Poppins loads from Google Fonts, with a system-font fallback when Google Fonts is unavailable. Production CSP allows only the required Google Fonts stylesheet/font hosts. No Tailwind runtime or build plugin is used.
