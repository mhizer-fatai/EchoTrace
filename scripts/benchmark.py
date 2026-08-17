"""Run the EchoTrace memory benchmark against real HydraDB.

Usage:
    python -m scripts.benchmark
    python -m scripts.benchmark --sessions 35 --target-tokens 115000
"""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="EchoTrace memory benchmark")
    parser.add_argument("--sessions", type=int, default=35, help="number of benchmark sessions")
    parser.add_argument("--target-tokens", type=int, default=115_000,
                        help="approximate corpus size in tokens to reach")
    parser.add_argument("--quiet", action="store_true", help="print only the score line")
    args = parser.parse_args()

    from backend.app.engine.benchmark import run_benchmark

    report = run_benchmark(
        session_count=args.sessions,
        target_tokens=args.target_tokens,
        verbose=not args.quiet,
    )
    print(f"\nBENCHMARK SCORE: {report['score']}% across {report['sessions']} sessions, "
          f"~{report['corpus_tokens']:,} tokens, {report['questions_asked']} questions.")
    if report["questions_correct"] < report["questions_asked"]:
        print("One or more questions failed — see DETAIL above.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
