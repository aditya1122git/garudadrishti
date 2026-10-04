"""Local Hugging Face inference. No post text leaves the application server."""
import asyncio
import math
import re
import threading
from functools import lru_cache
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .config import config


class Result(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sentiment: Literal['positive', 'negative', 'neutral', 'mixed']
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=300)
    model_used: str = ''
    hf_confidence: float | None = None
    pending: bool = False
    review_required: bool = False


def preprocess(text):
    """Improved preprocessing for political Hindi social-media text.

    Strips hashtags (major noise: #viral #bankipur confuse political Hindi),
    decodes HTML entities (&quot; etc), and normalizes short social text.
    """
    import html as _html
    # Decode HTML entities (&quot; -> ", &amp; -> &, etc.)
    text = _html.unescape(text)
    # Replace URLs per model card
    text = re.sub(r'https?://\S+', 'http', text)
    # Anonymise @mentions per model card
    text = re.sub(r'(?<!\w)@\w+', '@user', text)
    # Strip hashtags entirely -- #word is keyword noise, not sentiment signal
    text = re.sub(r'#\S+', '', text)
    # Normalise whitespace (including zero-width Unicode chars)
    text = re.sub(r'[\s\u200b\u200c\u200d\ufeff]+', ' ', text).strip()
    # Deduplicate repeated title fragments separated by common punctuation.
    segments = [s.strip() for s in re.split(r'[\n|!।]+', text) if s.strip()]
    seen_segs: set = set()
    unique = []
    for seg in segments:
        key = re.sub(r'\s+', '', seg.lower())
        if key and key not in seen_segs:
            seen_segs.add(key)
            unique.append(seg)
    text = ' '.join(unique)
    # Cap at 400 chars -- enough context, avoids token truncation noise
    return text[:400]



# ---------------------------------------------------------------------------
# Political-Hindi context override
# The XLM-RoBERTa model was trained on general Twitter sentiment.
# It misreads political victory language (भारी हैं = dominant/winning) as
# negative and praise phrases as neutral.  These lightweight regex rules
# correct low-confidence predictions where the model is likely wrong.
# Rules fire ONLY when model confidence < 0.65 to avoid overriding clear signals.
# ---------------------------------------------------------------------------
_POSITIVE_SIGNALS = [
    # Political dominance / winning
    r'भारी\s+हैं', r'भारी\s+पड़', r'जीत', r'जीते', r'जीता', r'विजय',
    r'तारीफ', r'सराहना', r'समर्थन', r'बधाई', r'शानदार', r'बेहतरीन',
    r'अच्छ', r'achh', r'shukriy', r'badhiya', r'great', r'excellent',
    r'proud', r'support', r'well done', r'congratul',
    r'केंद्रीय मंत्री.*तारीफ', r'मंत्री.*प्रशंसा',
    r'सटीक\s+बात',  # "sahi/accurate point" = positive
]
_NEGATIVE_SIGNALS = [
    r'fraud', r'धोखा', r'बर्बाद', r'शर्म', r'जंगलराज', r'बेकार',
    r'नाकाम', r'झूठ', r'proxy', r'corrupt', r'failure', r'flop',
    r'निराश', r'गद्दार', r'विरोध.*तीखा', r'खतरनाक',
]

