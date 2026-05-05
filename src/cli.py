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


if __name__ == "__main__":
    cli()
