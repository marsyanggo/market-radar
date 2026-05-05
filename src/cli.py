import click

from configs.settings import settings
from src.logger import logger


@click.group()
def cli() -> None:
    """Market Radar — daily stock screening CLI."""


@cli.command()
def ping() -> None:
    """Sanity check: verify config loads and logger works."""
    logger.info("Market Radar OK")
    click.echo("Market Radar OK")
    click.echo(f"  database_url: {settings.database_url}")
    click.echo(f"  log_dir:      {settings.log_dir}")
    click.echo(f"  alpaca_paper: {settings.is_paper}")
    click.echo(f"  alpaca_feed:  {settings.alpaca_data_feed}")


@cli.group()
def db() -> None:
    """Database commands."""


@db.command("init")
def db_init() -> None:
    """Create or migrate the SQLite schema."""
    from src.db.migrations import init_db

    version = init_db()
    click.echo(f"DB ready at version {version}")


@cli.group()
def screener() -> None:
    """Screener commands."""


@screener.command("run")
@click.option("--most-actives", default=50, help="Top N most-active stocks")
@click.option("--movers", default=25, help="Top N gainers + losers each")
def screener_run(most_actives: int, movers: int) -> None:
    """Fetch most-actives + movers and upsert into `stocks`."""
    from src.alpaca.screener import run_daily_screener

    counts = run_daily_screener(most_actives_top=most_actives, movers_top=movers)
    click.echo(f"screener done: {counts}")


@cli.group()
def indicators() -> None:
    """Technical indicators commands."""


@indicators.command("run")
@click.option("--symbol", multiple=True, help="Specific symbols (default: all in stocks table)")
def indicators_run(symbol: tuple[str, ...]) -> None:
    """Compute and persist EOD technical indicators."""
    from src.indicators.eod import run_eod_indicators

    counts = run_eod_indicators(symbols=list(symbol) if symbol else None)
    click.echo(f"indicators done: {counts}")


@cli.group()
def stream() -> None:
    """Real-time data stream commands."""


@stream.command("trades")
@click.option("--symbol", multiple=True, help="Specific symbols (default: stocks table)")
@click.option("--threshold", default=10000, help="Block size threshold (shares)")
@click.option("--flush", default=5.0, help="Flush interval seconds")
def stream_trades(symbol: tuple[str, ...], threshold: int, flush: float) -> None:
    """Subscribe to live trades via WebSocket. Requires an unused WS slot
    (Alpaca free tier = 1 connection — conflicts with AI_trader price_stream).
    Use `radar poll trades` if the WS slot is taken.
    """
    import asyncio

    from src.alpaca.trades_stream import load_default_symbols, run_block_stream

    symbols = list(symbol) if symbol else load_default_symbols()
    if not symbols:
        click.echo("no symbols — run `radar screener run` first", err=True)
        return
    click.echo(f"streaming blocks for {len(symbols)} symbols (threshold={threshold:,})")
    asyncio.run(run_block_stream(symbols, block_threshold=threshold, flush_interval=flush))


@cli.group()
def poll() -> None:
    """REST polling fallback (works alongside another WS consumer)."""


@poll.command("trades")
@click.option("--symbol", multiple=True, help="Specific symbols (default: stocks table)")
@click.option("--threshold", default=10000, help="Block size threshold (shares)")
@click.option("--interval", default=60.0, help="Poll interval seconds")
@click.option("--cycles", type=int, default=None, help="Stop after N cycles (default: forever)")
def poll_trades(symbol: tuple[str, ...], threshold: int, interval: float, cycles: int | None) -> None:
    """REST polling for block trades — works while AI_trader stream is running."""
    from src.alpaca.trades_poller import run_poller
    from src.alpaca.trades_stream import load_default_symbols

    symbols = list(symbol) if symbol else load_default_symbols()
    if not symbols:
        click.echo("no symbols — run `radar screener run` first", err=True)
        return
    click.echo(
        f"polling {len(symbols)} symbols every {interval}s (threshold={threshold:,})"
    )
    run_poller(symbols, block_threshold=threshold, poll_interval=interval, max_cycles=cycles)


@cli.group()
def news() -> None:
    """News commands."""


@news.command("fetch")
@click.option("--hours", default=24.0, help="Look back this many hours")
@click.option("--limit", default=50, help="Max items per fetch")
@click.option("--symbol", multiple=True, help="Specific symbols (default: all in stocks table)")
def news_fetch(hours: float, limit: int, symbol: tuple[str, ...]) -> None:
    """One-shot news fetch + persist with dedup."""
    from src.alpaca.news import fetch_and_persist, load_default_symbols

    symbols = list(symbol) if symbol else load_default_symbols()
    counts = fetch_and_persist(symbols=symbols, hours_back=hours, limit=limit)
    click.echo(f"news done: {counts}")


@news.command("poll")
@click.option("--interval", default=600.0, help="Poll interval seconds (default 10 min)")
@click.option("--cycles", type=int, default=None, help="Stop after N cycles")
def news_poll(interval: float, cycles: int | None) -> None:
    """Long-running news poller (10 min default cadence)."""
    from src.alpaca.news import load_default_symbols, run_news_poller

    symbols = load_default_symbols()
    run_news_poller(symbols=symbols, poll_interval=interval, max_cycles=cycles)


@cli.group()
def report() -> None:
    """Daily report commands."""


@report.command("run")
@click.option("--no-screener", is_flag=True, help="Skip screener refresh, reuse stocks table")
@click.option("--telegram", is_flag=True, help="Also send report to Telegram")
@click.option("--watchlists", is_flag=True, help="Write proposed watchlists for AI_trader")
def report_run(no_screener: bool, telegram: bool, watchlists: bool) -> None:
    """Run the full daily pipeline and write the markdown report."""
    from src.recommend.daily_pipeline import run_daily_pipeline

    counts = run_daily_pipeline(
        refresh_universe=not no_screener,
        send_telegram=telegram,
        write_watchlists_files=watchlists,
    )
    click.echo(f"report done: {counts}")


@cli.group()
def telegram() -> None:
    """Telegram commands."""


@telegram.command("test")
def telegram_test() -> None:
    """Send a test message to verify bot config."""
    from src.output.telegram import send_message

    ok = send_message("📡 Market Radar — telegram test ✅")
    click.echo(f"telegram test: {'OK' if ok else 'FAILED'}")


if __name__ == "__main__":
    cli()
