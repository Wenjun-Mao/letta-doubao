import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from letta_client import Letta

def sync():
    print("Connecting to Letta to fetch latest tools...")
    client = Letta(base_url="http://localhost:8283")
    
    try:
        tools = client.tools.list()
    except Exception as e:
        print(f"Failed to fetch tools. Is the Letta server running? Error: {e}")
        return

    out_file = Path(__file__).resolve().parents[1] / "agent_platform_api" / "letta" / "tools.py"
    
    with out_file.open("w", encoding="utf-8") as f:
        f.write('"""\n')
        f.write('Auto-generated Tool Registry.\n')
        f.write('Run `uv run scripts/sync_tools.py` to rebuild this file if you add custom tools to Letta.\n')
        f.write('"""\n\n')
        f.write('class DefaultTools:\n')
        f.write('    """\n')
        f.write('    Letta Core Tools Constants. \n')
        f.write('    Use nicely with IntelliSense instead of remembering strings.\n')
        f.write('    """\n\n')
        
        # Sort tools alphabetically for easier reading
        tools = sorted(tools, key=lambda x: (x.name or ""))
        
        for t in tools:
            name = t.name or ""
            safe_name = name.upper().replace("-", "_")
            
            description = t.description or ""
            desc = description.strip().replace('\n', ' ')
            # Truncate very long descriptions for the comment
            if len(desc) > 120:
                desc = desc[:117] + "..."
                
            f.write(f'    # {desc}\n')
            f.write(f'    {safe_name} = "{t.name}"\n\n')

    print(f"Success! Exported {len(tools)} tools to {out_file}")

if __name__ == "__main__":
    sync()
