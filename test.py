import json
print(json.loads("{}"))
try:
    print(json.loads(""))
except json.JSONDecodeError as e:
    print("JSONDecodeError:", repr(e))
