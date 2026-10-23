import math
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit


class ApplicationSettings:
    """Читает и проверяет настройки окружения без раскрытия секретов."""

    def __init__(self, environment: Mapping[str, str] | None = None):
        values = os.environ if environment is None else environment
        self.telegram_api_key = self._required(values, "TELEGRAM_API_KEY")
        self.postgres_dsn = self._required(values, "POSTGRES_DSN")
        self.use_api_model = any(key in values for key in ("OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY"))
        url_key = "OPENAI_BASE_URL" if self.use_api_model else "QWEN_URL"
        self.qwen_url = (
            self._required(values, url_key) if self.use_api_model else values.get(url_key, "http://llm:8080/v1").strip()
        ).rstrip("/")
        try:
            url = urlsplit(self.qwen_url)
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or any(character.isspace() for character in self.qwen_url)
                or (url.port is not None and not 1 <= url.port <= 65535)
                or (not self.use_api_model and url.path != "/v1")
            ):
                raise ValueError()
        except ValueError:
            raise ValueError(
                f"Настройка {url_key} должна быть HTTP адресом API без учётных данных и параметров"
            ) from None
        self.qwen_model = self._required(values, "OPENAI_MODEL") if self.use_api_model else "qwen3-1.7b"
        self.qwen_api_key = self._required(values, "OPENAI_API_KEY") if self.use_api_model else "local"
        self.model_dir = Path(values.get("MODEL_DIR", "/models"))
        self.workers = self._number(values, "WORKERS", 4, int)
        self.capacity = self._number(values, "CAPACITY", 16, int)
        if not self.workers <= self.capacity <= 100:
            raise ValueError("Нужны WORKERS <= CAPACITY <= 100")
        self.max_attachments = self._number(values, "MAX_ATTACHMENTS", 8, int)
        self.max_file_bytes = self._number(values, "MAX_FILE_BYTES", 10485760, int)
        self.max_pdf_pages = self._number(values, "MAX_PDF_PAGES", 20, int)
        self.connect_timeout = self._number(values, "CONNECT_TIMEOUT", 5, int)
        self.poll_timeout = self._number(values, "POLL_TIMEOUT", 1, int)
        self.receive_timeout = self._number(values, "RECEIVE_TIMEOUT", 10, int)
        self.send_timeout = self._number(values, "SEND_TIMEOUT", 15, float)
        self.download_timeout = self._number(values, "DOWNLOAD_TIMEOUT", 30, float)
        self.pdf_timeout = self._number(values, "PDF_TIMEOUT", 30, float)
        self.ocr_timeout = self._number(values, "OCR_TIMEOUT", 120, float)
        self.qwen_timeout = self._number(values, "QWEN_TIMEOUT", 60, float)
        self.statement_timeout_ms = self._number(values, "STATEMENT_TIMEOUT_MS", 10000, int)
        self.shutdown_timeout = self._number(values, "SHUTDOWN_TIMEOUT", 30, float)
        if self.shutdown_timeout > 30:
            raise ValueError("SHUTDOWN_TIMEOUT должен быть не больше 30 секунд")
        self.retry_delay = self._number(values, "STORAGE_RETRY_DELAY", 1, float)

    def _required(self, values: Mapping[str, str], key: str) -> str:
        value = values.get(key, "").strip()
        if not value:
            raise ValueError(f"Нужна настройка {key}")
        return value

    def _number(self, values: Mapping[str, str], key: str, default, convert):
        try:
            number = convert(values.get(key, str(default)))
            if not math.isfinite(number) or number <= 0:
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f"Настройка {key} должна быть конечной и положительной") from None
        return number
