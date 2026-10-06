# Verification record

Built and checked on 28 September 2026 using Python 3.12 and Node 24 on Windows.

## Completed

- Python tests after the Hugging Face migration: **23 passed**. One optional real-Mongo integration test skipped.
- TypeScript type checking and Vite production build: passed.
- Earlier Python installed-dependency audit (`pip-audit`) found no known vulnerabilities before the Hugging Face migration. The added ML dependencies require a fresh audit after installation; this earlier result is not a security assessment of the updated ML runtime.
- Frontend production-dependency audit (`npm audit --omit=dev`): **0 vulnerabilities**.
- Running local API + built React frontend with the explicit disposable demo database.
- Approximately 25,000–27,000 synthetic posts across 30 reporting days; today's fixture has 1,650 classified posts. Fixtures are date-relative and generated deterministically at startup; daily sentiment distribution may vary with startup time because timestamps use the current day's elapsed seconds.
- Browser verification: demo login; overview; active-alert evidence with five posts and platform breakdown; Facebook's disconnected/excluded state; settings and disabled real-credential controls.
- Responsive browser check at 390 × 844: mobile navigation works; the page does not overflow horizontally. Platform tabs intentionally scroll within their own row.
- API checks: role restrictions, unauthorized reads, sorted/filtered search, PDF and CSV reports, correct daily arithmetic and source exclusion.
- Browser autofill protection added to webhook/API-key fields; disabled webhook channels do not submit a stray autofilled URL.

- UI migration: Bootstrap CSS replaces Tailwind; Font Awesome replaces Lucide and text platform symbols. Google Fonts Poppins verified loaded in the browser. Login, overview and export dialog verified after migration; mobile width check showed no page-level horizontal overflow.

## Not yet verified against live infrastructure

- Docker/Compose startup and real MongoDB `$dateTrunc` execution: Docker and MongoDB are not installed on this build machine. An optional `tests/test_mongo.py` test checks actual MongoDB timezone aggregation and uniqueness when `TEST_MONGODB_URI` is set.
- YouTube live search/full-video ingestion verified on 2026-10-01; comments excluded. X and successful Meta ingestion remain unverified. See MODEL-VALIDATION.md.
- Actual Hugging Face CPU inference and live YouTube text evaluation completed; see MODEL-VALIDATION.md for measured errors. The current Gemini below-80% target verifier has simulated-provider coverage; live verification requires `GEMINI_API_KEY`.
- SMTP/SendGrid delivery and external webhooks: deliberately disabled in demo. Provider acceptance, delivery and receiver deduplication require an integration test before live use.
- Commercial listening providers: normalized connector contract is implemented; a vendor-specific licensed adapter must be supplied.
- Load testing, backup restore testing, penetration testing, and cloud deployment are not completed by the local demo. The README documents single-scheduler limits and operational requirements.

## Reproduce

```sh
cd backend
python -m pytest -q
```

For the optional Mongo test, set `TEST_MONGODB_URI` to a test MongoDB 7+ instance. It creates and removes only a uniquely named `test_jannetra_<uuid>` database. The default test suite sets demo flags for all other checks.

```sh
cd frontend
npm ci
npm run build
npm audit --omit=dev
```

The Windows workspace sandbox prevented Vite's development dependency optimizer from traversing parent directories. The local handoff therefore serves the successfully built production bundle using `npm run preview -- --port 5173`; this still proxies `/api` to port 8000. Docker uses the Nginx production server. The source remains usable with the normal Vite development command outside that sandbox.

## 2026-10-01 hybrid verification

28 backend tests passed, 1 optional real-Mongo test skipped; production frontend build and dependency consistency check passed. Actual live Mongo aggregation, YouTube-only ingestion, login/feed/exports checked. See MODEL-VALIDATION.md for the accuracy limitations and current local ports.

The title-only update was rechecked: descriptions and comments are excluded. The older provider run is superseded by the current Gemini verifier and must be rechecked after its key is configured.
