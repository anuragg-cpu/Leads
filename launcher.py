"""PyInstaller entry point.

Pointing PyInstaller directly at abhayleads/__main__.py breaks it:
when frozen, PyInstaller runs that file as the top-level "__main__"
module with no package context, so its `from .cli import main`
relative import fails at startup ("attempted relative import with no
known parent package"). This tiny script sits outside the package and
uses an absolute import instead, which works whether frozen or not -
packaging/Leads.spec's Analysis points here, not at __main__.py.

Not used when running from source (`python -m abhayleads ...` already
works fine there) - only the .exe build goes through this file.
"""

from abhayleads.cli import main

if __name__ == "__main__":
    main()
