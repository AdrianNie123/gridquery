"""GridQuery natural-language interface (Phase 4).

Translates a natural-language question into a query against the governed
Cube semantic layer, or refuses/clarifies. The LLM (claude-haiku-4-5) only
selects and parameterizes governed metrics; a deterministic validator
enforces the governed surface and code renders every number from Cube
result rows. See docs/plans/phase4.md for the contract.
"""

from dotenv import load_dotenv

# Load ANTHROPIC_API_KEY from a local .env if present. Never committed.
load_dotenv()
