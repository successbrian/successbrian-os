```python
"""
PURPOSE: Renders board recommendations in constitutional format.
WHY: Ensures all board output reads as proposals requiring Brian's explicit word,
     neutralizing binding-form language per Constitution Articles 1-2.
CALLED BY: board/harness/main.py, board/test_dryrun.py
NOTES: Strips imperatives. Appends mandatory label. Deterministic formatting.
"""

import re
from datetime import date

# Binding-form language patterns to neutralize per Constitution Art 1
BINDING_PATTERNS = [
    r'\bdecided\b',
    r'\bordered\b',
    r'\bbinding\b',
    r'\bstop everything\b',
    r'\bmust halt\b',
    r'\bmust\s+do\b',
    r'\bshall\s+execute\b',
    r'\bmandatory\b',
    r'\bimperative\b',
]

MANDATORY_LABEL = "Recommendation — requires Brian's word"

def neutralize_binding_language(text: str) -> str:
    """Replace binding-form language with neutral proposal language."""
    neutralized = text
    for pattern in BINDING_PATTERNS:
        neutralized = re.sub(pattern, "proposed", neutralized, flags=re.IGNORECASE)
    return neutralized.strip()

def render_recommendations(seats: list[dict], today: str = None) -> list[str]:
    """
    Render board seats as constitutional recommendations.
    Each output string contains the mandatory label and neutralized content.
    """
    if today is None:
        today = date.today().isoformat()
    
    recommendations = []
    for seat in seats:
        seat_id = seat.get('id', 'unknown')
        content = seat.get('content', '')
        neutralized_content = neutralize_binding_language(content)
        
        # Ensure mandatory label is present
        if MANDATORY_LABEL not in neutralized_content:
            neutralized_content = f"{MANDATORY_LABEL}: {neutralized_content}"
        else:
            neutralized_content = neutralized_content.replace(MANDATORY_LABEL, MANDATORY_LABEL)
            
        recommendations.append(neutralized_content)
        
    return recommendations
```
