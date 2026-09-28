# What is needed to connect live data

The local `.env` is created in this project directory. Demo mode stays enabled until live infrastructure is configured. Do not paste API keys into chat; enter them in `.env` or the live application's admin settings.

## Required for live deployment

1. **Hosting choice:** local PC, VPS, or cloud, plus available RAM and CPU/GPU. Plan initially for roughly 4 GB API memory and benchmark; the multilingual weights download is around 1.1 GB, excluding runtime dependencies. Small/free containers may not fit.
2. **Database:** authenticated MongoDB URI (Atlas or self-hosted). Docker's bundled MongoDB works for the local demo without a separate account.
3. **Administrator:** preferred email and a unique live password. The current demo login is public demo information, not a production credential. JWT and encryption keys have already been generated in the local `.env`; preserve them.
4. **At least one source:** YouTube Data API v3 key, or an X bearer token with public-search entitlement. X search may require paid access.

## Optional sources and notifications

- **Facebook/Instagram:** owned/managed Page or professional account IDs plus a Graph API token with the required permissions, OR a licensed social-listening provider and its adapter details. Unconfigured Meta sources remain excluded. No scraping or file import.
- **Email alerts:** recipient email and either SMTP host/port/username/password/from-address or a SendGrid key and verified sender. Enable the channel in Settings.
- **Webhook alerts:** destination URL and its exact hostname for `OUTBOUND_ALLOWED_HOSTS`; enable it in Settings. Provider-specific Slack/Telegram formatting may require an adapter.
- **Keywords/threshold:** confirm tracked terms and the default threshold of more than 500 negative posts per reporting day, Asia/Kolkata.
- **Validation examples:** a small anonymized set of Hindi/Hinglish/English texts with analyst-agreed labels helps evaluate domain quality. This is a development evaluation exercise; the app has no manual import feature.

## Hugging Face credentials

The default public multilingual model runs locally and needs **no Hugging Face API key**. `HF_TOKEN` is optional for authenticated model downloads. `HF_MODEL`, the pinned `HF_REVISION`, CPU defaults, batch size and cache settings are already set. Post text is not sent to Hugging Face. Network access is needed for the initial download; afterwards cached inference can run offline.

## Switching to live

Set `SEED_MOCK_DATA=false` and `DEMO_IN_MEMORY=false`, configure the live database/admin/source credentials, then restart. Test the model with `python -m app.check_classifier` from `backend`, trigger Refresh, and inspect source/classifier health before enabling external notifications. For local Python execution use `mongodb://127.0.0.1:27017` (with authentication for live); the default `mongodb://mongo:27017` hostname is for Docker Compose.
