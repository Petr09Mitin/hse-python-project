import asyncio
import math
from io import BytesIO

import aiohttp
from telebot import TeleBot

from receipt_bot.adapters.telegram.telegram_error import TELEGRAM_ERRORS
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.messaging.attachment_downloader import AttachmentDownloader
from receipt_bot.application.messaging.attachment_reference import AttachmentReference


class TelegramAttachmentDownloader(AttachmentDownloader):
    """Скачивает допустимый файл, ограничивая размер и время."""

    def __init__(self, bot: TeleBot, max_bytes: int = 10 * 1024 * 1024, timeout: float = 30):
        if type(max_bytes) is not int or max_bytes < 1 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Некорректный предел скачивания")
        self.bot = bot
        self.max_bytes = max_bytes
        self.timeout = timeout

    def download(self, reference: AttachmentReference) -> Attachment:
        if reference.media_type not in ("application/pdf", "image/jpeg", "image/png"):
            raise FileProcessingError("unsupported_attachment_type")
        if reference.size_bytes is not None and reference.size_bytes > self.max_bytes:
            raise FileProcessingError("attachment_too_large")
        try:
            url = self.bot.get_file_url(reference.source_token)
        except TELEGRAM_ERRORS as error:
            raise FileProcessingError("telegram_file_unavailable") from error
        try:
            content = asyncio.run(self._download(url))
        except (aiohttp.ClientError, TimeoutError, OSError) as error:
            raise FileProcessingError("attachment_download_failed") from error
        expected = {"application/pdf": b"%PDF-", "image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n"}
        if not content.startswith(expected[reference.media_type]):
            raise FileProcessingError("attachment_content_type_mismatch")
        return Attachment(reference.file_name, reference.media_type, content)

    async def _download(self, url: str) -> bytes:
        timeout = aiohttp.ClientTimeout(total=self.timeout, connect=self.timeout, sock_read=self.timeout)
        async with (
            aiohttp.ClientSession(timeout=timeout) as client,
            client.get(url, allow_redirects=False) as response,
        ):
            if response.status != 200:
                raise FileProcessingError("attachment_http_failed")
            if response.content_length is not None and response.content_length > self.max_bytes:
                raise FileProcessingError("attachment_too_large")
            with BytesIO() as output:
                async for chunk in response.content.iter_chunked(65536):
                    if output.tell() + len(chunk) > self.max_bytes:
                        raise FileProcessingError("attachment_too_large")
                    output.write(chunk)
                return output.getvalue()
