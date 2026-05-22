import os
import re

packages = [
    'analytics', 'board_systems', 'core', 'generation', 'institution', 
    'legacy', 'master', 'orchestration', 'retrieval', 'subjects'
]

pattern_from = re.compile(r'^(\s*from\s+)(' + '|'.join(packages) + r')(\b)', re.MULTILINE)
pattern_import = re.compile(r'^(\s*import\s+)(' + '|'.join(packages) + r')(\b)', re.MULTILINE)

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = pattern_from.sub(r'\1q_instructions.\2\3', content)
    new_content = pattern_import.sub(r'\1q_instructions.\2\3', new_content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed {filepath}")

for root, dirs, files in os.walk('q_instructions'):
    for file in files:
        if file.endswith('.py'):
            process_file(os.path.join(root, file))

print("Done fixing imports.")
