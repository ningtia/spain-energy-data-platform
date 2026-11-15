"""Command-line entry point.

Examples:
    energy-ingest ree --dataset market_prices --start 2025-01-01 --end 2025-01-01
    energy-ingest ree --dataset all --start 2018-01-01 --end 2026-11-14
    energy-ingest aemet --start 2018-01-01 --end 2026-11-14
    energy-ingest daily            # last 7 days, all sources (for the scheduler)
    energy-ingest upload           # push data/landing to the Databricks volume
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from energy_platform import config
from energy_platform.dates import parse_date
from energy_platform.http import make_session
from energy_platform.sources import aemet, ree


def _add_range(p: argparse.ArgumentParser) -> None:
    p.add_argument("--start", type=parse_date, required=True, help="YYYY-MM-DD (inclusive)")
    p.add_argument("--end", type=parse_date, required=True, help="YYYY-MM-DD (inclusive)")
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download chunks that already exist in landing (default: skip them)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="energy-ingest")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ree = sub.add_parser("ree", help="Ingest REE REData widgets")
    p_ree.add_argument("--dataset", default="all", choices=["all", *config.REE_DATASETS])
    _add_range(p_ree)

    p_aemet = sub.add_parser("aemet", help="Ingest AEMET daily climate data")
    p_aemet.add_argument("--station", action="append", help="Station id (repeatable)")
    _add_range(p_aemet)

    # AEMET publishes daily climate values with a lag of a few days, so look back a week.
    p_daily = sub.add_parser("daily", help="Incremental run for the last N days (default 7)")
    p_daily.add_argument("--days", type=int, default=7)

    sub.add_parser("upload", help="Upload landing zone to Databricks volume")
    return parser


def run_ree(session, dataset: str, start: date, end: date, skip_existing: bool) -> list[str]:
    names = list(config.REE_DATASETS) if dataset == "all" else [dataset]
    failed: list[str] = []
    for name in names:
        _, f = ree.ingest(session, name, start, end, config.landing_dir(), skip_existing)
        failed += f
    return failed


def run_aemet(start: date, end: date, stations, skip_existing: bool) -> list[str]:
    # AEMET gets its own, more patient session: it answers HTTP 429 when we go too fast.
    session = make_session(total_retries=config.AEMET_RETRIES, backoff=config.AEMET_BACKOFF)
    _, failed = aemet.ingest(
        session, start, end, config.landing_dir(), stations=stations, skip_existing=skip_existing
    )
    return failed


def report(failed: list[str]) -> int:
    log = logging.getLogger("energy_platform")
    if failed:
        log.error("%d chunk(s) failed - re-run the same command to retry only these:", len(failed))
        for f in failed:
            log.error("  %s", f)
        return 1
    log.info("Done. All chunks succeeded.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    session = make_session()

    if args.command == "ree":
        return report(run_ree(session, args.dataset, args.start, args.end, not args.overwrite))
    if args.command == "aemet":
        return report(run_aemet(args.start, args.end, args.station, not args.overwrite))
    if args.command == "daily":
        # Re-pull a trailing window and overwrite: sources revise recent data.
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=args.days - 1)
        failed = run_ree(session, "all", start, end, skip_existing=False)
        failed += run_aemet(start, end, None, skip_existing=False)
        return report(failed)
    if args.command == "upload":
        from energy_platform.upload import upload_landing

        upload_landing(config.landing_dir())
    return 0


if __name__ == "__main__":
    sys.exit(main())
