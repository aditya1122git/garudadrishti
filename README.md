# JanNetra — Social Sentiment Watchtower

FastAPI + React/TypeScript + Bootstrap CSS + Poppins (Google Fonts) + Font Awesome + Recharts, MongoDB/Motor + Beanie, a local Hugging Face multilingual transformer, and APScheduler. The dashboard monitors aggregate conversation about Jan Suraaj Party and Prashant Kishore. It does not infer voting intentions or profile people. The product does not assert an elected office or title for any tracked entity.

## Start JanNetra

Install Docker Desktop / Docker Engine with Compose **2.24+**. Copy `.env.example` to `.env`, set the required database, security, administrator, YouTube and classifier credentials, then run:

```sh
docker compose up --build
```

Open http://localhost:8080 and sign in with the administrator email and password you configured. The login form never exposes or prefills credentials. Compose defaults to live mode (`SEED_MOCK_DATA=false`).

The API and MongoDB have no published host ports. The frontend publishes `PUBLIC_PORT` (8080 by default) on all host interfaces and securely proxies `/api/*` to FastAPI over the private Docker network. MongoDB uses a persistent volume and an internal network. Its bundled development instance has no authentication; use an authenticated Atlas cluster or secured MongoDB deployment for production.

## Local development without Docker

Python 3.11+ and Node 22+ are required. Use two terminals. From `backend`:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From `frontend`:

```sh
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to port 8000.

## Configuration

A local `.env` is provided beside `docker-compose.yml`. It is ignored by Git and excluded from the downloadable source ZIP. A fresh checkout can copy `.env.example` to `.env`. Never overwrite an existing encryption key. The API reads the root `.env` and then optional `backend/.env`; shell variables take precedence.

1. Set `MONGODB_URI` to an authenticated connection, preferably Atlas with TLS and a restricted network allowlist.
2. Generate two independent secrets:

   ```sh
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Set the first as `JWT_SECRET`, the second as `ENCRYPTION_KEY`. Keep the encryption key stable across restarts. Rotating it requires decrypting and re-encrypting stored secrets under maintenance; merely changing it makes existing credentials unreadable.
3. For the first startup only, set `BOOTSTRAP_EMAIL` and a unique `BOOTSTRAP_PASSWORD` of at least 14 characters (bcrypt maximum 72 UTF-8 bytes). After the administrator exists in MongoDB, remove both variables. Changing them does not reset an existing password.
4. Configure platform keys and restart, or enter them through **Settings → API connections**. A saved key is **pending** until a successful sync. No secret is returned by the settings API.
5. Run **Refresh**, inspect source health, and compare a sample of classifications against source material. A source failure preserves its last successful checkpoint and displays a partial-data warning.

### Environment variables

| Variable | Purpose |
|---|---|
| `MONGODB_URI`, `MONGODB_DATABASE` | Database connection and database name |
| `JWT_SECRET`, `ENCRYPTION_KEY` | JWT signing and Fernet credential encryption; required in live mode |
| `BOOTSTRAP_EMAIL`, `BOOTSTRAP_PASSWORD` | Optional one-time initial administrator; required only when the users collection is empty |
| `HF_MODEL`, `HF_REVISION` | Model repository and pinned commit; default Cardiff NLP XLM-R sentiment |
| `HF_TOKEN` | Optional Hub download token; not required for the public default model |
| `HF_CACHE_DIR` | Persistent downloaded model cache; Compose supplies a named volume |
| `HF_DEVICE` | `cpu` (default), `cuda`, or `mps`; GPU runtime must be installed separately |
| `HF_BATCH_SIZE`, `HF_MAX_LENGTH` | Default 16 posts, 256 tokens per post; long posts are flagged as truncated |
| `HF_CPU_THREADS` | Default 2 CPU threads; inference runs in a background thread |
| `HF_LOCAL_FILES_ONLY` | Offline cache-only loading after downloading weights; default false |
| `GROQ_API_KEY`, `GROQ_MODEL` | Low-confidence fallback key and model; default `qwen/qwen3.8-27b` |
| `HF_CONFIDENCE_THRESHOLD`, `GROQ_CONCURRENCY` | Groq gate defaults to 0.60; 2 concurrent calls |
| `SARCASM_MODEL`, `SARCASM_REVISION` | Local Hindi/Hinglish detector; pinned `ashish5193/sarcasm_model` |
| `SARCASM_TOKENIZER_MODEL`, `SARCASM_TOKENIZER_REVISION` | Pinned Cardiff tokenizer required because the sarcasm repository does not bundle tokenizer files |
| `SARCASM_CONFIDENCE_THRESHOLD` | Sarcasm detection boundary; default 0.65 |
| `ENABLED_PLATFORMS` | Comma-separated sources: `facebook,instagram,x,youtube,news`; set `youtube` for YouTube-only operation |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key |
| `YOUTUBE_INITIAL_LOOKBACK_DAYS`, `YOUTUBE_TERMS_PER_QUERY` | First-run backfill window (7 days) and quota-aware keyword grouping (4 terms) |
| `APIFY_API_TOKEN` | The only required Apify value; shared across Facebook, Instagram, X and News |
| `APIFY_FACEBOOK_ACTOR_ID`, `APIFY_INSTAGRAM_ACTOR_ID`, `APIFY_X_ACTOR_ID`, `APIFY_NEWS_ACTOR_ID` | Optional advanced overrides; JanNetra supplies default Actor IDs |
| `APIFY_*_INPUT_JSON` | Optional Actor-specific input override with `{{keywords_json}}`, `{{query}}`, `{{since_iso}}`, `{{max_items}}` placeholders |
| `APIFY_MAX_ITEMS`, `APIFY_RUN_TIMEOUT_SECONDS` | Per-run item guard (50) and synchronous-run timeout (240 seconds) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | STARTTLS SMTP; SES SMTP credentials work here |
| `SENDGRID_API_KEY` | Optional SendGrid HTTP delivery; takes precedence over SMTP |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Enable one Telegram message, including the source link, for each newly classified negative post |
| `OUTBOUND_ALLOWED_HOSTS` | Exact, comma-separated trusted webhook/adapter hostnames, no wildcard; required for custom outbound URLs |
| `ALLOWED_ORIGINS` | Exact CORS origins for the UI |
| `REPORTING_TIMEZONE` | `Asia/Kolkata` by default |
| `SCHEDULER_ENABLED`, `SYNC_INTERVAL_MINUTES` | Scheduler switch and 15-minute default interval |

