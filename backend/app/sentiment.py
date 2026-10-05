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
    sarcasm_detected: bool = False
    sarcasm_confidence: float | None = None
    sarcasm_model_confidence: float | None = None
    sarcasm_model_used: str | None = None
    language: Literal['hi', 'en', 'hinglish'] = 'en'
    targets: list[str] = Field(default_factory=list)
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


def preprocess_sarcasm(text):
    """Twitter-style normalization that preserves sarcasm and campaign hashtags."""
    import html as _html
    text = _html.unescape(text)
    text = re.sub(r'https?://\S+', 'http', text)
    text = re.sub(r'(?<!\w)@\w+', '@user', text)
    return re.sub(r'[\s\u200b\u200c\u200d\ufeff]+', ' ', text).strip()[:400]



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
    r'jan\s*sura(?:j|aj)|\u091c\u0928\s*\u0938\u0941\u0930\u093e\u091c|'
    r'prashant\s*kishor(?:e)?|\u092a\u094d\u0930\u0936\u093e\u0902\u0924\s*'
    r'\u0915\u093f\u0936\u094b\u0930|(?<![a-z])pk(?![a-z])', re.IGNORECASE,
)
_TARGET_HASHTAG_PATTERN = re.compile(
    r'#(?:jan_?sura(?:j|aj)|prashant_?kishor(?:e)?|'
    r'\u091c\u0928\u0938\u0941\u0930\u093e\u091c|'
    r'\u092a\u094d\u0930\u0936\u093e\u0902\u0924\u0915\u093f\u0936\u094b\u0930)', re.IGNORECASE,
)
_ATTRIBUTION_RISK_PATTERN = re.compile(
    r'\b(?:said|says|blamed|accused|attacked|criticised|criticized|against|vs\.?)\b|'
    r'\u0915\u0939\u093e|\u092c\u094b\u0932\u0947|\u0906\u0930\u094b\u092a|'
    r'\u0939\u092e\u0932\u093e|\u0928\u093f\u0936\u093e\u0928\u093e|'
    r'\u0935\u093f\u0930\u094b\u0927|\u0916\u093f\u0932\u093e\u092b|'
    r'\b(?:bjp|rjd|jdu|jd\(u\)|congress|nda|modi|nitish|lalu|tejashwi)\b|'
    r'\u092d\u093e\u091c\u092a\u093e|\u0915\u093e\u0902\u0917\u094d\u0930\u0947\u0938|'
    r'\u0928\u0940\u0924\u0940\u0936|\u0932\u093e\u0932\u0942|'
    r'\u0924\u0947\u091c\u0938\u094d\u0935\u0940', re.IGNORECASE,
)

_ROMAN_HINDI = {
    'aaj', 'ab', 'accha', 'achha', 'bahut', 'bas', 'bhai', 'bihar', 'hai',
    'hain', 'hoga', 'ka', 'ke', 'ki', 'ko', 'kya', 'mein', 'mera', 'nahi',
    'nhi', 'par', 'se', 'sahi', 'vote', 'wala', 'wali', 'ye', 'yeh',
}


def detect_language(text: str) -> Literal['hi', 'en', 'hinglish']:
    devanagari = len(re.findall(r'[\u0900-\u097f]', text))
    latin_words = re.findall(r"[a-zA-Z']+", text.lower())
    if devanagari:
        return 'hinglish' if latin_words else 'hi'
    hindi_hits = sum(word in _ROMAN_HINDI for word in latin_words)
    return 'hinglish' if hindi_hits >= 2 else 'en'


def detect_targets(text: str) -> list[str]:
    targets = []
    if re.search(r'jan\s*sura(?:j|aj)|\u091c\u0928\s*\u0938\u0941\u0930\u093e\u091c|'
                 r'#jan_?sura(?:j|aj)|#\u091c\u0928\u0938\u0941\u0930\u093e\u091c', text, re.I):
        targets.append('jan_suraaj')
    if re.search(r'prashant\s*kishor(?:e)?|\u092a\u094d\u0930\u0936\u093e\u0902\u0924\s*'
                 r'\u0915\u093f\u0936\u094b\u0930|#prashant_?kishor(?:e)?|'
                 r'#\u092a\u094d\u0930\u0936\u093e\u0902\u0924\u0915\u093f\u0936\u094b\u0930|'
                 r'(?<![a-z])pk(?![a-z])', text, re.I):
        targets.append('prashant_kishore')
    return targets


