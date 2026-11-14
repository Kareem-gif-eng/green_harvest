"""اختبار سيناريوهات كاملة: الحسابات، المزارع، السوق، التبرعات."""
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "t.db")
        self.app = create_app(self.db_path, uploads_dir=self.tmp)
        self.app.config["TESTING"] = True

    def cl(self):
        return self.app.test_client()

    def post(self, client, url, data=None):
        with client.session_transaction() as s:
            s["csrf"] = "t"
        return client.post(url, data=dict(data or {}, _csrf="t"))

    def user(self, role, email, city="Mansoura"):
        c = self.cl()
        r = self.post(c, "/register", dict(name=email, email=email, password="password1",
                                           role=role, city=city, phone="010"))
        self.assertEqual(r.status_code, 302)
        return c

    def rows(self, sql):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()


class Flow(Base):
    def test_auth_and_roles(self):
        self.user("farmer", "f@x.com")
        ch = self.user("charity", "c@x.com")
        self.assertEqual(self.cl().get("/dashboard").status_code, 302)
        self.assertEqual(ch.get("/diagnose").status_code, 403)
        self.assertEqual(self.post(ch, "/crops", dict(name="قمح")).status_code, 403)
        c = self.cl()
        self.assertEqual(self.post(c, "/login", dict(email="f@x.com", password="bad")).status_code, 200)
        self.assertEqual(self.post(c, "/login", dict(email="f@x.com", password="password1")).status_code, 302)
        self.assertEqual(self.cl().post("/login", data={}).status_code, 400)

    def test_crops_private_and_diagnosis(self):
        a = self.user("farmer", "a@x.com")
        b = self.user("farmer", "b@x.com")
        self.post(a, "/crops", dict(name="طماطم", planting_date="2026-03-01"))
        self.assertIn("طماطم", a.get("/dashboard").get_data(as_text=True))
        self.assertNotIn("طماطم", b.get("/dashboard").get_data(as_text=True))
        self.assertEqual(self.post(b, "/crops/1/delete").status_code, 403)
        with a.session_transaction() as s:
            s["csrf"] = "t"
        r = a.post("/diagnose", data={"crop": "طماطم", "symptoms": "بقع", "_csrf": "t",
                                      "image": (io.BytesIO(b"\x89PNG\r\n"), "x.png")},
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        row = self.rows("SELECT status,result FROM diagnoses")[0]
        self.assertEqual((row["status"], row["result"]), ("awaiting_ai", None))
        self.assertIn("بانتظار", a.get("/diagnose").get_data(as_text=True))
        img = self.rows("SELECT image FROM diagnoses")[0]["image"]
        self.assertEqual(b.get("/uploads/" + img).status_code, 403)
        self.assertEqual(a.get("/uploads/" + img).status_code, 200)

    def test_market_orders_impact(self):
        s = self.user("farmer", "s@x.com", "Dakahlia")
        b = self.user("farmer", "b@x.com")
        self.post(s, "/market/new", dict(name="بطاطس", crop="بطاطس", quantity_kg="100",
                                         price_per_kg="5", city="Dakahlia"))
        self.assertEqual(self.post(s, "/market/new", dict(name="x", quantity_kg="-1",
                                                          price_per_kg="1")).status_code, 200)
        self.assertIn("بطاطس", self.cl().get("/market?q=بطا&city=Dakah&max_price=6").get_data(as_text=True))
        self.assertNotIn("بطاطس", self.cl().get("/market?max_price=1").get_data(as_text=True))
        self.assertEqual(self.post(s, "/market/1/order", dict(qty_kg="5")).status_code, 403)
        self.assertEqual(self.post(b, "/market/1/order", dict(qty_kg="500")).status_code, 302)
        self.assertEqual(len(self.rows("SELECT * FROM orders")), 0)
        self.post(b, "/market/1/order", dict(qty_kg="40"))
        self.assertEqual(self.post(b, "/orders/1/status", dict(status="accepted")).status_code, 403)
        self.post(s, "/orders/1/status", dict(status="accepted"))
        self.post(s, "/orders/1/status", dict(status="completed"))
        self.assertEqual(self.rows("SELECT available_kg FROM products")[0][0], 60)
        page = self.cl().get("/impact").get_data(as_text=True)
        self.assertIn(">100<", page)
        self.assertIn(">40<", page)
        self.assertEqual(len(self.rows("SELECT * FROM notifications WHERE user_id=1")), 1)

    def test_donation_workflow_and_notifications(self):
        f = self.user("farmer", "f@x.com")
        c1 = self.user("charity", "c1@x.com")
        c2 = self.user("charity", "c2@x.com")
        self.post(f, "/donations", dict(product="خيار", qty_kg="30", city="Mansoura"))
        self.post(c1, "/donations/1/request")
        self.post(c2, "/donations/1/request")
        self.assertEqual(self.post(c2, "/requests/1/respond", dict(action="accept")).status_code, 403)
        self.post(f, "/requests/1/respond", dict(action="accept"))
        st = {r["id"]: r["status"] for r in self.rows("SELECT * FROM donation_requests")}
        self.assertEqual(st, {1: "accepted", 2: "declined"})
        self.assertEqual(self.post(c2, "/requests/1/schedule",
                                   dict(pickup_time="2026-11-01T10:00")).status_code, 403)
        self.post(c1, "/requests/1/schedule", dict(pickup_time="2026-11-01T10:00", pickup_place="القرية"))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM donations WHERE status='collected'")[0][0], 0)
        self.post(c1, "/requests/1/collected")
        self.assertEqual(self.rows("SELECT status FROM donations")[0][0], "collected")
        self.assertTrue(any("موعد" in n["text"] for n in self.rows("SELECT text FROM notifications WHERE user_id=1")))
        self.post(f, "/notifications")
        self.assertEqual(self.rows("SELECT COUNT(*) FROM notifications WHERE user_id=1 AND is_read=0")[0][0], 0)


if __name__ == "__main__":
    unittest.main()
