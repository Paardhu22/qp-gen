import django, os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from services.generation_router import route_and_execute_new_engine

print("Running test...")
payload = route_and_execute_new_engine("Electricity, Acids Bases and Salts, Life Processes, Light", "medium", 10)

questions = []
for sec in payload.get("sections", []):
    questions.extend(sec.get("questions", []))

print(f"\nTEST RESULT:")
print(f"Requested: 10 | Generated: {len(questions)}")
print("\nGenerated Questions Text:")
for idx, q in enumerate(questions):
    print(f"Q{idx+1}: {q['content']}")
    
