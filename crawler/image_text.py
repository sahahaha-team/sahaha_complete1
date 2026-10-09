"""Local Windows OCR for public administrative images and scanned PDF pages."""
import subprocess
from pathlib import Path


def ocr_image(path: Path) -> str:
    from PIL import Image
    path = Path(path).resolve()
    normalized = path.with_name(path.stem + "_ocr.png")
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((2400, 2400))
        image.save(normalized)
    script = Path(__file__).resolve().parents[1] / "scripts" / "windows_ocr.ps1"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", str(script), "-ImagePath", str(normalized)],
                            capture_output=True, encoding="utf-8-sig", errors="replace", timeout=60,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("windows_ocr_failed")
    return result.stdout.strip()


def scanned_pdf_text(path: Path) -> str:
    import fitz
    import pdfplumber
    parts = []
    with fitz.open(path) as document, pdfplumber.open(path) as text_document:
        for page in document:
            text = (text_document.pages[page.number].extract_text() or '').strip()
            if len(text) < 30:
                image = path.with_name(path.stem + f"_page_{page.number}.png")
                scale = min(2, 2300 / max(page.rect.width, page.rect.height))
                page.get_pixmap(matrix=fitz.Matrix(scale, scale)).save(image)
                text = ocr_image(image)
                if text:
                    text = '[이미지 문자 인식 자료: 오자 가능, 원문 확인 필요]\n' + text
            if text:
                parts.append(f"[원문 {page.number+1}쪽]\n{text}")
    return "\n\n".join(parts)
