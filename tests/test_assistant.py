"""اختبار المساعد الزراعي: Gemini (بدون إنترنت، بـ mock)، الـ endpoints، الصور، الأمان، والـ JS."""
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import gemini  # noqa: E402
from app.db import execute, query  # noqa: E402
from tests.test_flow import Base  # noqa: E402

FAKE_KEY = "fake-test-key-do-not-leak-0001"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
JPG = b"\xff\xd8\xff" + b"0" * 200
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 200


class GeminiModule(unittest.TestCase):
    def test_payload_contains_system_history_and_inline_images(self):
        body = gemini.build_payload(
            [{"role": "user", "text": "سؤال قديم"}, {"role": "assistant", "text": "رد قديم"}],
            "الورق اصفر",
            [("png", PNG), ("jpg", JPG), ("webp", WEBP)],
        )
        self.assertIn("مساعد زراعي", body["systemInstruction"]["parts"][0]["text"])
        roles = [c["role"] for c in body["contents"]]
        self.assertEqual(roles, ["user", "model", "user"])
        parts = body["contents"][-1]["parts"]
        self.assertEqual(parts[0]["text"], "الورق اصفر")
        mimes = [p["inline_data"]["mime_type"] for p in parts[1:]]
        self.assertEqual(mimes, ["image/png", "image/jpeg", "image/webp"])
        self.assertEqual(base64.b64decode(parts[1]["inline_data"]["data"]), PNG)

    def test_parse_reply_success_and_blocked(self):
        ok = {"candidates": [{"content": {"parts": [{"text": "الرد "}, {"text": "هنا"}]}}]}
        self.assertEqual(gemini.parse_reply(ok), "الرد هنا")
        with self.assertRaises(gemini.GeminiError) as blocked:
            gemini.parse_reply({"promptFeedback": {"blockReason": "SAFETY"}})
        self.assertEqual(blocked.exception.status, 422)
        with self.assertRaises(gemini.GeminiError):
            gemini.parse_reply({"candidates": []})

    def test_http_errors_become_arabic_messages(self):
        def raise_http(code):
            def _fake(*a, **k):
                raise urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"{}"))
            return _fake

        with mock.patch("urllib.request.urlopen", raise_http(403)):
            with self.assertRaises(gemini.GeminiError) as e:
                gemini.post_json("https://example.test/x", FAKE_KEY, {})
        self.assertEqual(e.exception.status, 503)
        self.assertNotIn(FAKE_KEY, e.exception.message)

        with mock.patch("urllib.request.urlopen", raise_http(429)):
            with self.assertRaises(gemini.GeminiError) as e:
                gemini.post_json("https://example.test/x", FAKE_KEY, {})
        self.assertIn("مشغول", e.exception.message)

        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no net")):
            with self.assertRaises(gemini.GeminiError) as e:
                gemini.post_json("https://example.test/x", FAKE_KEY, {})
        self.assertIn("اتصال", e.exception.message)

    def test_api_key_is_sent_as_header_not_in_url(self):
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}).encode()

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            return FakeResp()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            reply = gemini.generate_reply(FAKE_KEY, "gemini-2.5-flash", [], "سؤال", [])
        self.assertEqual(reply, "ok")
        self.assertNotIn(FAKE_KEY, captured["url"])
        self.assertEqual(captured["headers"]["x-goog-api-key"], FAKE_KEY)
        self.assertIn("gemini-2.5-flash:generateContent", captured["url"])


