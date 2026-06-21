"""
파일 단위 데이터 적재 모듈 (PDF / HWPX / HWP)

웹 크롤링과 동일하게 PageData 호환 객체를 만들어 반환하므로,
이후 정제·태깅·임베딩·검색 파이프라인은 수정 없이 그대로 재사용된다.

- url 필드에는 로컬 파일을 식별하는 가상 URL("file://<상대경로>")을 넣어
  기존 upsert/중복제거(chunk_id = MD5(url_i)) 로직이 그대로 동작하게 한다.
- 각 추출기는 의존 라이브러리가 없거나 파싱에 실패해도 예외로 죽지 않고
  해당 파일만 건너뛴다 (명확한 경고 로그 출력).

지원 형식:
  .pdf   : pdfplumber (텍스트 레이어 기반, 스캔 이미지 PDF는 추출 불가)
  .hwpx  : 표준 zip + XML (의존성 없음, 권장)
  .hwp   : olefile 기반 PrvText 우선, 실패 시 best-effort (표/서식 누락 가능)
"""

import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".hwpx", ".hwp"}


@dataclass
class FilePageData:
    """크롤러의 PageData와 호환되는 최소 필드 집합."""
    url: str
    title: str
    content: str
    category: str
    sub_category: str = ""
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    not_modified: bool = False
    deleted: bool = False
    transient_fail: bool = False


# ===== 형식별 텍스트 추출 =====

def _extract_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber 미설치 → PDF 건너뜀 (pip install pdfplumber): %s", path.name)
        return ""

    texts: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    texts.append(t)
    except Exception as e:
        logger.warning("PDF 추출 실패 (%s): %s", path.name, e)
        return ""
    return "\n".join(texts)


def _extract_hwpx(path: Path) -> str:
    """HWPX = zip 컨테이너. Contents/section*.xml 의 텍스트 노드를 수집."""
    texts: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            section_names = sorted(
                n for n in zf.namelist()
                if n.startswith("Contents/section") and n.endswith(".xml")
            )
            for name in section_names:
                try:
                    root = ET.fromstring(zf.read(name))
                except ET.ParseError:
                    continue
                # 네임스페이스가 붙으므로 태그 localname 기준으로 텍스트 수집
                for elem in root.iter():
                    if elem.text and elem.text.strip():
                        texts.append(elem.text.strip())
    except Exception as e:
        logger.warning("HWPX 추출 실패 (%s): %s", path.name, e)
        return ""
    return "\n".join(texts)


def _extract_hwp(path: Path) -> str:
    """
    구버전 HWP(바이너리/OLE). PrvText(미리보기 텍스트) 스트림을 우선 사용.
    PrvText는 UTF-16LE 평문이라 의존성 없이 안전하게 읽힌다(서식/표는 누락).
    더 정밀한 추출이 필요하면 pyhwp/hwp5 설치 후 확장 가능.
    """
    try:
        import olefile
    except ImportError:
        logger.warning("olefile 미설치 → HWP 건너뜀 (pip install olefile): %s", path.name)
        return ""

    try:
        if not olefile.isOleFile(str(path)):
            logger.warning("HWP가 OLE 형식이 아님 → 건너뜀: %s", path.name)
            return ""
        ole = olefile.OleFileIO(str(path))
        try:
            if ole.exists("PrvText"):
                raw = ole.openstream("PrvText").read()
                return raw.decode("utf-16-le", errors="ignore").strip()
            logger.warning("HWP에 PrvText 스트림 없음 → 본문 추출 생략: %s", path.name)
            return ""
        finally:
            ole.close()
    except Exception as e:
        logger.warning("HWP 추출 실패 (%s): %s", path.name, e)
        return ""


_EXTRACTORS = {
    ".pdf": _extract_pdf,
    ".hwpx": _extract_hwpx,
    ".hwp": _extract_hwp,
}


def extract_text(path: Path) -> str:
    extractor = _EXTRACTORS.get(path.suffix.lower())
    if not extractor:
        return ""
    return extractor(path)


def load_file(path: Path, base_dir: Path, category: str) -> Optional[FilePageData]:
    """단일 파일 → FilePageData (추출 실패 시 None)."""
    text = extract_text(path)
    if not text or len(text.strip()) < 50:
        logger.warning("추출 텍스트가 비었거나 너무 짧음 → 건너뜀: %s", path.name)
        return None

    try:
        rel = path.relative_to(base_dir).as_posix()
    except ValueError:
        rel = path.name

    return FilePageData(
        url=f"file://{rel}",
        title=path.stem,
        content=text,
        category=category,
        sub_category=path.suffix.lower().lstrip("."),
    )


def load_files(target: str, category: str) -> list[FilePageData]:
    """
    target(폴더 또는 단일 파일) 아래의 지원 파일을 모두 적재.

    Returns: FilePageData 리스트 (추출 성공분만)
    """
    root = Path(target)
    if not root.exists():
        logger.warning("경로가 존재하지 않음: %s", root)
        return []

    if root.is_file():
        files = [root] if root.suffix.lower() in SUPPORTED_EXTENSIONS else []
        base_dir = root.parent
    else:
        files = sorted(
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        base_dir = root

    logger.info("파일 인제스트 대상: %d개 (%s)", len(files), root)

    pages: list[FilePageData] = []
    for p in files:
        page = load_file(p, base_dir, category)
        if page:
            pages.append(page)
            logger.info("  [OK] %s (%d자)", p.name, len(page.content))
    return pages
