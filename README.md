# BibleQuote ModuleConverter

Конвертер модулей для BibleQuote 7.x: превращает любые текстовые книги в нативные
модули и чинит библиотеку после «исчезновения» модулей.

## Возможности

- **Почти любые форматы текста → модуль**: TXT, Markdown, HTML, **PDF**, **DOCX** (Word),
  USFM — один файл или папка с файлами; каждый файл становится книгой. Форматирование
  (жирный, курсив, подчёркивание) сохраняется — BibleQuote понимает эти теги.
- **Вставка текста прямо в окно** (GUI): скопированный в Word/браузере текст вставляется
  с форматированием (читается HTML из буфера обмена Windows).
- **Авторазбиение на главы**: явные «Глава N» и «# Заголовок», одинокие римские цифры
  (I, II, III …) и числа — по строгой последовательности, жирные/крупные строки — по
  скорингу; номера страниц PDF не путаются с главами. Режим: `--chapters auto|roman|
  numbers|bold|none` или список «Главы» в окне. Список найденных меток пишется в отчёт.
- **Защита от «шифрованных» PDF**: в некоторых старых изданиях русский текст хранится
  латинскими «двойниками» букв; конвертер распознаёт подмену и восстанавливает
  кириллицу. Дореволюционные буквы (ѣ, і, ѳ, ѵ) приводятся к современным.
- Текст со ссылками вида `Быт. 1:1 ...` группируется по книгам Библии.
- **Нативные модули BibleQuote** (каталог с `bibleqt.ini`): пересборка, исправление
  `BookQty`, разрешение имён файлов с пробелами, нормализация кодировки.
- **USFM** (`.usfm`, `.sfm`) — стандарт библейской разметки.
- **Режим «Починить библиотеку»** (`--sanitize` или кнопка в GUI): убирает UTF-8 BOM
  из всех `bibleqt.ini` (причина бага «исчезающей библиотеки», см. FIX_REPORT.md),
  добавляет `DefaultEncoding = UTF-8`, где нужно.
- Конвертер **никогда не пишет BOM** и отказывается создавать модуль с пустым
  `BibleName`/`BibleShortName` (ровно та комбинация роняла сортировщик BibleQuote).
- Исходные файлы не изменяются — результат пишется в новый пустой каталог
  вместе с отчётом `conversion-report.txt`.

## Запуск

```
# GUI (без аргументов)
BQModuleConverter.exe

# любой текст -> модуль
BQModuleConverter.exe --input "D:\texts\апокрифы.txt" --output "D:\modules\Apocryph" ^
    --name "Апокрифическое наследие" --short Apocryph

# папка с файлами -> модуль
BQModuleConverter.exe --input "D:\texts" --output "D:\modules\MyBooks"

# починка библиотеки после «падения» списка модулей
BQModuleConverter.exe --sanitize "C:\BibleQuote\Library" --output x
```

Ключи: `--format auto|native|text|usfm|pdf|docx`, `--kind auto|bible|book`,
`--chapters auto|roman|numbers|bold|none`,
`--encoding auto|utf-8|windows-1251|...`, `--pattern` (своя регулярка со строками
book/chapter/verse/text), `--keep-on-error`.

## Сборка exe

```
pip install pyinstaller
pyinstaller --noconsole --onefile --clean --name BQModuleConverter converter/bq_module_converter.py
```

## Тесты

```
python -m unittest discover -s tests -v
```

## Состав репозитория

- `converter/bq_module_converter.py` — конвертер (GUI + CLI, один файл).
- `tests/test_bq_module_converter.py` — модульные тесты.
- `FIX_REPORT.md` — диагноз бага «исчезающей библиотеки» и порядок починки.
- `run_test.py` — установка тестового модуля в библиотеку и разбор `cached.lst`.
- `mini_debug5.py` — минимальный отладчик 32-битного BibleQuote.exe (ctypes).
- `make_deliverables.py` — сборка итогового комплекта (архив, exe, модули).
