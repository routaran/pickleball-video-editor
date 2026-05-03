"""Entry point for `python -m ml <subcommand>`.

Delegates to the unified CLI dispatcher in ml.cli.
"""

from ml.cli import main

if __name__ == "__main__":
    main()