class AssistantEndpoints(Base):
    def setUp(self):
        super().setUp()
        self.app.config["GEMINI_API_KEY"] = FAKE_KEY
        self.calls = []
        self.original = gemini.generate_reply
        self.fail_with = None

        def fake(api_key, model, history, text, images):
            self.calls.append({"key": api_key, "history": history, "text": text, "images": images})
            if self.fail_with:
                raise self.fail_with
            return f"رد تجريبي على: {text or 'الصور'}"

        gemini.generate_reply = fake

    def tearDown(self):
        gemini.generate_reply = self.original

    def send(self, client, text="", images=(), csrf="t", header=False):
        with client.session_transaction() as s:
            s["csrf"] = csrf
        data = {"text": text, "images": [(io.BytesIO(b), name) for name, b in images]}
        if header:
            return client.post("/assistant/message", data=data, content_type="multipart/form-data",
                               headers={"X-CSRF-Token": csrf})
        data["_csrf"] = csrf
        return client.post("/assistant/message", data=data, content_type="multipart/form-data")

    def farmer(self):
        if getattr(self, "_farmer", None) is None:
            self._farmer = self.user("farmer", "farmer@x.com")
        return self._farmer

    def test_anonymous_gets_json_401(self):
        r = self.send(self.cl(), "سؤال")
        self.assertEqual(r.status_code, 401)
        self.assertFalse(r.get_json()["ok"])

    def test_missing_key_gives_503_in_arabic(self):
        self.app.config["GEMINI_API_KEY"] = ""
        r = self.send(self.farmer(), "سؤال")
        self.assertEqual(r.status_code, 503)
        self.assertIn("مش مفعّلة", r.get_json()["error"])
        self.assertEqual(self.calls, [])

    def test_text_message_round_trip_and_history(self):
        c = self.farmer()
        r1 = self.send(c, "إمتى أزرع الطماطم؟")
        self.assertEqual(r1.status_code, 200)
        body = r1.get_json()
        self.assertTrue(body["ok"])
        self.assertIn("إمتى أزرع الطماطم؟", body["reply"])
        self.send(c, "وأروي كام مرة؟")
        # آخر عنصر في التاريخ هو رد المساعد، اللي قبله سؤال المستخدم
        self.assertEqual(self.calls[1]["history"][-2], {"role": "user", "text": "إمتى أزرع الطماطم؟"})
        self.assertEqual(self.calls[1]["history"][-1]["role"], "assistant")
        rows = self.rows("SELECT role,text FROM ai_messages ORDER BY id")
        self.assertEqual([r["role"] for r in rows], ["user", "assistant", "user", "assistant"])

    def test_multiple_images_sent_together(self):
        c = self.farmer()
        r = self.send(c, "الورق بقى أصفر", [("a.png", PNG), ("b.jpg", JPG), ("c.webp", WEBP)])
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        sent = self.calls[-1]["images"]
        self.assertEqual([ext for ext, _ in sent], ["png", "jpg", "webp"])
        self.assertEqual(len(self.rows("SELECT * FROM ai_images")), 3)

    def test_images_without_text_are_allowed(self):
        self.assertEqual(self.send(self.farmer(), "", [("a.png", PNG)]).status_code, 200)

    def test_empty_message_rejected(self):
        r = self.send(self.farmer(), "   ")
        self.assertEqual(r.status_code, 400)

    def test_too_many_images_rejected(self):
        five = [(f"{i}.png", PNG) for i in range(5)]
        r = self.send(self.farmer(), "سؤال", five)
        self.assertEqual(r.status_code, 400)
        self.assertIn("4", r.get_json()["error"])
        self.assertEqual(self.calls, [])

    def test_invalid_image_content_rejected_with_position(self):
        r = self.send(self.farmer(), "سؤال", [("ok.png", PNG), ("fake.png", b"<html>not an image</html>")])
        self.assertEqual(r.status_code, 400)
        self.assertIn("رقم 2", r.get_json()["error"])
        self.assertEqual(self.calls, [])

    def test_wrong_extension_and_oversize_rejected(self):
        self.assertEqual(self.send(self.farmer(), "س", [("x.gif", b"GIF89a" + b"0" * 50)]).status_code, 400)
        big = b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10)
        self.assertEqual(self.send(self.farmer(), "س", [("big.png", big)]).status_code, 400)

    def test_gemini_failure_is_reported_and_not_saved(self):
        self.fail_with = gemini.GeminiError("المساعد مشغول جداً دلوقتي.", 503)
        r = self.send(self.farmer(), "سؤال", [("a.png", PNG)])
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["error"], "المساعد مشغول جداً دلوقتي.")
        self.assertEqual(self.rows("SELECT COUNT(*) c FROM ai_messages")[0]["c"], 0)
        self.assertEqual(self.rows("SELECT COUNT(*) c FROM ai_images")[0]["c"], 0)

    def test_csrf_required_form_or_header(self):
        c = self.farmer()
        bad = c.post("/assistant/message", data={"text": "سؤال"}, content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 400)
        good = self.send(c, "سؤال", header=True)
        self.assertEqual(good.status_code, 200)

    def test_images_private_to_owner(self):
        a = self.farmer()
        self.send(a, "صورة", [("p.png", PNG)])
        name = self.rows("SELECT filename FROM ai_images")[0]["filename"]
        self.assertTrue(name.startswith("c_"))
        self.assertEqual(a.get("/uploads/" + name).status_code, 200)
        other = self.user("charity", "other@x.com")
        self.assertEqual(other.get("/uploads/" + name).status_code, 403)
        self.assertEqual(self.cl().get("/uploads/" + name).status_code, 403)

    def test_page_renders_and_reset_clears_history_and_files(self):
        c = self.farmer()
        self.send(c, "صورة", [("p.png", PNG)])
        page = c.get("/assistant")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('data-enabled="yes"', html)
        self.assertIn('data-speak-text', html)
        self.assertIn('accept="image/jpeg,image/png,image/webp"', html)
        self.assertIn('capture="environment"', html)
        name = self.rows("SELECT filename FROM ai_images")[0]["filename"]
        self.assertTrue(os.path.exists(os.path.join(self.tmp, name)))
        with c.session_transaction() as s:
            s["csrf"] = "t"
        c.post("/assistant/reset", data={"_csrf": "t"})
        self.assertEqual(self.rows("SELECT COUNT(*) c FROM ai_messages")[0]["c"], 0)
        self.assertEqual(self.rows("SELECT COUNT(*) c FROM ai_images")[0]["c"], 0)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, name)))

    def test_disabled_page_still_renders_without_key(self):
        self.app.config["GEMINI_API_KEY"] = ""
        html = self.farmer().get("/assistant").get_data(as_text=True)
        self.assertIn('data-enabled="no"', html)
        self.assertIn("مش مفعّلة", html)

    def test_api_key_never_reaches_the_browser(self):
        c = self.farmer()
        self.send(c, "سؤال")
        pages = [c.get("/assistant").get_data(as_text=True), c.get("/dashboard").get_data(as_text=True),
                 self.cl().get("/").get_data(as_text=True)]
        js = "".join((ROOT / "app" / "static" / "js" / f).read_text(encoding="utf-8")
                     for f in ("assistant.js", "voice.js"))
        for text in pages + [js]:
            self.assertNotIn(FAKE_KEY, text)
            self.assertNotIn("GEMINI_API_KEY", text)

    def test_nav_has_assistant_and_diagnosis(self):
        html = self.farmer().get("/dashboard").get_data(as_text=True)
        self.assertIn("/diagnose", html)
        self.assertIn("/assistant", html)
        self.assertIn("مساعدك الزراعي", html)


