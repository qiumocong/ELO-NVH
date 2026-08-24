$ErrorActionPreference = "Stop"
python -m PyInstaller --clean --noconfirm packaging/yanpu.spec
Write-Host "构建完成: dist\Yanpu\Yanpu.exe"
