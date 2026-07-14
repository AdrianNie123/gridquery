"""CLI: uv run python -m nl "your question" (or make ask Q="...")."""

import sys

from nl.interface import ask


def main() -> int:
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        print('usage: uv run python -m nl "your question"', file=sys.stderr)
        return 2
    answer = ask(question)
    print(answer.text)
    u = answer.usage
    if u:
        print(
            f"[tokens: in={u.get('input_tokens')} out={u.get('output_tokens')} "
            f"cache_write={u.get('cache_creation_input_tokens')} "
            f"cache_read={u.get('cache_read_input_tokens')}]",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
