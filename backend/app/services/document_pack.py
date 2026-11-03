"""Add a family's supporting documents to the end of a printed claim.

PDFs are added page by page as they are. Photos (JPG, PNG, WebP) are each
placed on an A4 page, turned the right way up, with a small caption. A file
that cannot be read is not silently dropped: a page says what is missing, so
whoever prints the pack knows to attach it by hand.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

A4 = (595.276, 841.89)
MARGIN = 36


@dataclass
class Attachment:
    label: str  # "Aadhaar card"
    filename: str
    mime_type: str
    content: bytes | None  # None when the stored file is gone


def _caption_page(lines: list[str]) -> bytes:
    from reportlab.pdfgen import canvas as rl_canvas

    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=A4)
    canvas.setFont("Helvetica-Bold", 14)
    y = A4[1] - 90
    for index, line in enumerate(lines):
        canvas.drawString(MARGIN + 20, y, line)
        if index == 0:
            canvas.setFont("Helvetica", 12)
        y -= 22
    canvas.save()
    return buffer.getvalue()


def _image_page(content: bytes, caption: str) -> bytes:
    from PIL import Image, ImageOps
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    image = ImageOps.exif_transpose(Image.open(io.BytesIO(content)))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=A4)
    canvas.setFont("Helvetica", 9)
    canvas.setFillGray(0.35)
    canvas.drawString(MARGIN, A4[1] - MARGIN + 10, caption)

    box_w = A4[0] - 2 * MARGIN
    box_h = A4[1] - 2 * MARGIN - 10
    scale = min(box_w / image.width, box_h / image.height)
    w, h = image.width * scale, image.height * scale
    x = (A4[0] - w) / 2
    y = MARGIN + (box_h - h) / 2
    canvas.drawImage(ImageReader(image), x, y, w, h)
    canvas.save()
    return buffer.getvalue()


def append_documents(pdf: bytes, attachments: list[Attachment]) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=io.BytesIO(pdf))
    total = len(attachments)

    def add_all(content: bytes) -> None:
        for page in PdfReader(io.BytesIO(content)).pages:
            writer.add_page(page)

    for number, item in enumerate(attachments, start=1):
        caption = f"Supporting document {number} of {total}: {item.label} ({item.filename})"
        problem = None
        if item.content is None:
            problem = "The file could not be found in storage."
        else:
            try:
                if item.mime_type == "application/pdf":
                    reader = PdfReader(io.BytesIO(item.content))
                    if reader.is_encrypted and not reader.decrypt(""):
                        raise ValueError("password protected")
                    for page in reader.pages:
                        writer.add_page(page)
                else:
                    add_all(_image_page(item.content, caption))
            except Exception:  # a damaged or locked file must not stop the whole pack
                problem = "The file could not be opened (it may be damaged or password protected)."
        if problem:
            add_all(_caption_page([
                f"Supporting document {number} of {total} is missing",
                f"{item.label}: {item.filename}",
                problem,
                "Please print it separately and attach it here.",
            ]))

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
