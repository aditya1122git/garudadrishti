# JanNetra model and live YouTube verification

Checked 2026-10-01 on the local CPU runtime. These are functional checks and small, authored sanity cases, not a representative held-out accuracy benchmark.

## Working behavior

- YouTube official search plus videos.list: video title only. No description, comments, or commentThreads content is classified or stored in the active scope.
- Cardiff multilingual sentiment and `ashish5193/sarcasm_model` run locally. Language, target entities, opponent context and Hindi/Hinglish sarcasm cues are combined into target-wise sentiment.
- Only combined confidence below 0.60 goes to Groq. The exact 0.60 boundary is covered by an automated test.
- Groq missing/failing: sub-60% items retain sentiment=null, show Awaiting Groq, and are excluded from classified counts. Local results at or above 60% save immediately.
- Final results retain the model used, HF confidence and review flag. Low-confidence Groq output is flagged for review.
- Groq JSON validates count and IDs in order, retries malformed batches individually, retries transient transport/rate errors with backoff and limits concurrency.

## Actual model checks

Model: `cardiffnlp/twitter-xlm-roberta-base-sentiment@f2f1202b1bdeb07342385c3f807f9c07cd8f5cf8`.

Basic English/Hindi/Hinglish cases: 8/9 matched authored expectations. Warm inference for 9 short texts: 0.386 seconds (host-specific).

The table below records the earlier Cardiff-only 75% gate benchmark for comparison; it is not a benchmark of the new combined pipeline. Political cases: 11/12 HF labels matched authored expectations. Of 6 results accepted at >=75%, 5 matched. Six remaining cases required Groq. This is too small and selected to estimate production accuracy.

| Input | Expected target sentiment | HF prediction | Confidence | Route |
|---|---|---|---:|---|
| Prashant Kishore has an excellent plan for Bihar. I support Jan Suraj. | positive | positive | 70.5% | Groq pending |
| Jan Suraj Party has failed us. Prashant Kishore makes empty promises. | negative | negative | 84.2% | HF accepted |
| Prashant Kishore addressed a meeting in Patna on Tuesday. | neutral | neutral | 62.4% | Groq pending |
| प्रशांत किशोर का काम शानदार है। मैं जन सुराज का समर्थन करता हूँ। | positive | positive | 81.1% | HF accepted |
| जन सुराज की नीतियाँ बेकार हैं। प्रशांत किशोर ने हमें निराश किया। | negative | negative | 95.0% | HF accepted |
| प्रशांत किशोर ने मंगलवार को पटना में प्रेस कॉन्फ्रेंस की। | neutral | neutral | 76.8% | HF accepted |
| Prashant Kishore ka plan bahut achha hai, Jan Suraj ko mera support hai. | positive | positive | 60.7% | Groq pending |
| Jan Suraj ne nirash kiya. PK ke vaade khokhle hain, kaam bilkul bekar hai. | negative | negative | 38.3% | Groq pending |
| Prashant Kishore ki press conference kal Patna mein hogi. | neutral | neutral | 49.9% | Groq pending |
| Prashant Kishore said the government has failed and its policies are terrible. | neutral | negative | 90.1% | HF accepted |
| वाह प्रशांत किशोर! फिर एक और खोखला वादा। जनता को बेवकूफ समझ रखा है? | negative | negative | 80.0% | HF accepted |
| Jan Suraj Party announces candidate list for the upcoming election. | neutral | neutral | 65.1% | Groq pending |

**Corrected target-attribution case:** Schema v4 runs language detection, entity detection, Cardiff sentiment and local sarcasm analysis before the Groq gate. For `BJP à¤•à¥‹ à¤µà¥‹à¤Ÿ à¤•à¥€à¤œà¤¿à¤ à¤›à¤¤ à¤¸à¥‡ à¤ªà¤¾à¤¨à¥€ à¤†à¤à¤—à¤¾ #prashantkishor #jansuraj`, Cardiff returned neutral at 0.354 and the sarcasm model itself returned only 0.002, consistent with its documented generalization limitation. The combined political-sarcasm cue and target context returned positive at 0.95 locally, with no Groq call. Broad political accuracy is still not established.

HF truncates inputs to configured HF_MAX_LENGTH tokens (256 by default) and flags truncation in the reason. Groq fallback receives only the title. Hinglish, sarcasm, clickbait and ambiguous short titles need representative human review.

## Live YouTube and application

- The upgraded 7-day, grouped general + short-duration search found 105 current monitored videos (up from 30 under the previous combined-query strategy). The first feed page contained 15 records discovered by the official short-duration search. After rate-aware retries, all 105 were classified and 0 remained pending. Live titles have no human gold labels, so these are coverage and routing checks rather than accuracy measurements.
- A controlled live Groq check classified `Prashant Kishore has good ideas but poor execution` as `mixed` with 0.90 confidence. Today's real titles produced zero mixed results; the system does not manufacture a mixed share when both stances are absent.
- Active title-only records contain no description field and no newline/description content. Legacy records outside the active scope remain excluded.
- Cached HF inference also passed with HF_HUB_OFFLINE=1 in a fresh process (exit 0).
- MongoDB connection and actual daily aggregation succeeded.
- HTTP checks: frontend, proxy, health, login, protected-route rejection, overview, settings, video-only feed, CSV export and PDF export passed.
- Automated backend suite: 28 passed, 1 optional standalone real-Mongo test skipped. Frontend production build passed. Dependency consistency check passed.
- A browser automation connection was unavailable, so this turn did not visually verify the rendered dashboard.

## Running locally

- Updated dashboard: http://127.0.0.1:5174/
- Updated API: http://127.0.0.1:8001/api/health
- Local .env has live mode and ENABLED_PLATFORMS=youtube. No other platform is connected by this instance.
- An older process occupies port 8000 and Windows denied stopping it. Stop that old server in its original terminal before using a single scheduled instance against the database. The updated preview points at 8001.
- Legacy YouTube records are retained but excluded unless they have the title-only scope. Matching video records are upgraded to title-only once.

## Groq verification

The configured Groq key is valid. The previously configured `llama-3.3-70b-versatile` returned `model_not_found`; the account's available multilingual `qwen/qwen3.8-27b` model passed live JSON validation and processed the pending title queue. The API key is stored only in the private excluded `.env`.

Only one scheduler should run against this database. Alerts/email/webhook delivery were not tested or sent. Docker/cloud deployment was not tested in this turn.
