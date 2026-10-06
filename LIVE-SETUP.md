# What is needed to connect live data

The local `.env` is created in this project directory. Live mode is the default. Do not paste API keys into chat; enter them in `.env` or the application's admin settings.

## Required for live deployment

1. **Hosting choice:** local PC, VPS, or cloud, plus available RAM and CPU/GPU. Plan initially for roughly 4 GB API memory and benchmark; the multilingual weights download is around 1.1 GB, excluding runtime dependencies. Small/free containers may not fit.
2. **Database:** authenticated MongoDB URI (Atlas or self-hosted).
3. **Administrator:** preferred email and a unique password. No default login is provided. JWT and encryption keys in the local `.env` must be preserved.
4. **At least one source:** YouTube Data API v3 key, an Apify API token for social sources, or the credential-free Google News RSS source.

## Optional sources and notifications

- **Apify sources:** `APIFY_API_TOKEN` is the only setting required for Facebook, Instagram and X. JanNetra uses fixed Actor IDs and validated source-specific inputs.
- **News:** Google News RSS needs no key and monitors the approved Bihar publisher list documented in the README.
- **Telegram alerts:** set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for immediate current-day negative-post alerts.
- **Keywords:** confirm tracked terms in Settings. The dashboard daily threshold remains an internal 500-negative-post rule.
- **Validation examples:** a small anonymized set of Hindi/Hinglish/English texts with analyst-agreed labels helps evaluate domain quality. This is a development evaluation exercise; the app has no manual import feature.

## Hugging Face credentials

The default public multilingual model runs locally and needs **no Hugging Face API key**. `HF_TOKEN` is optional for authenticated model downloads. `HF_MODEL`, the pinned `HF_REVISION`, CPU defaults, batch size and cache settings are already set. Post text is not sent to Hugging Face. Network access is needed for the initial download; afterwards cached inference can run offline.

## Switching to live

Configure the database, administrator and source credentials, then restart. Test the model with `python -m app.check_classifier` from `backend`, trigger Refresh, and inspect source/classifier health before enabling external notifications. For local Python execution use `mongodb://127.0.0.1:27017`; the default `mongodb://mongo:27017` hostname is for Docker Compose.

## Hostinger Docker Compose deployment

Hostinger clones the repository, so the ignored local `.env` file is not present on the server. Add these variables in the Hostinger project environment before deploying:

- `JWT_SECRET` - an independent random value of at least 32 characters
- `ENCRYPTION_KEY` - a Fernet key; keep this stable for the lifetime of the database
- `BOOTSTRAP_EMAIL` and `BOOTSTRAP_PASSWORD` - required on the first deployment because the new Mongo volume has no users; password must be 14-72 UTF-8 bytes
- `YOUTUBE_API_KEY`, `APIFY_API_TOKEN`, `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` when Telegram alerts are enabled
- `PUBLIC_PORT=8080` to use `http://SERVER_IP:8080`, or `PUBLIC_PORT=80` when port 80 is free

Generate the two security values locally without printing application credentials:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The Compose file explicitly forwards deployment environment variables to the API container. It also fails during Compose validation with a clear message when `JWT_SECRET` or `ENCRYPTION_KEY` is absent. After the first successful startup, the administrator remains in the persistent Mongo volume; `BOOTSTRAP_EMAIL` and `BOOTSTRAP_PASSWORD` can then be removed before a later redeploy.

The frontend is the only public container. It proxies all `/api/*` requests to FastAPI on the private Docker network, so the backend is checked at `http://SERVER_IP:PUBLIC_PORT/api/health`; a separate public API port is neither required nor exposed. When using port 8080, allow inbound TCP 8080 in **Hostinger hPanel -> VPS -> Firewall**. A timeout means the host port is blocked or the deployment still uses the old loopback-only Compose mapping. A working health request returns `{"status":"ok","demo":false}`.

## YouTube-only hybrid update

`ENABLED_PLATFORMS=youtube` limits active ingestion to YouTube. Only video titles are classified; descriptions and comments are excluded. General and short-duration searches run across public channels, grouped to stay within quota; the first upgraded sync backfills `YOUTUBE_INITIAL_LOOKBACK_DAYS=7`. Cardiff sentiment runs locally, and results below `HF_CONFIDENCE_THRESHOLD=0.80` or with ambiguous target attribution go to Gemini. The default verifier is `gemini-3.5-flash-lite` and supports positive, negative, neutral, and mixed. Missing or invalid Gemini credentials leave verification-dependent records pending. `HF_TOKEN` is optional for the public model. See `MODEL-VALIDATION.md` for measured limitations.
