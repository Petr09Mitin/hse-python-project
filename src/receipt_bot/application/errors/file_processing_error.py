class FileProcessingError(Exception):
    """Ожидаемая ошибка обработки файла с понятным кодом причины."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
