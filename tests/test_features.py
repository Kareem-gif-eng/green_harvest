"""اختبار الميزات: التقويم، ولوحات كل دور، وإن الميزات اللي اتشالت مابقتش موجودة."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_flow import Base  # noqa: E402


class Calendar(Base):
    def test_harvest_date_is_planting_plus_days(self):
        f = self.user("farmer", "f@x.com")
        self.post(f, "/crops", dict(name="بصل", planting_date="2026-01-10", harvest_days="90"))
        self.post(f, "/crops", dict(name="كوسة", planting_date="", harvest_days=""))
        page = f.get("/calendar").get_data(as_text=True)
        self.assertIn((date(2026, 1, 10) + timedelta(days=90)).isoformat(), page)
        self.assertIn("كوسة", page)  # ناقصة البيانات لازم تظهر في قائمة النقص
        self.assertEqual(self.cl().get("/calendar").status_code, 302)
        self.assertEqual(self.user("charity", "c@x.com").get("/calendar").status_code, 403)


class RemovedFeatures(Base):
    def test_removed_routes_are_gone(self):
        c = self.cl()
        for url in ("/whatsapp", "/whatsapp/webhook", "/consultations"):
            self.assertEqual(c.get(url).status_code, 404, url)

    def test_no_removed_links_in_any_role_navigation(self):
        pages = {"anon": self.cl(), "farmer": self.user("farmer", "f@x.com"),
                 "charity": self.user("charity", "c@x.com")}
        for role, client in pages.items():
            for url in ("/", "/dashboard", "/market", "/impact"):
                html = client.get(url).get_data(as_text=True)
                self.assertNotIn("واتساب", html, f"{role} {url}")
                self.assertNotIn("whatsapp", html.lower(), f"{role} {url}")
                self.assertNotIn("الاستشارات", html, f"{role} {url}")
                self.assertNotIn("/consultations", html, f"{role} {url}")
                self.assertNotIn("استشارة مهندس", html, f"{role} {url}")
                self.assertNotIn("مهندس", html, f"{role} {url}")

    def test_old_consultation_data_is_kept(self):
        f = self.user("farmer", "f@x.com")
        with self.app.app_context():
            from app.db import execute
            execute("INSERT INTO consultations(farmer_id,question) VALUES(1,'سؤال قديم')")
        self.assertEqual(self.rows("SELECT question FROM consultations")[0][0], "سؤال قديم")
        self.assertIsNotNone(f.get("/dashboard"))

    def test_old_engineer_accounts_are_plain_users_now(self):
        with self.app.app_context():
            from app.db import execute
            from werkzeug.security import generate_password_hash
            execute("INSERT INTO users(name,email,pw,role) VALUES('Old Eng','eng@x.com',?,'engineer')",
                    (generate_password_hash("password1"),))
        c = self.cl()
        self.post(c, "/login", dict(email="eng@x.com", password="password1"))
        r = c.get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/assistant", r.get_data(as_text=True))
        self.assertEqual(c.get("/diagnose").status_code, 403)

    def test_register_offers_only_public_roles(self):
        html = self.cl().get("/register").get_data(as_text=True)
        self.assertNotIn('value="engineer"', html)
        self.assertIn('value="farmer"', html)
        self.assertIn('value="charity"', html)


class Dashboards(Base):
    def test_farmer_and_charity_dashboards_render(self):
        for role in ("farmer", "charity"):
            c = self.user(role, f"{role}@x.com")
            self.assertEqual(c.get("/dashboard").status_code, 200, role)

    def test_admin_dashboard_renders(self):
        admin_client = self.cl()
        with self.app.app_context():
            from app.db import execute
            from werkzeug.security import generate_password_hash
            execute("INSERT INTO users(name,email,pw,role) VALUES('Admin','a@x.com',?,'admin')",
                    (generate_password_hash("password1"),))
        self.post(admin_client, "/login", dict(email="a@x.com", password="password1"))
        self.assertEqual(admin_client.get("/dashboard").status_code, 200)


if __name__ == "__main__":
    unittest.main()
