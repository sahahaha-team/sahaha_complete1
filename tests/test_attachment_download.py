import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import app
from chatbot.attachment_download import fetch_official_attachment


PDF_URL = "https://www.saha.go.kr/portal/Downfiles/saha_bicycle_road2017.pdf"


class AttachmentDownloadTests(unittest.TestCase):
    @staticmethod
    def response(content=b"%PDF-example", *, status=200, headers=None):
        response = Mock()
        response.status_code = status
        response.headers = headers or {"Content-Type": "application/pdf"}
        response.iter_content.return_value = [content]
        response.raise_for_status.return_value = None
        return response

    @patch("chatbot.attachment_download.requests.get")
    def test_official_pdf_is_returned_with_safe_filename(self, get):
        get.return_value = self.response()
        content, media_type, filename = fetch_official_attachment(PDF_URL, "자전거도로 현황도")
        self.assertEqual(b"%PDF-example", content)
        self.assertEqual("application/pdf", media_type)
        self.assertEqual("자전거도로 현황도.pdf", filename)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_non_official_or_non_document_url_is_rejected(self):
        for url in (
            "https://saha.go.kr.example.com/report.pdf",
            "http://www.saha.go.kr/report.pdf",
            "https://www.saha.go.kr/page.html",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    fetch_official_attachment(url)

    @patch("chatbot.attachment_download.requests.get")
    def test_api_forces_browser_download(self, get):
        get.return_value = self.response()
        response = TestClient(app.app).get(
            "/api/attachments/download",
            params={"url": PDF_URL, "name": "자전거도로 현황도"},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(b"%PDF-example", response.content)
        self.assertTrue(response.headers["content-disposition"].startswith("attachment;"))
        self.assertIn("filename*=UTF-8''%", response.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
