"""Render a PDF page as a deterministic EPUB cover asset."""
from __future__ import annotations

from io import BytesIO
import hashlib
from pathlib import Path


def add_pdf_cover(
    book: dict,
    source: Path,
    assets_dir: Path,
    *,
    page_number: int = 1,
    scale: float = 4.0,
) -> dict:
    """Render ``page_number`` and attach it to ``book`` as its EPUB cover."""
    if page_number < 1:
        raise ValueError("cover page number must be positive")
    if scale <= 0:
        raise ValueError("cover scale must be positive")

    import pypdfium2

    document = pypdfium2.PdfDocument(str(source))
    page_count = len(document)
    if page_number > page_count:
        document.close()
        raise ValueError(
            f"cover page {page_number} is outside the {page_count}-page PDF"
        )
    page = document[page_number - 1]
    bitmap = None
    try:
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().convert("RGB")
        stream = BytesIO()
        image.save(stream, format="PNG", optimize=True, compress_level=9)
        payload = stream.getvalue()
        width, height = image.size
    finally:
        if bitmap is not None and hasattr(bitmap, "close"):
            bitmap.close()
        page.close()
        document.close()

    digest = hashlib.sha256(payload).hexdigest()
    relative_path = f"assets/cover-{digest[:16]}.png"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir.parent / relative_path).write_bytes(payload)
    cover = {
        "path": relative_path,
        "media_type": "image/png",
        "sha256": digest,
        "width_px": width,
        "height_px": height,
        "source_page": page_number,
        "alt": f"Cover of {book['title']}",
    }
    book["cover"] = cover
    if not any(asset["path"] == relative_path for asset in book["assets"]):
        book["assets"].append(
            {
                "path": relative_path,
                "media_type": "image/png",
                "sha256": digest,
            }
        )
    return cover
