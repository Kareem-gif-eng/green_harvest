"""الأيقونات والصور: موجودة، صالحة كـ XML، ومربوطة بالصفحات."""
import re
import sys
import unittest
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_flow import Base  # noqa: E402

IMG = ROOT / "app" / "static" / "img"


class Assets(unittest.TestCase):
    def test_sprite_defines_every_icon_used_in_templates(self):
        sprite = (IMG / "icons.svg").read_text(encoding="utf-8")
        defined = set(re.findall(r'<symbol id="i-([\w-]+)"', sprite))
        used = set()
        for f in (ROOT / "app" / "templates").rglob("*.html"):
            used |= set(re.findall(r"#i-([\w-]+)", f.read_text(encoding="utf-8")))
            used |= set(re.findall(r"icon\('([\w-]+)'\)", f.read_text(encoding="utf-8")))
        self.assertTrue(used)
        self.assertEqual(used - defined, set(), "أيقونات مستخدمة ومش موجودة في الـ sprite")

    def test_every_svg_is_well_formed(self):
        for f in IMG.glob("*.svg"):
            xml.dom.minidom.parse(str(f))

    def test_every_image_has_alt_text_in_templates(self):
        for f in (ROOT / "app" / "templates").rglob("*.html"):
            for tag in re.findall(r"<img[^>]*>", f.read_text(encoding="utf-8")):
                self.assertIn("alt=", tag, f"{f.name}: {tag[:60]}")


class Pages(Base):
    def test_home_is_simple_with_icons_and_no_large_images(self):
        html = self.cl().get("/").get_data(as_text=True)
        self.assertNotIn("farm-hero.svg", html)
        self.assertNotIn("crop-tomato.svg", html)
        self.assertIn("/assistant", html)
        self.assertIn("#i-chat", html)

    def test_reader_bar_has_icons_on_every_page(self):
        c = self.cl()
        for url in ("/", "/market", "/impact", "/login"):
            html = c.get(url).get_data(as_text=True)
            self.assertIn("#i-speaker", html, url)
            self.assertIn('id="read-page"', html, url)

    def test_market_card_falls_back_to_default_image(self):
        f = self.user("farmer", "f@x.com")
        self.post(f, "/market/new", dict(name="خيار", quantity_kg="5", price_per_kg="3"))
        html = self.cl().get("/market").get_data(as_text=True)
        self.assertIn("img/product-default.svg", html)

    def test_diagnosis_and_assistant_pages_show_icons(self):
        f = self.user("farmer", "f@x.com")
        self.assertNotIn("leaf-spots.svg", f.get("/diagnose").get_data(as_text=True))
        html = f.get("/assistant").get_data(as_text=True)
        self.assertIn("#i-camera", html)
        self.assertIn("#i-image", html)
        self.assertIn("#i-send", html)


if __name__ == "__main__":
    unittest.main()
