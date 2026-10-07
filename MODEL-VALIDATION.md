# JanNetra model validation

## Current pipeline

- YouTube uses the video title only. Descriptions and comments are neither stored nor classified in the active scope.
- `cardiffnlp/twitter-xlm-roberta-base-sentiment` provides a fast local first pass for Hindi, English and Hinglish.
- An HF result below 80% is sent to Gemini. A result is also sent when campaign hashtags or quoted/opponent language make the sentiment target ambiguous, even if Cardiff's overall-tone probability is high.
- Gemini classifies stance specifically toward Samrat Choudhary, Bihar BJP, and the Bihar Government. Negative events involving crime, flood, firing, Bihar or an opponent remain neutral unless the title criticizes a tracked target. Gemini resolves sarcasm in the same target-aware decision.
- Missing or failing Gemini access leaves verification-dependent posts pending and excluded from totals. The next scheduled run retries them.
- Gemini responses use a strict JSON schema, validate IDs and array length, retry malformed batches per title, and retry transient rate/server failures with backoff.

## Why the standalone sarcasm model was removed

`ashish5193/sarcasm_model` was not retained. Its repository does not provide a usable tokenizer, the previous integration substituted an English Cardiff tokenizer, and the available project evidence did not establish accuracy on Hindi/Hinglish Bihar political titles. In an earlier measured campaign example it returned a sarcasm probability of only 0.002 for an explicit political joke. Loading it added a second transformer and could inject an unreliable signal into target attribution. Gemini now handles sarcasm together with speaker, opponent and tracked-target context.

## Known limitation and guardrail

Cardiff predicts overall text tone rather than entity-targeted stance. It can label headlines containing words such as crime, bullets or flood as negative even when a tracked entity only appears in a hashtag. Schema v5 caps such ambiguous results below the verifier gate so Gemini must decide who the language targets. Direct high-confidence criticism such as `बिहार सरकार ने जनता को निराश किया` can still be accepted locally.

The threshold is a routing rule, not a measured accuracy guarantee. Before treating alerts as ground truth, maintain a human-labeled Hindi/Hinglish evaluation set drawn from live titles and monitor precision for the negative class.

## Verification status

Automated tests cover the exact 80% boundary, target-only hashtag cases, direct target criticism, Gemini JSON shape and ordering, batch-to-single fallback, unavailable-provider behavior, and YouTube title-only ingestion. A live Gemini inference test still requires a configured `GEMINI_API_KEY`.
