from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe
from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=(Path(__file__).resolve().parents[2] / '.env', Path(__file__).resolve().parents[1] / '.env'), extra='ignore')
    mongodb_uri: str = 'mongodb://mongo:27017'
    mongodb_database: str = 'jannetra'
    seed_mock_data: bool = False
    demo_in_memory: bool = False
    jwt_secret: str = ''
    encryption_key: str = ''
    bootstrap_email: str = 'admin@jannetra.local'
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
    youtube_api_key: str = ''
    x_bearer_token: str = ''
    meta_access_token: str = ''
    meta_facebook_page_id: str = ''
    meta_instagram_account_id: str = ''
    meta_graph_version: str = 'v23.0'
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    sendgrid_api_key: str = ''
    outbound_allowed_hosts: str = ''
    allowed_origins: str = 'http://localhost:5173,http://localhost:8080'
    reporting_timezone: str = 'Asia/Kolkata'
    scheduler_enabled: bool = True
    sync_interval_minutes: int = 15

    @model_validator(mode='after')
    def secure_defaults(self):
        if self.demo_in_memory and not self.seed_mock_data:
            raise ValueError('DEMO_IN_MEMORY requires SEED_MOCK_DATA=true')
        if self.seed_mock_data:
            self.jwt_secret = self.jwt_secret or token_urlsafe(48)
            self.encryption_key = self.encryption_key or Fernet.generate_key().decode()
            self.bootstrap_password = self.bootstrap_password or 'JanNetra-Demo-2026!'
        if len(self.jwt_secret) < 32 or not self.encryption_key or len(self.bootstrap_password) < 14:
            raise ValueError('Set JWT_SECRET (32+ chars), ENCRYPTION_KEY (Fernet), BOOTSTRAP_PASSWORD (14+ chars)')
        if len(self.bootstrap_password.encode()) > 72:
            raise ValueError('BOOTSTRAP_PASSWORD must be at most 72 UTF-8 bytes')
        self.bootstrap_email = self.bootstrap_email.strip().lower()
        Fernet(self.encryption_key.encode())
        if not 1 <= self.hf_batch_size <= 32 or not 16 <= self.hf_max_length <= 512:
            raise ValueError('HF_BATCH_SIZE must be 1..32 and HF_MAX_LENGTH must be 16..512')
        if not 1 <= self.hf_cpu_threads <= 32:
            raise ValueError('HF_CPU_THREADS must be 1..32')
        if self.hf_device not in ('cpu', 'cuda', 'mps'):
            raise ValueError('HF_DEVICE must be cpu, cuda, or mps')
        if not self.hf_model.strip() or not self.hf_revision.strip():
            raise ValueError('HF_MODEL and HF_REVISION are required')
        return self


@lru_cache
def config():
    return Config()
