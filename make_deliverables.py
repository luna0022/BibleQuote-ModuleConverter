from pathlib import Path
from shutil import copy2, rmtree
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source"
OUT = ROOT / "deliverables"
MODULES = OUT / "RepairedModules"
SOURCE_ZIP = OUT / "BibleQuote_7.5.0.900_modified_source.zip"

OUT.mkdir(exist_ok=True)
if MODULES.exists():
    rmtree(MODULES)
MODULES.mkdir(parents=True)

for name in ("ApoJuda", "ApoOccult", "Apocryph"):
    src = ROOT / "test_output" / f"{name}_converted"
    dst = MODULES / name
    dst.mkdir(parents=True)
    for path in src.rglob("*"):
        if path.is_file():
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(path, target)

copy2(ROOT / "build" / "dist" / "BQModuleConverter.exe", OUT / "BQModuleConverter.exe")

notes = """Итоговый комплект BibleQuote 7.5.0.900

Состав:
1. BibleQuote_7.5.0.900_modified_source.zip
   - исправленный загрузчик нативных модулей;
   - кнопка «Convert modules» на панели инструментов;
   - автономный конвертер в каталоге Tools;
   - модульные тесты конвертера.

2. BQModuleConverter.exe
   - автономный EXE-конвертер;
   - поддерживает нативные каталоги BibleQuote, TXT/MD/HTML, USFM;
   - восстанавливает несовпадение BookQty, имена файлов и кодировку;
   - не изменяет исходные файлы, а пишет новый модуль и отчёт.

3. RepairedModules
   - уже исправленные копии ApoJuda, ApoOccult и Apocryph.

Полная сборка BibleQuote.exe
-----------------------------
Проект является VCL-приложением Embarcadero Delphi. В этой системе не найден
компилятор Delphi (dcc32/dcc64) и RAD Studio MSBuild, поэтому основной EXE здесь
не пересобран. На машине с RAD Studio 10.3 или новее выполните из каталога
распакованных исходников:

msbuild BibleQuote.dproj /t:Build /p:Config=Release /p:Platform=Win32

PostBuildEvent автоматически скопирует Tools\\BQModuleConverter.exe в
Output\\Tools\\BQModuleConverter.exe.

Проверка конвертера
-------------------
python -m unittest source/Tests/BQModuleConverterTests.py
"""
(OUT / "README-СБОРКА.txt").write_text(notes, encoding="utf-8")

if SOURCE_ZIP.exists():
    SOURCE_ZIP.unlink()

exclude_dirs = {".git", "Output", "__pycache__"}
exclude_suffixes = {".pyc", ".pyo"}
with ZipFile(SOURCE_ZIP, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(SOURCE.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(SOURCE)
        if any(part in exclude_dirs for part in relative.parts):
            continue
        if path.suffix.lower() in exclude_suffixes:
            continue
        archive.write(path, Path("BibleQuote-7.5.0.900-modified") / relative)

print(SOURCE_ZIP)
print(OUT / "BQModuleConverter.exe")
print(MODULES)
