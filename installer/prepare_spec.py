# prepare_specs.py
import sys
import os

if len(sys.argv) < 2:
    print("Error: Missing spec file name argument.")
    sys.exit(1)

spec_file = sys.argv[1]
NEW_RECURSION_LIMIT = 5000

if not os.path.exists(spec_file):
    print(f"Error: Spec file not found at {spec_file}")
    sys.exit(1)

try:
    with open(spec_file, 'r+', encoding='utf-8') as f:
        content = f.read()
        f.seek(0, 0)
        f.write(f"import sys; sys.setrecursionlimit({NEW_RECURSION_LIMIT})\n" + content)
except Exception as e:
    print(f"Error modifying spec file: {e}")
    sys.exit(1)

print(f"Successfully modified {spec_file} with recursion limit {NEW_RECURSION_LIMIT}.")
