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
    ],
    hiddenimports=[],
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
