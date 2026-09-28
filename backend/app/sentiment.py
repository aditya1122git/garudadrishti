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
    sentiment: Literal['positive', 'negative', 'neutral']
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=300)


def preprocess(text):
    # Match the model card's social-text normalization without stripping Hindi.
    text = re.sub(r'https?://\S+', 'http', text)
    return re.sub(r'(?<!\w)@\w+', '@user', text)


def result_from_scores(labels, scores, truncated=False):
    labels = [str(label).lower() for label in labels]
    if len(labels) != 3 or set(labels) != {'negative', 'neutral', 'positive'}:
        raise ValueError('Model must expose named negative, neutral and positive labels')
    if len(scores) != 3 or any(not math.isfinite(s) or not 0 <= s <= 1 for s in scores):
        raise ValueError('Invalid model probabilities')
    if abs(sum(scores) - 1) > .001:
        raise ValueError('Model probabilities must sum to one')
    index = max(range(3), key=lambda i: scores[i])
    note = 'Overall text sentiment; not target-specific stance.'
    if scores[index] < .7:
        note += ' Low model confidence; review.'
    if truncated:
        note += ' Long post truncated; review full text.'
    return Result(sentiment=labels[index], confidence=scores[index], reason=note)


class Classifier:
    def __init__(self, settings=None):
        self.settings = settings or config()
        self._tokenizer = self._model = None
        # Thread lock remains held even if the awaiting coroutine is cancelled.
        # Loading and inference are serialized to bound memory and protect the cache.
        self._lock = threading.Lock()
        self.status = 'pending'
        self.error = None

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
                results.extend(result_from_scores(self._labels, row, cut)
                               for row, cut in zip(scores, truncated, strict=True))
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
            self.status = 'live'
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
    return {'provider': 'Hugging Face (local)', 'status': 'demo' if c.seed_mock_data else engine.status,
            'model': c.hf_model, 'revision': c.hf_revision,
            'error': None if c.seed_mock_data else engine.error}
