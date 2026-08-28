"""允许 `python -m sourcing ...` 直接调用 CLI。"""

from .cli import cli

if __name__ == "__main__":
    cli()
