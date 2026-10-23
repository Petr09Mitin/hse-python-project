import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import aiohttp

from receipt_bot.bootstrap.safe_logging import configure_logging

logger = logging.getLogger("receipt_bot.bootstrap.prepare_models")


def model_files() -> list[dict]:
    return json.loads(Path(__file__).with_name("models.json").read_text(encoding="utf-8"))


def checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download_model(url: str, destination: Path, sha256: str, timeout: float = 600, retry_delay: float = 1) -> None:
    """Загружает и проверяет модель перед атомарной заменой файла."""
    if destination.is_file() and checksum(destination) == sha256:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_download(url, destination, sha256, timeout, retry_delay))


async def _download(url: str, destination: Path, sha256: str, timeout: float, retry_delay: float) -> None:
    limits = aiohttp.ClientTimeout(total=timeout, connect=min(timeout, 10), sock_read=min(timeout, 30))
    async with aiohttp.ClientSession(timeout=limits, trust_env=False) as client:
        for attempt in range(3):
            temporary = None
            permanent = False
            try:
                with NamedTemporaryFile(dir=destination.parent, prefix=".download-", delete=False) as output:
                    temporary = Path(output.name)
                    digest = hashlib.sha256()
                    async with client.get(url) as response:
                        permanent = 400 <= response.status < 500 and response.status != 429
                        response.raise_for_status()
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            output.write(chunk)
                            digest.update(chunk)
                    if digest.hexdigest() != sha256:
                        raise ValueError("model_checksum_mismatch")
                temporary.replace(destination)
                return
            except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
                if permanent or attempt == 2:
                    raise RuntimeError("model_download_failed") from None
                await asyncio.sleep(retry_delay)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def prepare_models(directory: Path) -> None:
    for model in model_files():
        download_model(model["url"], directory / model["path"], model["sha256"])


def main() -> int:
    configure_logging()
    try:
        prepare_models(Path(os.environ.get("MODEL_DIR", "/models")))
    except (OSError, ValueError, RuntimeError):
        logger.error("models_failed")
        return 1
    logger.info("models_ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
