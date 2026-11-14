"""نقطة ربط نموذج الذكاء الاصطناعي للتشخيص.

لو مفيش AI_API_KEY، الدالة بترجع None ومفيش أي نتيجة مزيفة:
الطلب بيفضل "بانتظار نموذج".
"""
import os


def run_ai(image_path, crop, symptoms):
    """ترجع dict فيه result و confidence و advice، أو None."""
    if not os.environ.get("AI_API_KEY"):
        return None
    raise NotImplementedError("ضيف استدعاء مزود النموذج هنا (انظر README).")
