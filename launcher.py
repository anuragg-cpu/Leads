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

import sys

if sys.platform == "win32":
    # packaging/Leads.spec builds Leads.exe windowed (console=False), so
    # double-clicking it to open the GUI never flashes a black cmd
    # window alongside it. But `Leads.exe fetch`/`stats`/etc. still need
    # their output to land somewhere when run from an actual terminal -
    # so if there IS a parent console (invoked from cmd/PowerShell),
    # attach to it and reopen stdio against it. AttachConsole simply
    # fails (returns 0) when there's no parent console to attach to
    # (e.g. launched from Explorer or a taskbar pin), in which case this
    # is a no-op and the GUI opens silently, exactly as before.
    #
    # Known rough edge of this technique (not fixable from here): cmd.exe
    # and PowerShell treat a windowed-subsystem exe as fire-and-forget -
    # they don't wait for it before showing the next prompt, so a CLI
    # command's output can appear a beat after the prompt returns. The
    # output is still correct, just not synchronously ordered. Run it as
    # `start /wait Leads.exe stats` if that ordering matters for a script.
    import ctypes

    ATTACH_PARENT_PROCESS = -1
    if ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        sys.stdout = open("CONOUT$", "w")
        sys.stderr = open("CONOUT$", "w")
        sys.stdin = open("CONIN$", "r")

from abhayleads.cli import main

if __name__ == "__main__":
    main()
