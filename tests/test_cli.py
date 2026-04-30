from __future__ import annotations

from src.main import build_parser


def test_cli_has_module_and_safety_flags():
    parser = build_parser()
    args = parser.parse_args(["--dry-run", "--count", "0"])

    assert args.no_submit is True
    assert args.count == 0

