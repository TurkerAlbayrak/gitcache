"""Enable ``python -m devcache`` as an entry point."""

from devcache.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
