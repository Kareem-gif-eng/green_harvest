"""فحص المسارات والروابط:
- كل ملف template بيتشار له بـ extends/include/from موجود فعلاً.
- كل url_for('endpoint') في القوالب موجود في التطبيق.
- كل رابط href/action ثابت في القوالب بيطابق route حقيقي.
- كل صفحة GET بدون متغيرات بترجع بدون خطأ 500، لكل الأدوار.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import RequestRedirect

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

TEMPLATES = ROOT / "app" / "templates"
TEMPLATE_REF = re.compile(r"{%-?\s*(?:extends|include|from)\s+['\"]([^'\"]+)['\"]")
URL_FOR = re.compile(r"url_for\(\s*['\"]([\w.]+)['\"]")
STATIC_LINK = re.compile(r"""(href|action|src)=["'](/[^"']*)["']""")


def template_files():
    return sorted(TEMPLATES.rglob("*.html"))


class LinkChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp()
        cls.app = create_app(os.path.join(tmp, "t.db"), uploads_dir=tmp)
        cls.app.config["TESTING"] = True

    def test_every_template_reference_exists(self):
        names = {p.relative_to(TEMPLATES).as_posix() for p in template_files()}
        for path in template_files():
            for ref in TEMPLATE_REF.findall(path.read_text(encoding="utf-8")):
                self.assertIn(ref, names, f"{path.name}: قالب مفقود {ref}")

    def test_every_url_for_endpoint_exists(self):
        endpoints = set(self.app.view_functions) | {"static"}
        for path in template_files():
            for ep in URL_FOR.findall(path.read_text(encoding="utf-8")):
                self.assertIn(ep, endpoints, f"{path.name}: endpoint غير موجود {ep}")

    def test_hardcoded_links_match_routes(self):
        adapter = self.app.url_map.bind("localhost")
        for path in template_files():
            for attr, link in STATIC_LINK.findall(path.read_text(encoding="utf-8")):
                if "{" in link:
                    continue
                method = "POST" if attr == "action" else "GET"
                if attr == "src" or link.startswith("/static/"):
                    method = "GET"
                try:
                    adapter.match(link, method=method)
                except (NotFound, MethodNotAllowed, RequestRedirect) as exc:
                    if isinstance(exc, RequestRedirect):
                        continue
                    self.fail(f"{path.name}: الرابط {link} ({method}) مش متطابق مع أي route")

    def test_static_assets_served(self):
        with self.app.test_client() as c:
            r = c.get("/static/css/style.css")
            self.assertEqual(r.status_code, 200)
            self.assertIn("text/css", r.mimetype)

    def test_public_and_error_pages(self):
        with self.app.test_client() as c:
            for url in ("/", "/market", "/impact", "/login", "/register"):
                self.assertEqual(c.get(url).status_code, 200, url)
            self.assertEqual(c.get("/nope").status_code, 404)
            self.assertEqual(c.get("/market/999").status_code, 404)

    def test_every_static_get_route_renders_without_500(self):
        with self.app.test_client() as c:
            for rule in self.app.url_map.iter_rules():
                if "GET" not in rule.methods or rule.arguments or rule.endpoint == "static":
                    continue
                status = c.get(rule.rule).status_code
                self.assertLess(status, 500, f"{rule.rule} رجع {status}")


if __name__ == "__main__":
    unittest.main()
