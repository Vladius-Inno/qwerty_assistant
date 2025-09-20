#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    return subprocess.call(cmd)


def cmd_test(args: argparse.Namespace) -> int:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    pytest_args = ["pytest"]
    if args.quiet:
        pytest_args.append("-q")
    if args.k:
        pytest_args += ["-k", args.k]
    return run(pytest_args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qwerty-cli", description="Project CLI helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p_test = sub.add_parser("test", help="Run pytest")
    p_test.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (-q)")
    p_test.add_argument("-k", help="Only run tests matching expression")
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

