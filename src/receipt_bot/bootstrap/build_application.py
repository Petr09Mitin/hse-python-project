from threading import Lock

from telebot import TeleBot, apihelper

from receipt_bot.adapters.persistence.postgres_conversation_repository import PostgresConversationRepository
from receipt_bot.adapters.persistence.postgres_expense_repository import PostgresExpenseRepository
from receipt_bot.adapters.recognition.paddle_ocr_runner import PaddleOCRRunner
from receipt_bot.adapters.recognition.py_mu_pdf_reader import PyMuPDFReader
from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner
from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier
from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer
from receipt_bot.adapters.recognition.qwen_receipt_item_classificator import QwenReceiptItemClassificator
from receipt_bot.adapters.reports.openpyxl_report_exporter import OpenpyxlReportExporter
from receipt_bot.adapters.telegram.telegram_attachment_downloader import TelegramAttachmentDownloader
from receipt_bot.adapters.telegram.telegram_message_receiver import TelegramMessageReceiver
from receipt_bot.adapters.telegram.telegram_message_sender import TelegramMessageSender
from receipt_bot.application.categories.category_review_processor import CategoryReviewProcessor
from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher
from receipt_bot.application.receipts.message_processor import MessageProcessor
from receipt_bot.application.receipts.receipt_saver import ReceiptSaver
from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor
from receipt_bot.application.reports.report_period_resolver import ReportPeriodResolver
from receipt_bot.application.reports.report_processor import ReportProcessor
from receipt_bot.bootstrap.application_runner import ApplicationRunner
from receipt_bot.bootstrap.application_settings import ApplicationSettings


def build_application(settings: ApplicationSettings) -> ApplicationRunner:
    """Собирает приложение и его внешние зависимости."""
    apihelper.CONNECT_TIMEOUT = settings.connect_timeout
    apihelper.READ_TIMEOUT = settings.receive_timeout
    apihelper.RETRY_ON_ERROR = False
    apihelper.SESSION_TIME_TO_LIVE = None
    bot = TeleBot(settings.telegram_api_key, threaded=False, skip_pending=False)
    expenses = PostgresExpenseRepository(settings.postgres_dsn, settings.connect_timeout, settings.statement_timeout_ms)
    conversations = PostgresConversationRepository(
        settings.postgres_dsn, settings.connect_timeout, settings.statement_timeout_ms
    )
    # API-модель может тратить общий лимит ответа на обязательные размышления перед JSON.
    client = QwenClient(
        settings.qwen_url,
        settings.qwen_model,
        settings.qwen_timeout,
        max_concurrent=2,
        max_tokens=8192 if settings.use_api_model else 2048,
        api_key=settings.qwen_api_key,
    )
    sessions = []
    session_lock = Lock()

    def initialize_worker():
        # SDK не закрывает сессии работников; сохраняем их для очистки при остановке.
        with session_lock:
            sessions.append(apihelper._get_req_session())

    def close():
        client.close()
        for session in sessions:
            session.close()

    try:
        ocr = (
            QwenOCRRunner(client)
            if settings.use_api_model
            else PaddleOCRRunner(
                str(settings.model_dir / "PP-OCRv3_mobile_det"),
                str(settings.model_dir / "cyrillic_PP-OCRv3_mobile_rec"),
                settings.ocr_timeout,
            )
        )
        initialize_worker()
        receipts = MessageProcessor(
            expenses,
            TelegramAttachmentDownloader(bot, settings.max_file_bytes, settings.download_timeout),
            ReceiptTextExtractor(
                PyMuPDFReader(settings.max_pdf_pages, settings.pdf_timeout), ocr, settings.max_pdf_pages
            ),
            QwenReceiptClassifier(client),
            QwenReceiptDataStructurer(client),
            QwenReceiptItemClassificator(client),
            ReceiptSaver(expenses),
            settings.max_attachments,
            settings.max_file_bytes,
        )
        reports = ReportProcessor(ReportPeriodResolver(conversations), expenses, OpenpyxlReportExporter())
        dispatcher = MessageDispatcher(
            receipts, CategoryReviewProcessor(expenses), reports, TelegramMessageSender(bot, settings.send_timeout)
        )
        return ApplicationRunner(
            TelegramMessageReceiver(bot, settings.capacity, settings.poll_timeout, settings.receive_timeout),
            dispatcher,
            settings.workers,
            settings.capacity,
            settings.shutdown_timeout,
            settings.retry_delay,
            close,
            initialize_worker,
        )
    except Exception:
        close()
        raise
