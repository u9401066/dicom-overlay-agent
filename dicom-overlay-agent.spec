# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


def optional_tree(source: str, target: str):
    path = Path(source)
    return [(str(path), target)] if path.exists() else []


def optional_file(source: str, target: str):
    path = Path(source)
    return [(str(path), target)] if path.is_file() else []


datas = [
    ("config.yaml", "."),
    ("THIRD_PARTY_NOTICES.md", "."),
    *optional_file("build/package-build-receipt.json", "."),
    *optional_tree("clinical_rules", "clinical_rules"),
    *optional_tree("clinical_knowledge", "clinical_knowledge"),
    *optional_file("build/clinical-knowledge.sqlite", "clinical_knowledge"),
    *optional_tree("openclaw/workspace", "openclaw/workspace"),
    *optional_tree("build/openclaw-runtime/openclaw", "openclaw"),
    # Core 4: bundle the portable Node.js runtime when present so the portable
    # bundle is zero-install. Fetch it with scripts\fetch-node.ps1.
    *optional_file("node/node.exe", "node"),
]

# Keep UPX enabled for direct spec invocations. The release build sets this to
# 0 only when it has recorded an explicit no-UPX baseline receipt.
UPX_ENABLED = os.environ.get("DICOM_OVERLAY_UPX_ENABLED", "1") == "1"

_PIL_AVIF_MODULES = {"PIL.AvifImagePlugin", "PIL._avif"}

hiddenimports = [
    "pythoncom",
    "win32com.client",
    *(
        module
        for module in collect_submodules("PIL")
        if module not in _PIL_AVIF_MODULES
    ),
]

a = Analysis(
    ["src/dicom_overlay/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "imagehash",
        "numpy",
        "scipy",
        "matplotlib",
        "pandas",
        "pytest",
        "_pytest",
        # Build/test-only presentation helpers must never leak into the
        # windowed runtime. The build environment is no-dev too; these are a
        # defense-in-depth boundary if a workstation environment is polluted.
        "rich",
        "pygments",
        "markdown_it",
        "mdurl",
        # The product contract is PNG/JPEG. Pillow's optional AVIF codec adds
        # ~7.5 MiB on Windows and is not used by capture, review, or exports.
        "PIL.AvifImagePlugin",
        "PIL._avif",
        # Core 4: Qt modules the overlay never uses. Dropping them prunes large
        # DLLs (Qt6Pdf, Qt6Qml/Quick, WebEngine) from the bundle.
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtQuick3D",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebChannel",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "PyQt6.QtPositioning",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtDesigner",
        "PyQt6.QtHelp",
        "PyQt6.QtCharts",
        "PyQt6.QtDataVisualization",
        "PyQt6.Qt3DCore",
    ],
    noarchive=False,
    optimize=0,
)

# Core 4: drop heavy binaries/data PyInstaller bundles by default but the overlay
# never loads. opengl32sw.dll is a ~20 MB software OpenGL fallback; clinical
# workstations have real GPUs. Qt6Pdf/Qml/Quick/WebEngine come from transitive
# Qt packaging. Pruning here keeps the bundle lean without touching app code.
_BIN_DROP_NAMES = {"opengl32sw.dll"}
_BIN_DROP_PREFIXES = (
    "Qt6Pdf",
    "Qt6Qml",
    "Qt6Quick",
    "Qt6WebEngine",
    "Qt6WebChannel",
    "Qt6Multimedia",
    "Qt63D",
    "Qt6Charts",
    "Qt6DataVisualization",
    "Qt6Designer",
    "Qt6Sql",
    "Qt6Test",
    "Qt6Bluetooth",
    "Qt6Nfc",
    "Qt6Positioning",
    "Qt6Sensors",
    "Qt6SerialPort",
)
_DATA_DROP_DIR_FRAGMENTS = (
    "PyQt6/Qt6/qml",
    "PyQt6\\Qt6\\qml",
    "PyQt6/Qt6/translations",
    "PyQt6\\Qt6\\translations",
)


def _basename(dest: str) -> str:
    return dest.replace("\\", "/").rsplit("/", 1)[-1]


def _keep_binary(entry) -> bool:
    name = _basename(entry[0])
    normalized = entry[0].replace("\\", "/").casefold()
    folded_name = name.casefold()
    if (
        "/pil/" in f"/{normalized}/"
        and folded_name.startswith("_avif.")
        and folded_name.endswith(".pyd")
    ):
        return False
    if name in _BIN_DROP_NAMES:
        return False
    return not name.startswith(_BIN_DROP_PREFIXES)


def _keep_data(entry) -> bool:
    dest = entry[0].replace("\\", "/")
    return not any(frag.replace("\\", "/") in dest for frag in _DATA_DROP_DIR_FRAGMENTS)


a.binaries = [b for b in a.binaries if _keep_binary(b)]
a.datas = [d for d in a.datas if _keep_data(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DICOMOverlayAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=UPX_ENABLED,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=UPX_ENABLED,
    upx_exclude=[],
    name="DICOMOverlayAgent",
)
