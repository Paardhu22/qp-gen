import os
import sys
import django

sys.path.append("/home/paardhu/Projects/qp-gen/backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from services.openai_service import get_openai_client
from services.answer_script_service import SYSTEM_PROMPT, _build_user_prompt

client = get_openai_client()
prompt = _build_user_prompt(1, "Test question", 1, "SHORT_ANSWER", None, None, "No source material")

try:
    print(f"Model: {settings.OPENAI_MODEL}")
    completion = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1000,
    )
    print("Success:", completion.choices[0].message.content)
except Exception as e:
    import traceback
    traceback.print_exc()
