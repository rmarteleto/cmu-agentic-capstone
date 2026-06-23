#!/usr/bin/env python3
"""CLI entry point for the SIG Compliance Assistant.

Usage:
    # single question (web/Teams/Slack-style prompt)
    python main.py ask "Do you encrypt data at rest?"

    # build/update the vector DB from local files
    python main.py ingest --sops data/sops/*.docx --sigs data/sig.txt
"""
from __future__ import annotations

import argparse
import glob as _glob
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def cmd_ask(args):
    from sig_agent.orchestration import Orchestrator
    ans = Orchestrator().answer_question(args.question)
    print(f"\nStatus       : {ans.status.value}")
    print(f"Needs review : {'YES' if ans.needs_human_review else 'no'}")
    print(f"Confidence   : {ans.confidence:.2f}")
    print(f"Answer       :\n{ans.answer or '(no match — abstained; see notes)'}")
    if ans.citations:
        print("Citations    :")
        for c in ans.citations:
            print(f"  - {c.document_id} {c.section} (v{c.version}, {c.effective_date})")
    if ans.notes:
        print(f"Notes        : {ans.notes}")


def cmd_ingest(args):
    from sig_agent.ingestion.pipeline import ingest_sops, ingest_sigs
    if args.sops:
        paths = [p for pat in args.sops for p in (_glob.glob(pat) or [pat])]
        print(f"Indexed {ingest_sops(paths)} SOP passages from {len(paths)} file(s).")
    if args.sigs:
        print(f"Indexed {ingest_sigs(args.sigs)} SIG Q/A pairs from {len(args.sigs)} file(s).")


def main(argv=None):
    p = argparse.ArgumentParser(description="SIG Compliance Assistant (multi-agent)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="answer a single question")
    a.add_argument("question")
    a.set_defaults(func=cmd_ask)

    g = sub.add_parser("ingest", help="rebuild vector DB from local files")
    g.add_argument("--sops", nargs="*", default=None,
                   help="SOP .docx file(s) to index into the SOP corpus")
    g.add_argument("--sigs", nargs="*", default=None,
                   help="historical SIG file(s) (.xlsx or .txt) to index as candidate answers")
    g.set_defaults(func=cmd_ingest)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
