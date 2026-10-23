import math

from requests import RequestException
from telebot import apihelper


def error_details(error: Exception) -> tuple[bool, str, float]:
    if isinstance(error, apihelper.ApiTelegramException):
        code = error.error_code
        retry_after = error.result_json.get("parameters", {}).get("retry_after", 0)
        delay = 0
        if type(retry_after) in (int, float) and math.isfinite(retry_after) and retry_after > 0:
            delay = retry_after
        return code == 429 or code >= 500, f"telegram_{code}", delay
    if isinstance(error, apihelper.ApiHTTPException):
        code = error.result.status_code
        return code == 429 or code >= 500, f"telegram_http_{code}", 0
    return isinstance(error, RequestException), "telegram_network_error", 0


TELEGRAM_ERRORS = (apihelper.ApiException, RequestException)
