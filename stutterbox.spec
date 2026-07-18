# PyInstaller spec for Stutterbox.
#
#   Build:  uv run python -m PyInstaller stutterbox.spec --noconfirm
#   Output: dist/Stutterbox/  (one folder; Stutterbox.exe + _internal/)
#
# One-folder build: resources/ and migrations/ ship as loose files under
# _internal/ and resolve at runtime via sys._MEIPASS (see core/config.py's
# _bundle_root). Both trees MUST stay in datas below, or a frozen build dies at
# startup: main.py reads resources/theme.qss to theme the app, and the SQLite
# container applies migrations/*.sql on first record. Drop an app icon at
# resources/icons/app.ico and it becomes the exe + window icon; absent one the
# build still succeeds.
from pathlib import Path

_icon_path = Path("resources/icons/app.ico")
_icon = str(_icon_path) if _icon_path.exists() else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("resources", "resources"), ("migrations", "migrations")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Stutterbox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Stutterbox",
)