# HF predicts the overall emotional tone, while JanNetra needs stance toward
# the tracked entities. These patterns identify titles where a high-confidence
# general-sentiment label still needs target attribution by the Groq verifier.
_TARGET_PATTERN = re.compile(
    r'jan\s*sura(?:j|aj)|à¤œà¤¨\s*à¤¸à¥à¤°à¤¾à¤œ|prashant\s*kishor(?:e)?|'
    r'à¤ªà¥à¤°à¤¶à¤¾à¤‚à¤¤\s*à¤•à¤¿à¤¶à¥‹à¤°|(?<![a-z])pk(?![a-z])', re.IGNORECASE,
)
_TARGET_HASHTAG_PATTERN = re.compile(
    r'#(?:jan_?sura(?:j|aj)|prashant_?kishor(?:e)?|à¤œà¤¨à¤¸à¥à¤°à¤¾à¤œ|à¤ªà¥à¤°à¤¶à¤¾à¤‚à¤¤à¤•à¤¿à¤¶à¥‹à¤°)', re.IGNORECASE,
)
_ATTRIBUTION_RISK_PATTERN = re.compile(
    r'\b(?:said|says|blamed|accused|attacked|criticised|criticized|against|vs\.?)\b|'
    r'à¤•à¤¹à¤¾|à¤¬à¥‹à¤²à¥‡|à¤†à¤°à¥‹à¤ª|à¤¹à¤®à¤²à¤¾|à¤¨à¤¿à¤¶à¤¾à¤¨à¤¾|à¤µà¤¿à¤°à¥‹à¤§|à¤–à¤¿à¤²à¤¾à¤«|'
    r'\b(?:bjp|rjd|jdu|jd\(u\)|congress|nda|modi|nitish|lalu|tejashwi)\b|'
    r'à¤­à¤¾à¤œà¤ªà¤¾|à¤•à¤¾à¤‚à¤—à¥à¤°à¥‡à¤¸|à¤¨à¥€à¤¤à¥€à¤¶|à¤²à¤¾à¤²à¥‚|à¤¤à¥‡à¤œà¤¸à¥à¤µà¥€', re.IGNORECASE,
)


def needs_target_verification(text: str, result: Result) -> bool:
    """Detect target-attribution risk that confidence cannot measure."""
    if result.sentiment == 'neutral' or not _TARGET_PATTERN.search(text):
        return False
    without_hashtags = re.sub(r'#\S+', '', text)
    target_only_in_hashtag = (
        bool(_TARGET_HASHTAG_PATTERN.search(text))
        and not _TARGET_PATTERN.search(without_hashtags)
    )
    return target_only_in_hashtag or bool(_ATTRIBUTION_RISK_PATTERN.search(without_hashtags))

def _political_override(text_clean, label, confidence):
    """Return corrected (label, confidence, note) for low-confidence predictions."""
    if confidence >= 0.65:
        return label, confidence, ''
    text_lower = text_clean.lower()
    pos_hit = any(re.search(p, text_lower) for p in _POSITIVE_SIGNALS)
    neg_hit = any(re.search(p, text_lower) for p in _NEGATIVE_SIGNALS)
    if pos_hit and not neg_hit and label != 'positive':
        return 'positive', max(confidence, 0.58), ' Corrected by political-Hindi positive signal.'
    if neg_hit and not pos_hit and label != 'negative':
        return 'negative', max(confidence, 0.58), ' Corrected by political-Hindi negative signal.'
    return label, confidence, ''

def result_from_scores(labels, scores, truncated=False, raw_text=''):
    labels = [str(label).lower() for label in labels]
    if len(labels) != 3 or set(labels) != {'negative', 'neutral', 'positive'}:
        raise ValueError('Model must expose named negative, neutral and positive labels')
    if len(scores) != 3 or any(not math.isfinite(s) or not 0 <= s <= 1 for s in scores):
        raise ValueError('Invalid model probabilities')
    if abs(sum(scores) - 1) > .001:
        raise ValueError('Model probabilities must sum to one')
    index = max(range(3), key=lambda i: scores[i])
    label, confidence = labels[index], scores[index]
    # Apply political-Hindi context correction for low-confidence predictions
    if raw_text:
        label, confidence, override_note = _political_override(raw_text, label, confidence)
    else:
        override_note = ''
    note = 'Overall text sentiment; not target-specific stance.'
    if confidence < .7:
        note += ' Low model confidence; review.'
    if truncated:
        note += ' Long post truncated; review full text.'
    note += override_note
    return Result(sentiment=label, confidence=confidence, reason=note[:300])


