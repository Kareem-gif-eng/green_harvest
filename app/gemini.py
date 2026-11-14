"""ربط Google Gemini من الخادم فقط.

- المفتاح بيتقري من متغير البيئة GEMINI_API_KEY ومابيتبعتش للمتصفح أبداً.
- مفيش مكتبة إضافية: الطلب بيتبعت بـ urllib من بايثون.
- الدوال بتتقسم لطبقات (بناء الطلب / الإرسال / تفسير الرد) عشان تتختبر من غير إنترنت.
"""
import base64
import json
import logging
import urllib.error
import urllib.request
import time
TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 3
RETRY_DELAYS = (2, 4)
RETRYABLE_HTTP_CODES = (500, 502, 503, 504)
log = logging.getLogger("greenharvest.gemini")

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash"
TIMEOUT_SECONDS = 90
MIME_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}

SYSTEM_PROMPT = """أنت مساعد زراعي خبير بتساعد الفلاحين المصريين. اتكلم بالعامية المصرية البسيطة والودودة،
وكلماتك لازم تكون سهلة لفلاح ممكن يكون قراته محدودة. اتجنب المصطلحات العلمية المعقدة، ولو استخدمت مصطلح اشرحه بكلمة.

مهامك: الإجابة عن المحاصيل وأمراض النبات والآفات والري والتسميد والتربة ومواسم الزراعة والمشاكل الزراعية.
خليك هادي وعملي: ابدأ بخلاصة مباشرة، وبعدها خطوات قصيرة مرتبة لو محتاجة. ماتكررّش السؤال، وماتستخدمش مقدمات طويلة أو كلام تسويقي.

قواعد لازم تلتزم بيها:
1. لو اتبعتلك صور لنبات: حلل الصور وقول المشكلة المحتملة، والأسباب المحتملة، والخطوات العملية اللي ينفذها الفلاح.
2. ماتقولش إن التشخيص مؤكد أبداً. استخدم عبارات زي "غالباً" و"الاحتمال الأكبر" و"ممكن يكون".
3. لو الصور مش كفاية (مش واضحة، أو مش بتوضح الجزء المصاب، أو مش عارف النبات): قول ده بصراحة واطلب صورة أوضح للورقة أو الساق أو الجذر حسب الحالة.
4. لو المشكلة ممكن تكون خطيرة أو بتنتشر بسرعة: انصح الفلاح يتواصل مع الإرشاد الزراعي في منطقته.
5. لو محتاج معلومة عشان ترد بدقة (زي نوع المحصول، عمر النبات، طريقة الري، الأعراض)، اسأل سؤال واحد أو اتنين بسيطين بس.
6. لو مش متأكد من حاجة قولها بصراحة. ماتخترعش.
7. لما تنصح بمبيد أو سماد: قول إنه لازم يتم بعد الرجوع للإرشاد الزراعي، وإن الفلاح يتبع التعليمات المكتوبة على العبوة، وماتنصحش بجرعات خطيرة.
8. رد بإيجاز ووضوح: 3 إلى 6 جمل في الغالب، إلا لو الفلاح طلب تفاصيل. رتّب الخطوات بأرقام بسيطة، وسيب سطر بين الأفكار.
9. فرّق بين المعلومة المؤكدة والاحتمال، وماتخترعش درجات حرارة أو مواعيد أو جرعات لو مش متأكد.
10. لو السؤال مش له علاقة بالزراعة، قول بأدب إنك متخصص في الزراعة بس.
11. لو ناقصك سياق، اسأل سؤالاً واحداً محدداً في نهاية الرد بدل ما تسأل أسئلة كتير مرة واحدة."""