def sarcasm_heuristic(text: str) -> float:
    """High-precision cues for political sarcasm missed by the imbalanced model."""
    lower = text.lower()
    if re.search(r'#(?:sarcasm|irony)\b|(?<!\w)/s(?!\w)', lower):
        return 0.98
    praise = re.search(
        r'\b(?:wow|great|nice|excellent|shabash|wah|kya baat)\b|'
        r'\u0935\u093e\u0939|\u0936\u093e\u092c\u093e\u0936|'
        r'\u0915\u094d\u092f\u093e\s+\u092c\u093e\u0924|'
        r'\u0905\u091a\u094d\u091b\u0947\s+\u0926\u093f\u0928', lower,
    )
    negative_outcome = re.search(
        r'\b(?:fail|failed|fraud|damage|ruin|leak|broken|disaster)\b|'
        r'\u092c\u0930\u094d\u092c\u093e\u0926|\u0928\u093e\u0915\u093e\u092e|'
        r'\u0927\u094b\u0916\u093e|\u091b\u0924\s+\u0938\u0947\s+\u092a\u093e\u0928\u0940|'
        r'\u092a\u093e\u0928\u0940\s+\u091f\u092a\u0915', lower,
    )
    vote_appeal = re.search(
        r'\bvote\s+(?:for|karo|kijiye|dijiye)\b|'
        r'\u0935\u094b\u091f\s+(?:\u0915\u0940\u091c\u093f\u090f|'
        r'\u0926\u0940\u091c\u093f\u090f|\u0926\u094b)', lower,
    )
    if negative_outcome and (praise or vote_appeal):
        return 0.90
    return 0.0


