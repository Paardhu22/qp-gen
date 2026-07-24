import re

families = {
    "OBJECTIVE": {"response_mode": "OBJ", "is_auto_markable": True, "sort_order": 10, "name": "Objective"},
    "DESCRIPTIVE": {"response_mode": "CON", "is_auto_markable": False, "sort_order": 20, "name": "Descriptive"},
    "SOURCE_BASED": {"response_mode": "SRC", "is_auto_markable": False, "sort_order": 30, "name": "Source Based"},
    "VISUAL": {"response_mode": "VIS", "is_auto_markable": False, "sort_order": 40, "name": "Visual"},
    "LANGUAGE": {"response_mode": "LNG", "is_auto_markable": False, "sort_order": 50, "name": "Language"},
    "PRACTICAL": {"response_mode": "PRC", "is_auto_markable": False, "sort_order": 60, "name": "Practical"},
    "STRUCTURAL": {"response_mode": "STRUCT", "is_auto_markable": False, "sort_order": 70, "name": "Structural"}
}

with open("../research.md", "r") as f:
    content = f.read()

table_lines = []
in_table = False
for line in content.split("\n"):
    if line.startswith("| # | ID | Family |"):
        in_table = True
        continue
    if in_table and line.startswith("|---"):
        continue
    if in_table and line.startswith("| ") and "`" in line:
        table_lines.append(line)
    elif in_table and not line.startswith("|"):
        break

types = []
for line in table_lines:
    parts = [p.strip() for p in line.split("|")][1:-1]
    if len(parts) < 7:
        continue
    
    code = parts[1].replace("`", "")
    family = parts[2]
    auto_mark = parts[3]
    needs_stimulus = parts[4]
    container = parts[5]
    
    is_auto = "Yes" in auto_mark
    req_stim = "Yes" in needs_stimulus or "Optional" in needs_stimulus or "Via children" in needs_stimulus
    is_container = "Yes" in container
    
    # Capitalize the name correctly (e.g., MCQ_SINGLE -> Mcq Single)
    name = " ".join([word.capitalize() for word in code.split("_")])
    
    types.append(f"""    {{
        "code": "{code}",
        "name": "{name}",
        "family": "{family}",
        "description": "{name}",
        "is_container": {is_container},
        "requires_stimulus": {req_stim},
        "is_auto_markable": {is_auto}
    }}""")

families_list = []
for k, v in families.items():
    families_list.append(f"""    {{
        "code": "{k}",
        "name": "{v['name']}",
        "response_mode": "{v['response_mode']}",
        "is_auto_markable": {v['is_auto_markable']},
        "sort_order": {v['sort_order']}
    }}""")

print(f"FAMILIES = [\n" + ",\n".join(families_list) + "\n]")
print(f"TYPES = [\n" + ",\n".join(types) + "\n]")