### Hugging Face multilingual classifier

The primary classifier is `cardiffnlp/twitter-xlm-roberta-base-sentiment`, run locally with Transformers/PyTorch. Its [official model card](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment) lists Hindi and English among eight sentiment fine-tuning languages. **Hinglish, sarcasm and Bihar political discourse have not been validated here.** It predicts overall text tone, not entity-targeted stance. A negative news report can concern an issue rather than the tracked party. Validate on human-labeled examples before relying on political alerts; model probability is not calibrated accuracy.

Hugging Face runs locally. YouTube classification uses the video title only. Each title passes through language detection, tracked-entity detection, Cardiff multilingual sentiment, and `ashish5193/sarcasm_model`. The target-wise combiner uses opponent/campaign context and high-precision Hindi/Hinglish cues alongside the sarcasm model because its training data is imbalanced and it can miss implicit political sarcasm. Only combined confidence below `HF_CONFIDENCE_THRESHOLD` (default 0.60) is sent to Groq (`GROQ_MODEL=qwen/qwen3.8-27b`). Mixed requires meaningful positive and negative stance toward the tracked target. `GROQ_API_KEY` is required for low-confidence verification. Missing keys/provider failures leave these items pending and excluded from final sentiment totals. Strict JSON output, result IDs/count validation, per-item retry on malformed batches, backoff and bounded concurrency are implemented. First real classification downloads about 1.6 GB of model weights plus tokenizer files. Models are cached once per API process, and serialized inference runs off the async event loop. Start deployment planning around 4 GB RAM for the API and benchmark on the actual host; this is a sizing estimate, not a measured guarantee. CPU works; GPU is optional.

Only unclassified live posts are normally processed. A versioned schema migration requeues active records when target-stance rules change. Failed inference leaves posts pending and exposes `unavailable`; the next sync retries. Before first inference the status is `pending`. Model output count, named labels and probabilities are validated. Groq results below the threshold and truncated HF inputs are flagged for review. Confidence is not calibrated accuracy; the stored record includes raw HF confidence, raw sarcasm-model probability, combined sarcasm confidence, language, targets and model provenance.

To change models, set `HF_MODEL` and its matching `HF_REVISION` commit, then restart. Only sequence classifiers with exactly negative/neutral/positive named labels are accepted; unknown `LABEL_0` mappings fail closed. Remote repository code is disabled. The pinned official checkpoint uses restricted `weights_only=True` loading. Enable `HF_LOCAL_FILES_ONLY=true` after caching for offline HF operation; Groq fallback still requires network access. Keep one API worker with the built-in scheduler.

To download the model and run an explicit smoke check, from `backend` run:

```sh
python -m app.check_classifier
```

This uses built-in sample text only. It does not write posts, connect to social platforms or send alerts. It is a smoke test, not an accuracy benchmark.

## Connector coverage and limitations

| Platform | Implemented connector | Required access / coverage |
|---|---|---|
| X | Configured Apify Actor, normalized output, overlap deduplication and retry/backoff | Apify token, Actor access and the Actor's input schema. |
| YouTube | Official Data API v3 video search + `videos.list` snippet/statistics | API key and quota. Every 2 hours, active terms are split into OR groups; each group gets a general search and a `videoDuration=short` search, with result deduplication. The initial strategy upgrade backfills 7 days. Only the video title is matched, stored, and classified. Descriptions and comments are excluded. Likes and views are read as video metadata. Legacy YouTube records outside the title-only scope remain stored but are excluded from feeds and totals. |
| Facebook | Configured Apify Actor | Actor backed by owned/managed Graph access or a licensed compliant listening provider; arbitrary public scraping is outside the supported configuration. |
| Instagram | Configured Apify Actor | Actor backed by owned/managed professional-account access or a licensed compliant listening provider; arbitrary public scraping is outside the supported configuration. |
| News | Configured Apify Actor | Public/licensed news access. Headline plus available summary is classified. |

