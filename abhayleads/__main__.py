"""Lets both `python -m abhayleads` and the packaged .exe use the same
entry point: no args opens the CRM window, any subcommand runs the CLI.
"""

from .cli import main

if __name__ == "__main__":
    main()
