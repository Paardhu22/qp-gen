import os
import sys
import django

sys.path.append("/home/paardhu/Projects/qp-gen/backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from services.answer_script_service import _generate_single_answer
from services.openai_service import get_openai_client
from django.contrib.auth.models import User

user = User.objects.first()
client = get_openai_client()
question = {"content": "Test question", "type": "SHORT_ANSWER", "marks": 1}
res = _generate_single_answer(client, 1, question, [], user, set())
print("RESULT:", res)