There is no manual upload/CSV/JSON import endpoint or UI; CSV is export only. Missing Actor credentials show **Not connected**, never fabricated zeros. An unavailable source remains identifiable and its last observed figures are marked partial/stale. The operator must choose Actors and data access that comply with platform terms and applicable law. For Facebook and Instagram, JanNetra supports only owned/managed access or a licensed compliant listening source routed through Apify. Zero engagement metrics may represent unavailable fields; “interactions” is likes + comments + shares, not views.

YouTube Search API is relevance-ranked and does not promise an exhaustive list of every matching upload. JanNetra searches public videos across channels; it cannot use a person's YouTube watch history. Calls are bounded to control quota, and the dedicated short-duration query improves Shorts coverage without claiming that every under-four-minute video is a YouTube Short. The default search cadence is conservative; check the project's actual daily quota before increasing it. Short keywords such as PK are noisy; deactivate them in Settings if appropriate.

### Apify Actor contract

`APIFY_API_TOKEN` is sufficient for the standard setup. JanNetra currently selects `apify/facebook-search-scraper`, `data-slayer/instagram-keyword-posts-scraper`, `apidojo/tweet-scraper`, and `easyapi/google-news-scraper`, with source-specific keyword inputs and comments disabled. The connector runs Apify's synchronous dataset endpoint with bearer authentication, a response item guard, bounded timeout and retry/backoff. The EasyAPI news Actor requires a minimum request size of 100; JanNetra still limits the returned dataset items to `APIFY_MAX_ITEMS`.

Actor IDs and JSON templates remain optional advanced overrides because Store Actors and their schemas can change independently of JanNetra. When overriding an Actor, copy its working JSON input from Apify Console and replace values with the supported placeholders.

```json
{"searchQueries": {{keywords_json}}, "startDate": "{{since_iso}}", "maxItems": {{max_items}}}
```

Available placeholders are `{{keywords_json}}`, `{{query}}`, `{{since_iso}}`, and `{{max_items}}`. Property names must match the chosen Actor's input schema. Output normalization accepts common IDs, post text/caption/title, publication timestamps, URLs, authors and engagement counts. Items without a usable timestamp or tracked term are excluded. Social replies/comments are not requested by JanNetra. A custom Actor can return the canonical fields for deterministic mapping.

Apify usage can incur Actor and compute charges; `APIFY_MAX_ITEMS` is the local per-run guard. No source is marked live until its Actor run completes successfully.

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

Notifications are configurable in Settings. They use per-channel atomic leases and record successful delivery; failed deliveries retry. Webhooks receive an `Idempotency-Key: jannetra:YYYY-MM-DD` header. The receiver should deduplicate it. Delivery is **at least once**, not exactly once: a crash after a remote send and before marking it delivered can duplicate an email. SMTP uses a stable Message-ID. Generic webhooks are supported; Slack/Telegram-specific payload mapping belongs in the receiver adapter.

Per-post Telegram alerts are enabled when both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set. Each newly classified negative post is queued once and sent with its platform, author, confidence, excerpt and original link. Successful posts are marked sent; failed deliveries retry on a later sync. Existing historical negatives are not backfilled automatically, preventing a notification flood when Telegram is first enabled.

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

Tests cover IST boundaries, strict threshold semantics, daily alert deduplication, encrypted secrets, batch-length fallback, invalid confidence, Hindi/PK matching, X token failover without quota evasion, authentication, viewer restrictions, filtering/sorting and exports. See `VERIFICATION.md` for checks actually performed in the build environment and checks still requiring real infrastructure/credentials.

Official references: [Hugging Face model card](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment), [YouTube API](https://developers.google.com/youtube/v3/docs), [YouTube full video snippets](https://developers.google.com/youtube/v3/docs/videos/list), [Beanie documentation](https://beanie-odm.dev/).

### UI assets

Bootstrap CSS and Font Awesome SVG icons are bundled locally. Poppins loads from Google Fonts, with a system-font fallback when Google Fonts is unavailable. Production CSP allows only the required Google Fonts stylesheet/font hosts. No Tailwind runtime or build plugin is used.

## Local verification (2026-10-01)

See `MODEL-VALIDATION.md` for real model and YouTube results, including a high-confidence target-stance error. The current local preview uses port 5174 with `API_PROXY_TARGET=http://127.0.0.1:8001`; the API uses port 8001 because an existing Windows process occupies 8000. Default Docker ports are unchanged. Run only one scheduler instance against a database.
