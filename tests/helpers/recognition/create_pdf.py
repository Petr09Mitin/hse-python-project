def create_pdf(sizes: tuple, first_text: str = "") -> bytes:
    import pymupdf

    with pymupdf.open() as document:
        for index, (width, height) in enumerate(sizes):
            page = document.new_page(width=width, height=height)
            if index == 0 and first_text:
                page.insert_text((20, 30), first_text)
        return document.tobytes()


def create_scan_with_footer(content: bytes) -> bytes:
    import pymupdf

    with pymupdf.open(stream=content, filetype="pdf") as source, pymupdf.open() as scan:
        page = source[0]
        bitmap = page.get_pixmap().tobytes("png")
        result = scan.new_page(width=page.rect.width, height=page.rect.height + 40)
        result.insert_image(page.rect, stream=bitmap)
        result.insert_text((20, page.rect.height + 25), "Page 1 of 1")
        return scan.tobytes()