class Classifier:
    def __init__(self, settings=None):
        self.settings = settings or config()
        self._tokenizer = self._model = None
        # Thread lock remains held even if the awaiting coroutine is cancelled.
        # Loading and inference are serialized to bound memory and protect the cache.
        self._lock = threading.Lock()
        self.status = 'pending'
        self.error = None
        self._groq = None

    @property
    def provenance(self):
        return f'{self.settings.hf_model}@{self.settings.hf_revision}'

    def _load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        c = self.settings
        torch.set_num_threads(c.hf_cpu_threads)
        options = dict(revision=c.hf_revision, cache_dir=c.hf_cache_dir,
                       token=c.hf_token or False, local_files_only=c.hf_local_files_only,
                       trust_remote_code=False)
        tokenizer = AutoTokenizer.from_pretrained(c.hf_model, **options)
        # The official checkpoint is .bin; PyTorch's restricted weights-only loader
        # is mandatory. Do not execute repository code or unrestricted pickle loads.
        model = AutoModelForSequenceClassification.from_pretrained(c.hf_model, weights_only=True, **options)
        labels = [model.config.id2label[i] for i in range(model.config.num_labels)]
        result_from_scores(labels, [1 / 3] * 3)
        model.to(c.hf_device)
        model.eval()
        self._labels = labels
        self._tokenizer, self._model = tokenizer, model

    def _run(self, texts):
        with self._lock:
            self._load()
            import torch
            c = self.settings
            results = []
            for offset in range(0, len(texts), c.hf_batch_size):
                batch = [preprocess(t) for t in texts[offset:offset + c.hf_batch_size]]
                raw = self._tokenizer(batch, truncation=False, add_special_tokens=True)
                truncated = [len(ids) > c.hf_max_length for ids in raw['input_ids']]
                tokens = self._tokenizer(batch, padding=True, truncation=True,
                                         max_length=c.hf_max_length, return_tensors='pt')
                tokens = {k: v.to(c.hf_device) for k, v in tokens.items()}
                with torch.inference_mode():
                    scores = self._model(**tokens).logits.softmax(dim=-1).cpu().tolist()
                if len(scores) != len(batch):
                    raise ValueError('Classification array length mismatch')
                results.extend(result_from_scores(self._labels, row, cut, bt)
                               for row, cut, bt in zip(scores, truncated, batch, strict=True))
            return results

    async def classify(self, texts):
        if not texts:
            return []
        if any(not isinstance(t, str) or not t.strip() for t in texts):
            raise ValueError('Post text must be nonempty')
        self.status, self.error = 'loading', None
        try:
            results = await asyncio.to_thread(self._run, texts)
            if len(results) != len(texts):
                raise ValueError('Classification array length mismatch')
            results = [Result.model_validate(r) for r in results]
            for result in results:
                result.model_used = self.provenance
                result.hf_confidence = result.confidence
            verify = [i for i, result in enumerate(results)
                      if result.confidence < self.settings.hf_confidence_threshold
                      or needs_target_verification(texts[i], result)]
            if verify:
                from .groq_fallback import GroqFallback
                if self._groq is None:
                    self._groq = GroqFallback(self.settings)
                refined = await self._groq.classify([texts[i] for i in verify])
                for index, fallback in zip(verify, refined, strict=True):
                    if fallback is None:
                        results[index].pending = True
                        results[index].review_required = True
                    else:
                        fallback.model_used = 'groq/' + self.settings.groq_model
                        fallback.hf_confidence = results[index].confidence
                        fallback.review_required = fallback.confidence < self.settings.hf_confidence_threshold
                        results[index] = fallback
            self.status = 'partial' if any(r.pending for r in results) else 'live'
            self.error = ((getattr(self._groq, 'last_error', None) or
                           'Groq fallback unavailable; low-confidence posts remain pending.')
                          if self.status == 'partial' else None)
            return results
        except Exception:
            self.status = 'unavailable'
            self.error = 'Local model unavailable; check model cache, dependencies and memory. Posts remain pending.'
            raise


@lru_cache
def classifier():
    return Classifier()


def classifier_status():
    c = config()
    engine = classifier()
    status = 'demo' if c.seed_mock_data else ('ready' if engine.status == 'pending' else engine.status)
    return {'provider': 'Hugging Face + Groq fallback', 'status': status,
            'model': c.hf_model, 'revision': c.hf_revision,
            'threshold': c.hf_confidence_threshold, 'fallback_model': c.groq_model,
            'fallback_configured': bool(c.groq_api_key),
            'error': None if c.seed_mock_data else engine.error}
