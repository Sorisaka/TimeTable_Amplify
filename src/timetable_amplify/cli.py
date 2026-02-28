"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .errors import NoFeasibleSolutionError, UserVisibleError
from .io.availability_csv_parser import parse_google_form_csv
from .io.availability_editable import write_editable_availability
from .io.priority_editable import write_priority_json
from .logging_utils import setup_logging
from .output import format_timetable_for_stdout
from .pipeline import run_pipeline


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optimize a live timetable with Fixstars Amplify")
    parser.add_argument("--config", default="configs/default_config.json", help="Path to JSON config")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and detailed unexpected errors")
    parser.add_argument(
        "--generate-editable-from-csv",
        help="Parse Google Form-like CSV and generate editable intermediate JSON",
    )
    parser.add_argument(
        "--editable-out",
        default="input/generated_availability_editable.json",
        help="Output path for generated editable intermediate JSON",
    )
    parser.add_argument(
        "--emit-priority-json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Emit priority.json alongside editable output (default: true)",
    )
    parser.add_argument(
        "--priority-json",
        help="Priority JSON path for generation/read. Default: <editable_dir>/priority.json",
    )
    parser.add_argument(
        "--overwrite-priority",
        action="store_true",
        help="Overwrite existing priority.json during CSV->editable generation",
    )
    return parser


def _default_priority_path(editable_out: Path) -> Path:
    return editable_out.parent / "priority.json"


def main() -> int:
    args = build_arg_parser().parse_args()

    try:
        if args.generate_editable_from_csv:
            parsed = parse_google_form_csv(Path(args.generate_editable_from_csv))
            editable_out = Path(args.editable_out)
            write_editable_availability(parsed, editable_out)
            print(f"generated editable file: {editable_out}")

            if args.emit_priority_json:
                priority_out = Path(args.priority_json) if args.priority_json else _default_priority_path(editable_out)
                if priority_out.exists() and not args.overwrite_priority:
                    print(
                        f"priority json exists and was kept: {priority_out} (use --overwrite-priority to replace)",
                        file=sys.stderr,
                    )
                else:
                    write_priority_json(priority_out, [band.name for band in parsed.bands])
                    print(f"generated priority file: {priority_out}")

            for warning in parsed.warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            return 0

        config = load_config(args.config)
        setup_logging(config.logging, debug=args.debug)
        logging.getLogger(__name__).info("Starting timetable optimization")

        result, artifacts = run_pipeline(args.config, priority_json_path=args.priority_json)
        print(format_timetable_for_stdout(result))
        print(f"artifacts: {artifacts}")
        return 0
    except NoFeasibleSolutionError as exc:
        print(f"NO_SOLUTION: {exc}", file=sys.stderr)
        return 0
    except UserVisibleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # Final safety net.
        logger = logging.getLogger(__name__)
        if args.debug:
            logger.exception("Unexpected error")
            print(f"ERROR: unexpected failure detail={exc.__class__.__name__}: {exc}", file=sys.stderr)
        else:
            logger.error("Unexpected error: %s", exc.__class__.__name__)
            print(
                "ERROR: unexpected failure occurred. Re-run with --debug for detail.",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
