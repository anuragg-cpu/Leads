# PyInstaller spec for Abhay Leads.
#
# Build (from the repo root, inside your venv, on Windows):
#   pyinstaller packaging/Leads.spec
#
# Output: dist/Leads/Leads.exe (folder build - faster to launch than
# --onefile, and avoids some antivirus false-positives that --onefile
# builds are prone to). Zip the whole dist/Leads folder if you want to
# move it to another machine.

import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(project_root / "launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "config" / "config.example.yaml"), "config"),
        # `abhayleads serve`'s web UI loads these from disk at runtime
        # (Jinja2Templates/StaticFiles), not via Python import, so
        # PyInstaller's static analysis never finds them on its own -
        # without this, the built exe's `serve` command starts fine but
        # every web UI page 500s with a template/file-not-found error.
        (str(project_root / "abhayleads" / "server" / "templates"), "abhayleads/server/templates"),
        (str(project_root / "abhayleads" / "server" / "static"), "abhayleads/server/static"),
    ],
    hiddenimports=[
        # uvicorn/starlette pick these implementations at runtime via
        # importlib rather than a plain top-level import, so PyInstaller's
        # static analysis misses them - without these, a packaged `serve`
        # can fail to start (or fail on its first request) with an
        # ImportError/ModuleNotFoundError these names don't hint at well.
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "multipart",
        "anyio._backends._asyncio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Leads",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep a console so `Leads.exe fetch` etc. print output
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Leads",
)
