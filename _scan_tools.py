import re
import glob
import os

tools_dir = 'android_mcp/tools'

for f in sorted(glob.glob(f'{tools_dir}/*.py')):
    filename = os.path.basename(f)
    if filename == '__init__.py':
        continue
    
    with open(f) as fh:
        lines = fh.readlines()
    
    file_tools = []
    for i, line in enumerate(lines):
        if '@mcp.tool()' in line:
            # Find the def line (should be next non-blank, non-comment line)
            for j in range(i+1, min(i+5, len(lines))):
                stripped = lines[j].strip()
                if stripped.startswith('def '):
                    sig = stripped
                    # Read until we find the colon or hit a limit
                    for k in range(j+1, min(j+20, len(lines))):
                        cont = lines[k].strip()
                        sig += cont
                        if sig.count('(') <= sig.count(')'):
                            break
                    file_tools.append((j+1, sig))
                    break
    
    if file_tools:
        print(f"=== {filename} ===")
        for lineno, sig in file_tools:
            print(f"  L{lineno}  {sig}")
        print()