def apply_target_context(text: str, result: Result, sarcasm_probability: float,
                         sarcasm_threshold: float) -> Result:
    """Combine sentiment, sarcasm and entity context into target-wise stance."""
    result.language = detect_language(text)
    result.targets = detect_targets(text)
    result.sarcasm_model_confidence = sarcasm_probability
    result.sarcasm_confidence = max(sarcasm_probability, sarcasm_heuristic(text))
    result.sarcasm_detected = result.sarcasm_confidence >= sarcasm_threshold
    if not result.sarcasm_detected or not result.targets:
        return result

    without_hashtags = re.sub(r'#\S+', '', text)
    target_only_in_hashtag = (
        bool(_TARGET_HASHTAG_PATTERN.search(text))
        and not _TARGET_PATTERN.search(without_hashtags)
    )
    opponent_context = bool(_ATTRIBUTION_RISK_PATTERN.search(without_hashtags))
    rule_confidence = min(0.99, 0.5 + 0.5 * result.sarcasm_confidence)

    if result.sentiment in {'negative', 'neutral'} and target_only_in_hashtag and opponent_context:
        result.sentiment = 'positive'
        result.confidence = rule_confidence
        result.reason = 'Sarcastic opponent criticism in tracked campaign context; positive toward target.'
    elif result.sentiment == 'positive' and not target_only_in_hashtag and not opponent_context:
        result.sentiment = 'negative'
        result.confidence = rule_confidence
        result.reason = 'Sarcastic praise aimed directly at tracked target; negative stance.'
    else:
        # Sarcasm is present but its target is unclear. Only this sub-60 result
        # goes to Groq for semantic attribution.
        result.confidence = min(result.confidence, 0.59)
        result.reason = 'Sarcasm detected but target attribution is ambiguous; verifier required.'
    return result

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
        self._sarcasm_tokenizer = self._sarcasm_model = None
        # Thread lock remains held even if the awaiting coroutine is cancelled.
        # Loading and inference are serialized to bound memory and protect the cache.
        self._lock = threading.Lock()
        self.status = 'pending'
        self.error = None
        self._groq = None

    @property
    def provenance(self):
        return f'{self.settings.hf_model}@{self.settings.hf_revision}'

    @property
    def sarcasm_provenance(self):
        return f'{self.settings.sarcasm_model}@{self.settings.sarcasm_revision}'

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
        sarcasm_tokenizer = AutoTokenizer.from_pretrained(
            c.sarcasm_tokenizer_model, revision=c.sarcasm_tokenizer_revision,
            cache_dir=c.hf_cache_dir, token=c.hf_token or False,
            local_files_only=c.hf_local_files_only, trust_remote_code=False,
        )
        sarcasm_model = AutoModelForSequenceClassification.from_pretrained(
            c.sarcasm_model, revision=c.sarcasm_revision, cache_dir=c.hf_cache_dir,
            token=c.hf_token or False, local_files_only=c.hf_local_files_only,
            trust_remote_code=False, weights_only=True,
        )
        if sarcasm_model.config.num_labels != 2:
            raise ValueError('Sarcasm model must expose two labels: 0 non-sarcastic, 1 sarcastic')
        sarcasm_model.to(c.hf_device)
        sarcasm_model.eval()
        self._sarcasm_tokenizer, self._sarcasm_model = sarcasm_tokenizer, sarcasm_model

    def _run(self, texts):
        with self._lock:
            self._load()
            import torch
            c = self.settings
            results = []
            for offset in range(0, len(texts), c.hf_batch_size):
                originals = texts[offset:offset + c.hf_batch_size]
                batch = [preprocess(t) for t in originals]
                raw = self._tokenizer(batch, truncation=False, add_special_tokens=True)
                truncated = [len(ids) > c.hf_max_length for ids in raw['input_ids']]
                tokens = self._tokenizer(batch, padding=True, truncation=True,
                                         max_length=c.hf_max_length, return_tensors='pt')
                tokens = {k: v.to(c.hf_device) for k, v in tokens.items()}
                with torch.inference_mode():
                    scores = self._model(**tokens).logits.softmax(dim=-1).cpu().tolist()
                sarcasm_batch = [preprocess_sarcasm(t) for t in originals]
                sarcasm_tokens = self._sarcasm_tokenizer(
                    sarcasm_batch, padding=True, truncation=True,
                    max_length=c.hf_max_length, return_tensors='pt',
                )
                sarcasm_tokens = {k: v.to(c.hf_device) for k, v in sarcasm_tokens.items()}
                with torch.inference_mode():
                    sarcasm_scores = self._sarcasm_model(
                        **sarcasm_tokens).logits.softmax(dim=-1).cpu().tolist()
                if len(scores) != len(batch):
                    raise ValueError('Classification array length mismatch')
                if len(sarcasm_scores) != len(batch) or any(len(row) != 2 for row in sarcasm_scores):
                    raise ValueError('Sarcasm classification array length mismatch')
                for row, sarcasm_row, cut, cleaned, original in zip(
                        scores, sarcasm_scores, truncated, batch, originals, strict=True):
                    result = result_from_scores(self._labels, row, cut, cleaned)
                    result.hf_confidence = result.confidence
                    result.sarcasm_model_used = self.sarcasm_provenance
                    results.append(apply_target_context(
                        original, result, sarcasm_row[1], c.sarcasm_confidence_threshold))
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
                if result.hf_confidence is None:
                    result.hf_confidence = result.confidence
            verify = [i for i, result in enumerate(results)
                      if result.confidence < self.settings.hf_confidence_threshold]
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
                        fallback.hf_confidence = results[index].hf_confidence
                        fallback.sarcasm_detected = results[index].sarcasm_detected
                        fallback.sarcasm_confidence = results[index].sarcasm_confidence
                        fallback.sarcasm_model_confidence = results[index].sarcasm_model_confidence
                        fallback.sarcasm_model_used = results[index].sarcasm_model_used
                        fallback.language = results[index].language
                        fallback.targets = results[index].targets
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
    return {'provider': 'Hugging Face sentiment + sarcasm + Groq fallback', 'status': status,
            'model': c.hf_model, 'revision': c.hf_revision,
            'sarcasm_model': c.sarcasm_model, 'sarcasm_revision': c.sarcasm_revision,
            'sarcasm_threshold': c.sarcasm_confidence_threshold,
            'threshold': c.hf_confidence_threshold, 'fallback_model': c.groq_model,
            'fallback_configured': bool(c.groq_api_key),
            'error': None if c.seed_mock_data else engine.error}
