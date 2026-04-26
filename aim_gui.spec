# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['aim_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pandas/numpy が lazy import されるため明示的に列挙
        'pandas',
        'numpy',
        'aim_csv_to_md',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 不要な大型ライブラリを除外してバンドルサイズ削減
        'matplotlib', 'scipy', 'PIL', 'IPython',
        'unittest', 'test', 'pydoc', 'doctest',
        'tkinter.test',
        'xmlrpc', 'email', 'html', 'http',
        'urllib3', 'distutils', 'setuptools',
    ],
    noarchive=False,
    optimize=2,          # __pycache__ 最適化レベル2
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # COLLECT に binaries を任せる
    name='AiM CSV to MD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,              # シンボルストリップで起動高速化
    upx=False,               # numpy/pandas に UPX は逆効果
    console=False,           # macOS .app はコンソール不要
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',     # Apple Silicon ネイティブ
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    upx_exclude=[],
    name='AiM CSV to MD',
)

app = BUNDLE(
    coll,
    name='AiM CSV to MD.app',
    icon='icon.icns',
    bundle_identifier='com.local.aimcsvtomd',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'CFBundleShortVersionString': '1.0.0',
    },
)
