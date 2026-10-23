import multiprocessing
import time

import pytest

from receipt_bot.adapters.recognition.native_operation import run_native
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.messaging.attachment import Attachment
from tests.helpers.recognition.create_pdf import create_pdf, create_scan_with_footer


def rotate_pdf(content: bytes, rotation: int) -> bytes:
    import pymupdf

    with pymupdf.open(stream=content, filetype="pdf") as document:
        document[0].set_rotation(rotation)
        return document.tobytes()


def test_pdf_preserves_page_text_and_renders_only_ocr_pages():
    from receipt_bot.adapters.recognition.py_mu_pdf_reader import PyMuPDFReader

    content = run_native(create_pdf, (((200, 300), (400, 500)), "Receipt 10.00"), 10)
    attachment = Attachment("receipt.pdf", "application/pdf", content)
    pages = PyMuPDFReader(timeout=10).read(attachment)
    assert len(pages) == 2
    assert pages[0].width == 200 and pages[0].height == 300
    assert pages[0].text_lines[0].text == "Receipt 10.00"
    assert pages[0].text_lines[0].box[0] == 20
    assert pages[0].image is None and pages[0].text_usable
    assert not pages[1].text_usable and pages[1].image.startswith(b"\x89PNG")
    assert pages[1].page_number == 2 and pages[1].width == 400


def test_pdf_rejects_page_limit_and_malformed_pdf():
    from receipt_bot.adapters.recognition.py_mu_pdf_reader import PyMuPDFReader

    content = run_native(create_pdf, (((200, 300),) * 3,), 10)
    attachment = Attachment("receipt.pdf", "application/pdf", content)
    with pytest.raises(FileProcessingError, match="pdf_page_limit"):
        PyMuPDFReader(max_pages=2, timeout=10).read(attachment)
    with pytest.raises(FileProcessingError):
        PyMuPDFReader(timeout=10).read(Attachment("bad.pdf", "application/pdf", b"bad"))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_scan_with_short_text_footer_requires_ocr(rotation):
    from receipt_bot.adapters.recognition.py_mu_pdf_reader import PyMuPDFReader

    source = run_native(create_pdf, (((300, 1000),), "RECEIPT\nMilk 100.00\nTOTAL 100.00"), 10)
    content = run_native(create_scan_with_footer, (source,), 10)
    content = run_native(rotate_pdf, (content, rotation), 10)
    pages = PyMuPDFReader(timeout=10).read(Attachment("scan.pdf", "application/pdf", content))
    assert [line.text for line in pages[0].text_lines] == ["Page 1 of 1"]
    assert not pages[0].text_usable
    assert pages[0].image.startswith(b"\x89PNG")


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotated_text_pdf_preserves_text_without_ocr(rotation):
    from receipt_bot.adapters.recognition.py_mu_pdf_reader import PyMuPDFReader

    content = run_native(create_pdf, (((300, 1000),), "Receipt 10.00"), 10)
    content = run_native(rotate_pdf, (content, rotation), 10)
    page = PyMuPDFReader(timeout=10).read(Attachment("text.pdf", "application/pdf", content))[0]
    assert page.text_usable and page.image is None
    assert page.text_lines[0].text == "Receipt 10.00"
    assert (page.width, page.height) == ((1000, 300) if rotation in (90, 270) else (300, 1000))
    left, top, right, bottom = page.text_lines[0].box
    assert 0 <= left < right <= page.width
    assert 0 <= top < bottom <= page.height


def test_native_deadline_terminates_stuck_process_and_collects_failure():
    from receipt_bot.adapters.recognition.native_operation import run_native
    from tests.helpers.recognition.native_tasks import delayed_result, failed_result

    before = {process.pid for process in multiprocessing.active_children()}
    started = time.monotonic()
    with pytest.raises(FileProcessingError, match="native_timeout"):
        run_native(delayed_result, (), 0.2)
    assert time.monotonic() - started < 3
    assert {process.pid for process in multiprocessing.active_children()} == before
    with pytest.raises(FileProcessingError, match="native_failed"):
        run_native(failed_result, (), 3)


def test_paddle_mapping_uses_rec_polys_and_scales_to_page_size():
    from receipt_bot.adapters.recognition.paddle_ocr_runner import map_prediction

    results = [
        {
            "rec_texts": ["Молоко", "ИТОГ"],
            "rec_scores": [0.99, 0.95],
            "rec_polys": [[[10, 20], [90, 20], [90, 40], [10, 40]], [[10, 80], [90, 80], [90, 100], [10, 100]]],
        }
    ]
    recognition = map_prediction(results, 2, (100, 200), 200, 400)
    assert [line.text for line in recognition.lines] == ["Молоко", "ИТОГ"]
    assert recognition.lines[0].box == (20, 40, 180, 80)
    assert recognition.lines[1].page_number == 2 and recognition.lines[1].order == 1
    with pytest.raises(FileProcessingError):
        map_prediction([{"rec_texts": ["a"], "rec_scores": [], "rec_polys": []}], 1, (10, 10), None, None)
