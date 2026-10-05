from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe
from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

DEFAULT_APIFY_ACTORS = {
    'facebook': 'apify~facebook-search-scraper',
    'instagram': 'data-slayer~instagram-keyword-posts-scraper',
    'x': 'apidojo~tweet-scraper',
}


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=(Path(__file__).resolve().parents[2] / '.env', Path(__file__).resolve().parents[1] / '.env'), extra='ignore')
    mongodb_uri: str = 'mongodb://mongo:27017'
    mongodb_database: str = 'jannetra'
    seed_mock_data: bool = False
    demo_in_memory: bool = False
    jwt_secret: str = ''
    encryption_key: str = ''
    bootstrap_email: str = ''
    bootstrap_password: str = ''
    hf_model: str = 'cardiffnlp/twitter-xlm-roberta-base-sentiment'
    hf_revision: str = 'f2f1202b1bdeb07342385c3f807f9c07cd8f5cf8'
    hf_token: str = ''
    hf_cache_dir: str = '.cache/huggingface'
    hf_device: str = 'cpu'
    hf_batch_size: int = 16
    hf_max_length: int = 256
    hf_cpu_threads: int = 2
    hf_local_files_only: bool = False
    sarcasm_model: str = 'ashish5193/sarcasm_model'
    sarcasm_revision: str = '6e8df8df0e3ff4adf248a15f06057cd6b7b173b2'
    sarcasm_tokenizer_model: str = 'cardiffnlp/twitter-roberta-base-sentiment-latest'
    sarcasm_tokenizer_revision: str = '3216a57f2a0d9c45a2e6c20157c20c49fb4bf9c7'
    sarcasm_confidence_threshold: float = 0.65
    groq_api_key: str = ''
    groq_model: str = 'qwen/qwen3.8-27b'
    hf_confidence_threshold: float = 0.60
    groq_concurrency: int = 2
    enabled_platforms: str = 'facebook,instagram,x,youtube,news'
    apify_api_token: str = ''
    apify_facebook_actor_id: str = ''
    apify_instagram_actor_id: str = ''
    apify_x_actor_id: str = ''
    apify_facebook_input_json: str = ''
    apify_instagram_input_json: str = ''
    apify_x_input_json: str = ''
    apify_max_items: int = 50
    apify_run_timeout_seconds: int = 240
    youtube_api_key: str = ''
    youtube_initial_lookback_days: int = 7
    youtube_terms_per_query: int = 4
    telegram_bot_token: str = ''
    telegram_chat_id: str = ''
    allowed_origins: str = 'http://localhost:5173,http://localhost:8080'
    reporting_timezone: str = 'Asia/Kolkata'
    scheduler_enabled: bool = True
    automation_start_hour: int = 6
    automation_end_hour: int = 22
    youtube_sync_interval_minutes: int = 15
    apify_sync_interval_hours: int = 4

    @model_validator(mode='after')
    def secure_defaults(self):
        if self.demo_in_memory and not self.seed_mock_data:
            raise ValueError('DEMO_IN_MEMORY requires SEED_MOCK_DATA=true')
        if self.seed_mock_data:
            self.jwt_secret = self.jwt_secret or token_urlsafe(48)
            self.encryption_key = self.encryption_key or Fernet.generate_key().decode()
        if len(self.jwt_secret) < 32 or not self.encryption_key:
            raise ValueError('Set JWT_SECRET (32+ chars) and ENCRYPTION_KEY (Fernet)')
        self.bootstrap_email = self.bootstrap_email.strip().lower()
        if self.bootstrap_email or self.bootstrap_password:
            if '@' not in self.bootstrap_email:
                raise ValueError('BOOTSTRAP_EMAIL must be a valid administrator email')
            if len(self.bootstrap_password) < 14:
                raise ValueError('BOOTSTRAP_PASSWORD must contain at least 14 characters')
            if len(self.bootstrap_password.encode()) > 72:
                raise ValueError('BOOTSTRAP_PASSWORD must be at most 72 UTF-8 bytes')
        self.telegram_bot_token = self.telegram_bot_token.strip()
        self.telegram_chat_id = self.telegram_chat_id.strip()
        if bool(self.telegram_bot_token) != bool(self.telegram_chat_id):
            raise ValueError('Set both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or leave both empty')
        Fernet(self.encryption_key.encode())
        if not 1 <= self.hf_batch_size <= 32 or not 16 <= self.hf_max_length <= 512:
            raise ValueError('HF_BATCH_SIZE must be 1..32 and HF_MAX_LENGTH must be 16..512')
        if not 1 <= self.hf_cpu_threads <= 32:
            raise ValueError('HF_CPU_THREADS must be 1..32')
        if (not 0 <= self.hf_confidence_threshold <= 1
                or not 0 <= self.sarcasm_confidence_threshold <= 1
                or not 1 <= self.groq_concurrency <= 8):
            raise ValueError('Invalid classifier threshold/concurrency')
        if not 1 <= self.youtube_initial_lookback_days <= 30 or not 1 <= self.youtube_terms_per_query <= 5:
            raise ValueError('Invalid YouTube search coverage settings')
        if set(self.enabled_platforms.split(',')) - {'facebook', 'instagram', 'x', 'youtube', 'news'}:
            raise ValueError('Invalid ENABLED_PLATFORMS')
        if not 1 <= self.apify_max_items <= 1000 or not 30 <= self.apify_run_timeout_seconds <= 300:
            raise ValueError('Invalid Apify run limits')
        if (not 0 <= self.automation_start_hour < self.automation_end_hour <= 23
                or self.youtube_sync_interval_minutes != 15
                or self.apify_sync_interval_hours != 4
                or (self.automation_end_hour - self.automation_start_hour) % self.apify_sync_interval_hours):
            raise ValueError('Automation window must support 15-minute YouTube and 4-hour Apify schedules')
        # A single token is enough for the standard setup. Explicit environment
        # values remain available when an operator wants to swap an Actor.
        for platform, actor_id in DEFAULT_APIFY_ACTORS.items():
            field = f'apify_{platform}_actor_id'
            if not getattr(self, field).strip():
                setattr(self, field, actor_id)
        if self.hf_device not in ('cpu', 'cuda', 'mps'):
            raise ValueError('HF_DEVICE must be cpu, cuda, or mps')
        if not all(value.strip() for value in (
            self.hf_model, self.hf_revision, self.sarcasm_model,
            self.sarcasm_revision, self.sarcasm_tokenizer_model,
            self.sarcasm_tokenizer_revision,
        )):
            raise ValueError('Sentiment and sarcasm model names/revisions are required')
        return self


@lru_cache
def config():
    return Config()
