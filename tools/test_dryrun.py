```python
"""
PURPOSE: Mechanical dryrun test for board fix 2/3.
WHY: Verifies constitutional output format, single-channel sink, and DONE-CHECK criteria.
CALLED BY: CI/CD, manual validation
NOTES: Exits 0 on success. Checks for forbidden binding language. Validates nudge_bus count.
"""

import sys
import os
import re
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import run_board_session
from sink import ensure_nudge_bus_table, file_nudge
from renderer import MANDATORY_LABEL

# Track nudge calls for verification
nudge_calls = []

# Patch file_nudge to capture calls
original_file_nudge = None
try:
    from core.nudge import file_nudge as original_file_nudge
except ImportError:
    pass

def mock_file_nudge(content: str, priority: str = 'important', source: str = 'board', dedupe_key: str = '') -> None:
    nudge_calls.append({
        'content': content,
        'priority': priority,
        'source': source,
        'dedupe_key': dedupe_key
    })

# Apply mock
import sink
sink.file_nudge = mock_file_nudge

def run_dryrun() -> bool:
    """Run dryrun and validate all DONE-CHECK criteria."""
    today = date.today().isoformat()
    
    # Run board session
    count = run_board_session(today)
    
    if count == 0:
        print("FAIL: No recommendations emitted.")
        return False
        
    # Check 1: Zero occurrences of binding language (case-insensitive)
    forbidden = ['decided', 'ordered', 'binding', 'stop everything', 'must halt']
    all_content = ' '.join([c['content'] for c in nudge_calls])
    for term in forbidden:
        if re.search(re.escape(term), all_content, re.IGNORECASE):
            print(f"FAIL: Found forbidden term '{term}' in output.")
            return False
            
    # Check 2: Every item contains mandatory label
    for i, call in enumerate(nudge_calls):
        if MANDATORY_LABEL not in call['content']:
            print(f"FAIL: Item {i} missing mandatory label: {MANDATORY_LABEL}")
            return False
            
    # Check 3: Source is 'board' for all
    for i, call in enumerate(nudge_calls):
        if call['source'] != 'board':
            print(f"FAIL: Item {i} source is not 'board': {call['source']}")
            return False
            
    # Check 4: Dedupe key format matches board:YYYY-MM-DD:<seat>
    for i, call in enumerate(nudge_calls):
        if not re.match(r'^board:\d{4}-\d{2}-\d{2}:.+$', call['dedupe_key']):
            print(f"FAIL: Item {i} dedupe_key format invalid: {call['dedupe_key']}")
            return False
            
    # Check 5: Count matches emitted items
    if len(nudge_calls) != count:
        print(f"FAIL: nudge_calls count ({len(nudge_calls)}) != emitted count ({count})")
        return False
        
    print(f"PASS: All {count} recommendations emitted. Zero binding language. Single channel sink verified.")
    return True

if __name__ == '__main__':
    success = run_dryrun()
    sys.exit(0 if success else 1)
```

=== VERIFY ===
```bash
# 1. Run board/test_dryrun.py; it exits 0.
cd ~/workspace/successbrian-os/board && python test_dryrun.py
echo "Exit code: $?"

# 2. Verify zero occurrences of binding language (case-insensitive)
python -c "
import re, sys
sys.path.insert(0, '.')
from test_dryrun import run_dryrun
run_dryrun()
" 2>&1 | grep -iE 'decided|ordered|binding|stop everything|must halt' && echo "FAIL: Binding language found" || echo "PASS: No binding language"

# 3. Verify every emitted item contains "requires Brian's word"
python -c "
import sys
sys.path.insert(0, '.')
from test_dryrun import run_dryrun
run_dryrun()
" 2>&1 | grep -i 'requires Brian'\''s word' > /dev/null && echo "PASS: Mandatory label present" || echo "FAIL: Missing mandatory label"

# 4. Verify nudge_bus count matches emitted items (via mock tracking in test)
python -c "
import sys
sys.path.insert(0, '.')
from test_dryrun import run_dryrun
run_dryrun()
" 2>&1 | grep -i 'PASS' > /dev/null && echo "PASS: Count matches" || echo "FAIL: Count mismatch"

# 5. Full mechanical check (combined)
cd ~/workspace/successbrian-os/board && python test_dryrun.py && echo "ALL DONE-CHECKS PASSED" || echo "DONE-CHECK FAILED"
```
