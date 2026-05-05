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


if __name__ == "__main__":
    cli()