class GeminiError(Exception):
    """خطأ يتعرض للمستخدم بالعربي."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


def build_payload(history, text, images):
    """history: قائمة {role: 'user'|'assistant', text}.
    images: قائمة (ext, bytes). بترجع جسم الطلب الجاهز لـ Gemini."""
    contents = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn["text"]}]})

    parts = [{"text": text or "حلل الصور دي وقولّي المشكلة اللي شايفها."}]
    for ext, data in images:
        parts.append({"inline_data": {
            "mime_type": MIME_BY_EXT[ext],
            "data": base64.b64encode(data).decode("ascii"),
        }})
    contents.append({"role": "user", "parts": parts})

    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1500},
    }


def _google_status(exc):
    """بيقرا حالة الخطأ من رد Google (زي INVALID_ARGUMENT) من غير أي بيانات حساسة."""
    try:
        payload = json.loads(exc.read().decode("utf-8", "replace"))
        status = payload.get("error", {}).get("status", "unknown")
        return str(status)[:60]
    except Exception:  # noqa: BLE001
        return "unknown"


def post_json(url, api_key, body):
    """إرسال الطلب إلى Gemini مع إعادة المحاولة عند الأخطاء المؤقتة."""

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    for attempt in range(MAX_ATTEMPTS):

        try:
            with urllib.request.urlopen(
                req,
                timeout=TIMEOUT_SECONDS
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:

            status_code = exc.code
            google_status = _google_status(exc)

            log.warning(
                "Gemini HTTP error: attempt=%s/%s status=%s google_status=%s",
                attempt + 1,
                MAX_ATTEMPTS,
                status_code,
                google_status,
            )

            # أخطاء مؤقتة من خوادم Google
            if status_code in RETRYABLE_HTTP_CODES:

                if attempt < MAX_ATTEMPTS - 1:
                    delay = RETRY_DELAYS[attempt]

                    log.warning(
                        "Retrying Gemini request in %s seconds...",
                        delay,
                    )

                    time.sleep(delay)
                    continue

                raise GeminiError(
                    "خدمة المساعد عليها ضغط حاليًا. حاول تاني بعد شوية.",
                    503,
                )

            # المفتاح غير صحيح أو غير مفعّل
            if status_code in (400, 401, 403):
                raise GeminiError(
                    "مفتاح خدمة الذكاء الاصطناعي غير صحيح أو غير مفعّل. كلّم المدير.",
                    503,
                )

            # الموديل غير موجود أو غير متاح
            if status_code == 404:
                raise GeminiError(
                    "موديل الذكاء الاصطناعي غير متاح حاليًا. راجع إعدادات الموديل.",
                    503,
                )

            # تجاوز حدود الاستخدام
            if status_code == 429:
                raise GeminiError(
                    "المساعد مشغول جدًا أو تم تجاوز حد الاستخدام. حاول بعد دقيقة.",
                    503,
                )

            raise GeminiError(
                "حصلت مشكلة في خدمة المساعد. حاول تاني بعد شوية.",
                502,
            )

        except (urllib.error.URLError, TimeoutError, OSError) as exc:

            log.warning(
                "Gemini network error: attempt=%s/%s error=%s",
                attempt + 1,
                MAX_ATTEMPTS,
                type(exc).__name__,
            )

            if attempt < MAX_ATTEMPTS - 1:
                delay = RETRY_DELAYS[attempt]

                log.warning(
                    "Retrying Gemini connection in %s seconds...",
                    delay,
                )

                time.sleep(delay)
                continue

            raise GeminiError(
                "الاتصال بخدمة المساعد بطيء حاليًا. حاول تاني بعد شوية.",
                503,
            )

    raise GeminiError(
        "تعذر الحصول على رد من المساعد. حاول مرة أخرى.",
        503,
    )
    """الإرسال الفعلي. بيتعمل mock في الاختبارات."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        log.warning("Gemini HTTP error: status=%s google_status=%s",
                    exc.code, _google_status(exc))
        if exc.code in (400, 403):
            raise GeminiError("مفتاح خدمة الذكاء الاصطناعي غير صحيح أو غير مفعّل. كلّم المدير.", 503)
        if exc.code == 429:
            raise GeminiError("المساعد مشغول جداً دلوقتي. حاول بعد دقيقة.", 503)
        raise GeminiError("حصلت مشكلة في خدمة المساعد. حاول تاني بعد شوية.", 502)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("Gemini network error: %s", type(exc).__name__)
        raise GeminiError("مافيش اتصال بخدمة المساعد دلوقتي. اتأكد من الإنترنت وحاول تاني.", 503)


def parse_reply(data):
    """يستخرج النص من رد Gemini، ويرفع GeminiError لو الرد اتمنع أو فاضي."""
    feedback = data.get("promptFeedback", {})
    if feedback.get("blockReason"):
        raise GeminiError("السؤال ده مش قادر أرد عليه. جرّب تصيغه بطريقة تانية.", 422)
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiError("المساعد مارجعش رد. جرّب تسأل تاني.", 502)
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise GeminiError("المساعد مارجعش رد واضح. جرّب تسأل تاني أو ابعت صورة أوضح.", 502)
    return text


def generate_reply(api_key, model, history, text, images):
    """الدالة اللي بيستدعيها الـ endpoint."""
    url = API_URL.format(model=model or DEFAULT_MODEL)
    body = build_payload(history, text, images)
    return parse_reply(post_json(url, api_key, body))
