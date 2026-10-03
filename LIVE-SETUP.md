# What is needed to connect live data

The local `.env` is created in this project directory. Live mode is the default. Do not paste API keys into chat; enter them in `.env` or the application's admin settings.

## Required for live deployment

1. **Hosting choice:** local PC, VPS, or cloud, plus available RAM and CPU/GPU. Plan initially for roughly 4 GB API memory and benchmark; the multilingual weights download is around 1.1 GB, excluding runtime dependencies. Small/free containers may not fit.
2. **Database:** authenticated MongoDB URI (Atlas or self-hosted).
3. **Administrator:** preferred email and a unique password. No default login is provided. JWT and encryption keys in the local `.env` must be preserved.
4. **At least one source:** YouTube Data API v3 key or an Apify API token. JanNetra supplies default Actors and inputs for Facebook, Instagram, X and News.

## Optional sources and notifications

- **Apify sources:** `APIFY_API_TOKEN` connects the four standard Actors automatically. Actor IDs and input templates in `.env` or Settings are optional advanced overrides. Apify Store Actors can incur per-result and compute charges; keep the item limit conservative.
- **Email alerts:** recipient email and either SMTP host/port/username/password/from-address or a SendGrid key and verified sender. Enable the channel in Settings.
- **Webhook alerts:** destination URL and its exact hostname for `OUTBOUND_ALLOWED_HOSTS`; enable it in Settings. Provider-specific Slack/Telegram formatting may require an adapter.
- **Keywords/threshold:** confirm tracked terms and the default threshold of more than 500 negative posts per reporting day, Asia/Kolkata.
- **Validation examples:** a small anonymized set of Hindi/Hinglish/English texts with analyst-agreed labels helps evaluate domain quality. This is a development evaluation exercise; the app has no manual import feature.

## Hugging Face credentials

The default public multilingual model runs locally and needs **no Hugging Face API key**. `HF_TOKEN` is optional for authenticated model downloads. `HF_MODEL`, the pinned `HF_REVISION`, CPU defaults, batch size and cache settings are already set. Post text is not sent to Hugging Face. Network access is needed for the initial download; afterwards cached inference can run offline.

## Switching to live

Configure the database, administrator and source credentials, then restart. Test the model with `python -m app.check_classifier` from `backend`, trigger Refresh, and inspect source/classifier health before enabling external notifications. For local Python execution use `mongodb://127.0.0.1:27017`; the default `mongodb://mongo:27017` hostname is for Docker Compose.

## YouTube-only hybrid update

`ENABLED_PLATFORMS=youtube` limits active ingestion to YouTube. Only video titles are classified; descriptions and comments are excluded. General and short-duration searches run across public channels, grouped to stay within quota; the first upgraded sync backfills `YOUTUBE_INITIAL_LOOKBACK_DAYS=7`. Configure `GROQ_API_KEY` in the private `.env` to enable fallback below `HF_CONFIDENCE_THRESHOLD=0.75`, then restart the API. The default current fallback is `qwen/qwen3.8-27b` and supports positive, negative, neutral, and mixed. Missing/invalid Groq credentials or model access leave those records pending, not silently finalized. `HF_TOKEN` is optional for the public model. See `MODEL-VALIDATION.md` for measured limitations.