class BrowserHelpers(unittest.TestCase):
    """دوال JS المستقلة في voice.js (تقسيم القراءة، اختيار الصوت، دمج النص المسموع)."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("Node غير متوفر")

    def run_js(self, expr):
        script = ("const a = require(process.argv[1]);"
                  "console.log(JSON.stringify(" + expr + "));")
        path = str(ROOT / "app" / "static" / "js" / "voice.js")
        out = subprocess.run(["node", "-e", script, path], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_split_keeps_long_answers_in_order_and_under_limit(self):
        long_answer = ("ازرع الطماطم في الشتا. اروي كل يومين. " * 40).strip()
        chunks = self.run_js("a.splitForSpeech(process.argv[2], 180)".replace("process.argv[2]", json.dumps(long_answer)))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 180 for c in chunks))
        self.assertEqual(" ".join(chunks).replace("  ", " "), " ".join(long_answer.split()))

    def test_clean_removes_emoji_and_symbols_before_reading(self):
        out = self.run_js("a.cleanForSpeech('🌱 مساعدك الزراعي 🔊 اقرأ الصفحة — ✔ 50% - × · صحّة')")
        self.assertEqual(out, "مساعدك الزراعي اقرأ الصفحة 50% صحة")

    def test_clean_removes_tashkeel_and_tatweel(self):
        out = self.run_js("a.cleanForSpeech('مَسَاعِدُكْ الـزراعي')")
        self.assertEqual(out, "مساعدك الزراعي")

    def test_symbol_only_chunks_are_dropped(self):
        out = self.run_js("a.splitForSpeech('🔊 ⏹ — · | ')")
        self.assertEqual(out, [])

    def test_clean_removes_markdown(self):
        out = self.run_js("a.cleanForSpeech('**مهم** جداً # عنوان')")
        self.assertEqual(out, "مهم جدا عنوان")

    def test_voice_selection_prefers_egyptian_then_any_arabic(self):
        voices = [{"lang": "en-US"}, {"lang": "ar-SA"}, {"lang": "ar-EG"}]
        self.assertEqual(self.run_js("a.pickArabicVoice(" + json.dumps(voices) + ").lang"), "ar-EG")
        self.assertEqual(self.run_js("a.pickArabicVoice(" + json.dumps(voices[:2]) + ").lang"), "ar-SA")
        self.assertIsNone(self.run_js("a.pickArabicVoice([{lang:'en-US'}])"))



    def test_page_text_order_drops_repeats_and_blanks(self):
        out = self.run_js("a.orderedTexts(['عنوان', '  ', 'عنوان', 'فقرة   أولى', 'فقرة أولى', 'تعليمات'])")
        self.assertEqual(out, ["عنوان", "فقرة أولى", "تعليمات"])


if __name__ == "__main__":
    unittest.main()


class VoiceWiring(Base):
    """القراءة بالصوت المشتركة متوصلة بالصفحات."""

    def setUp(self):
        super().setUp()
        self.app.config["GEMINI_API_KEY"] = FAKE_KEY

    def farmer(self):
        return self.user("farmer", "farmer@x.com")

    def test_reader_and_voice_script_on_every_public_page(self):
        import re
        c = self.cl()
        for url in ("/", "/market", "/impact", "/login", "/register"):
            html = c.get(url).get_data(as_text=True)
            self.assertIn('id="read-page"', html, url)
            self.assertIn("js/voice.js", html, url)
            self.assertNotIn("js/assistant.js", html, url)



    def test_assistant_reply_has_speak_button_with_text_source(self):
        c = self.farmer()
        with c.session_transaction() as s:
            s["csrf"] = "t"
        with mock.patch.object(gemini, "generate_reply", return_value="ده رد تجريبي"):
            c.post("/assistant/message", data={"text": "سؤال", "_csrf": "t"},
                   content_type="multipart/form-data")
        html = c.get("/assistant").get_data(as_text=True)
        self.assertIn('class="speak-btn"', html)
        self.assertIn("data-speak-scope", html)
        self.assertIn("data-speak-text", html)
        self.assertIn("data-stop-audio", html)

    def test_no_removed_feature_in_static_files(self):
        for f in (ROOT / "app" / "static").rglob("*"):
            if f.is_file():
                text = f.read_text(encoding="utf-8", errors="ignore").lower()
                self.assertNotIn("whatsapp", text, f.name)
                self.assertNotIn("consultation", text, f.name)
                self.assertNotIn("مهندس", text, f.name)


class GeminiSafety(unittest.TestCase):
    def test_errors_are_logged_without_key_or_user_content(self):
        secret_body = json.dumps({"error": {"status": "PERMISSION_DENIED", "message": "x" + FAKE_KEY}}).encode()

        def raise_http(*a, **k):
            raise urllib.error.HTTPError("https://example.test/?key=" + FAKE_KEY, 403, "x", {},
                                         io.BytesIO(secret_body))

        with mock.patch("urllib.request.urlopen", raise_http), \
                self.assertLogs("greenharvest.gemini", level="WARNING") as logs:
            with self.assertRaises(gemini.GeminiError):
                gemini.post_json("https://example.test/x", FAKE_KEY, {"contents": "سر المستخدم"})
        text = "\n".join(logs.output)
        self.assertIn("status=403", text)
        self.assertIn("PERMISSION_DENIED", text)
        self.assertNotIn(FAKE_KEY, text)
        self.assertNotIn("سر المستخدم", text)

    def test_missing_key_warning_at_startup_explains_setup(self):
        with tempfile.TemporaryDirectory() as tmp, \
                self.assertLogs("greenharvest", level="WARNING") as logs:
            from app import create_app
            os.environ.pop("GEMINI_API_KEY", None)
            create_app(os.path.join(tmp, "x.db"), uploads_dir=tmp)
        self.assertTrue(any("GEMINI_API_KEY" in line and ".env" in line for line in logs.output))
