#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Universal converter for BibleQuote native modules and plain text books.

The converter never modifies its input. It creates a normalized native
BibleQuote module in UTF-8 with a consistent book list, chapter metadata,
and a conversion report. The original files stay untouched.
"""

from __future__ import annotations

import argparse
import codecs
import html
import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional

ENCODINGS = {
    "auto": None,
    "utf-8": "utf-8-sig",
    "utf-8-sig": "utf-8-sig",
    "utf-16": "utf-16",
    "windows-1251": "cp1251",
    "cp1251": "cp1251",
    "windows-1252": "cp1252",
    "cp1252": "cp1252",
    "dos-866": "cp866",
    "cp866": "cp866",
    "koi8-r": "koi8-r",
    "iso-8859-1": "iso-8859-1",
}

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text", ".htm", ".html", ".usfm", ".sfm", ".pdf", ".docx"}
BOOK_FIELDS = {"pathname", "fullname", "shortname", "chapterqty"}

CANONICAL_BOOKS = [
    ("Бытие", "Быт", ["genesis", "gen"]),
    ("Исход", "Исх", ["exodus", "exo", "exod"]),
    ("Левит", "Лев", ["leviticus", "lev"]),
    ("Числа", "Числ", ["numbers", "num"]),
    ("Второзаконие", "Втор", ["deuteronomy", "deut"]),
    ("Иисус Навин", "Нав", ["joshua", "josh"]),
    ("Книга Судей", "Суд", ["judges", "judg"]),
    ("Руфь", "Руф", ["ruth", "rut"]),
    ("1-я Царств", "1Цар", ["1 samuel", "1sam"]),
    ("2-я Царств", "2Цар", ["2 samuel", "2sam"]),
    ("3-я Царств", "3Цар", ["1 kings", "1kings"]),
    ("4-я Царств", "4Цар", ["2 kings", "2kings"]),
    ("1-я Паралипоменон", "1Пар", ["1 chronicles", "1chron"]),
    ("2-я Паралипоменон", "2Пар", ["2 chronicles", "2chron"]),
    ("Ездра", "Ездр", ["ezra", "ezr"]),
    ("Неемия", "Неем", ["nehemiah", "neh"]),
    ("Есфирь", "Есф", ["esther", "esth"]),
    ("Иов", "Иов", ["job"]),
    ("Псалтирь", "Пс", ["psalms", "psalm", "ps"]),
    ("Притчи", "Притч", ["proverbs", "prov"]),
    ("Екклезиаст", "Еккл", ["ecclesiastes", "eccl"]),
    ("Песня Песней", "Песн", ["song of songs", "song", "canticles"]),
    ("Исаия", "Ис", ["isaiah", "isa"]),
    ("Иеремия", "Иер", ["jeremiah", "jer"]),
    ("Плач Иеремии", "Плач", ["lamentations", "lam"]),
    ("Иезекииль", "Иез", ["ezekiel", "ezek"]),
    ("Даниил", "Дан", ["daniel", "dan"]),
    ("Осия", "Ос", ["hosea", "hos"]),
    ("Иоиль", "Иоил", ["joel", "joel"]),
    ("Амос", "Ам", ["amos", "amos"]),
    ("Авдий", "Авд", ["obadiah", "obad"]),
    ("Иона", "Ион", ["jonah", "jon"]),
    ("Михей", "Мих", ["micah", "mic"]),
    ("Наум", "Наум", ["nahum", "nah"]),
    ("Аввакум", "Авв", ["habakkuk", "hab"]),
    ("Софония", "Соф", ["zephaniah", "zeph"]),
    ("Аггей", "Агг", ["haggai", "hag"]),
    ("Захария", "Зах", ["zechariah", "zech"]),
    ("Малахия", "Мал", ["malachi", "mal"]),
    ("Матфея", "Мф", ["matthew", "matt", "mt"]),
    ("Марка", "Мк", ["mark", "mr"]),
    ("Луки", "Лк", ["luke", "lk"]),
    ("Иоанна", "Ин", ["john", "jn"]),
    ("Деяния", "Деян", ["acts", "act"]),
    ("Иакова", "Иак", ["james", "jas"]),
    ("1-е Петра", "1Пет", ["1 peter", "1pet"]),
    ("2-е Петра", "2Пет", ["2 peter", "2pet"]),
    ("1-е Иоанна", "1Ин", ["1 john", "1jn"]),
    ("2-е Иоанна", "2Ин", ["2 john", "2jn"]),
    ("3-е Иоанна", "3Ин", ["3 john", "3jn"]),
    ("Иуды", "Иуд", ["jude", "jud"]),
    ("Откровение", "Откр", ["revelation", "rev", "apocalypse"]),
]

BOOK_LOOKUP: dict[str, tuple[str, str]] = {}
for index, (full, short, aliases) in enumerate(CANONICAL_BOOKS, start=1):
    for alias in [full, short, *aliases]:
        BOOK_LOOKUP[unicodedata.normalize("NFKC", alias).casefold()] = (full, short)


class ConversionError(RuntimeError):
    pass


@dataclass
class Options:
    input_path: Path
    output_path: Path
    module_name: str = ""
    short_name: str = ""
    source_format: str = "auto"
    module_kind: str = "auto"
    encoding: str = "auto"
    pattern: str = ""
    keep_on_error: bool = False
    chapters: str = "auto"  # auto | roman | numbers | bold | none


@dataclass
class Book:
    full_name: str
    short_name: str
    source_path: Optional[Path] = None
    source_file_name: str = ""
    chapters: list[str] = field(default_factory=list)
    declared_chapter_qty: int = 0
    actual_chapter_qty: int = 0


@dataclass
class Report:
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    input_files: int = 0
    input_books: int = 0
    output_books: int = 0
    output_chapters: int = 0
    skipped_books: int = 0
    copied_assets: int = 0
    headings: list[str] = field(default_factory=list)  # найденные метки глав

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


@dataclass
class IniModule:
    settings: list[tuple[str, str]]
    book_records: list[dict[str, str]]


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_ini_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def decode_bytes(data: bytes, requested: str = "auto", source_name: str = "") -> tuple[str, str]:
    requested_key = normalize_ini_key(requested)
    if requested_key in ENCODINGS and ENCODINGS[requested_key] is not None:
        encoding = ENCODINGS[requested_key] or requested
        return data.decode(encoding, errors="replace"), encoding

    for name, encoding in (
        ("utf-8-sig", "utf-8-sig"),
        ("utf-16", "utf-16"),
    ):
        if data.startswith(codecs.BOM_UTF8) and name == "utf-8-sig":
            return data.decode(encoding, errors="replace"), encoding
        if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) and name == "utf-16":
            return data.decode(encoding, errors="replace"), encoding

    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    # HTML files can declare an ANSI code page in a metatag.
    probe = data[:65536].decode("latin-1", errors="ignore")
    match = re.search(r"charset\s*=\s*['\"]?([A-Za-z0-9_\-]+)", probe, re.IGNORECASE)
    if match:
        name = match.group(1).lower()
        codec = ENCODINGS.get(name, name)
        try:
            return data.decode(codec, errors="replace"), codec
        except (LookupError, UnicodeDecodeError):
            pass

    return data.decode("cp1251", errors="replace"), "cp1251"


def read_text_file(path: Path, encoding: str = "auto") -> tuple[str, str]:
    return decode_bytes(path.read_bytes(), encoding, path.name)


def strip_html_markup(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return html.unescape(normalize_spaces(value))


def escape_text_paragraphs(value: str) -> str:
    lines = [normalize_spaces(line) for line in value.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(f"<p>{html.escape(line, quote=False)}</p>" for line in lines)


def ensure_html(content: str, charset: str = "windows-1251") -> str:
    meta = f'<meta http-equiv="Content-Type" content="text/html; charset={charset}">'
    match = re.search(
        r"(?is)<meta\b[^>]*http-equiv\s*=\s*['\"]?content-type['\"]?[^>]*>",
        content,
    )
    if match:
        return content[: match.start()] + meta + content[match.end() :]
    match = re.search(r"(?is)<head\b[^>]*>", content)
    if match:
        insert_at = match.end()
        return content[:insert_at] + "\n" + meta + content[insert_at:]
    match = re.search(r"(?is)<html\b[^>]*>", content)
    if match:
        insert_at = match.end()
        return content[:insert_at] + "\n<head>" + meta + "</head>" + content[insert_at:]
    return "<html>\n<head>\n" + meta + "\n</head>\n<body>\n" + content + "\n</body>\n</html>\n"


def is_comment_line(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith((";", "//", "#")) or (
        stripped.startswith("[") and stripped.endswith("]")
    )


def parse_ini_module(path: Path, encoding: str, report: Report) -> IniModule:
    text, detected = read_text_file(path, encoding)
    report.warning(f"Кодировка bibleqt.ini определена как {detected}.")
    settings: list[tuple[str, str]] = []
    records: list[dict[str, str]] = []
    current: Optional[dict[str, str]] = None
    seen_settings: set[str] = set()

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if is_comment_line(raw_line):
            continue
        if "=" not in raw_line:
            report.warning(
                f"bibleqt.ini, строка {line_number}: пропущена строка без «=»: {raw_line[:80]}"
            )
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        value = value.strip()
        normalized = normalize_ini_key(key)
        if normalized in BOOK_FIELDS:
            if normalized == "pathname":
                current = {"pathname": value}
                records.append(current)
            elif current is not None:
                current[normalized] = value
            else:
                report.warning(
                    f"bibleqt.ini, строка {line_number}: поле {key} встречается до PathName и пропущено."
                )
        else:
            if normalized not in seen_settings:
                settings.append((key, value))
                seen_settings.add(normalized)

    return IniModule(settings=settings, book_records=records)


def get_setting(module: IniModule, name: str, default: str = "") -> str:
    wanted = normalize_ini_key(name)
    for key, value in module.settings:
        if normalize_ini_key(key) == wanted:
            return value.strip()
    return default


def set_setting(settings: list[tuple[str, str]], name: str, value: str) -> list[tuple[str, str]]:
    wanted = normalize_ini_key(name)
    result: list[tuple[str, str]] = []
    replaced = False
    for key, old_value in settings:
        if normalize_ini_key(key) == wanted:
            if not replaced:
                result.append((key, value))
                replaced = True
        else:
            result.append((key, old_value))
    if not replaced:
        result.append((name, value))
    return result


def normalize_module_file_name(name: str) -> str:
    # BibleQuote modules sometimes contain accidental spaces immediately
    # before the extension: "58 .htm" instead of "58.htm".
    return re.sub(r"\s+(?=\.[^.\\/]+$)", "", name)


def build_file_lookup(directory: Path, report: Report) -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    try:
        files = [path for path in directory.rglob("*") if path.is_file()]
    except OSError as exc:
        raise ConversionError(f"Не удалось прочитать каталог модуля: {exc}") from exc

    for path in files:
        key_exact = str(path.relative_to(directory)).casefold().replace("/", "\\")
        lookup.setdefault(key_exact, path)
        lookup.setdefault(path.name.casefold(), path)
        lookup.setdefault(normalize_module_file_name(path.name).casefold(), path)
        normalized_relative = normalize_module_file_name(key_exact)
        lookup.setdefault(normalized_relative, path)
    return lookup


def resolve_module_file(directory: Path, name: str, lookup: dict[str, Path]) -> Optional[Path]:
    candidates = [
        name,
        normalize_module_file_name(name),
        name.casefold(),
        normalize_module_file_name(name).casefold(),
        normalize_module_file_name(name).lstrip(".\\/"),
    ]
    for candidate in candidates:
        found = lookup.get(candidate.casefold().replace("/", "\\"))
        if found is not None:
            return found
    return None


def count_case_insensitive(haystack: str, needle: str) -> int:
    if not needle:
        return 0
    return len(re.findall(re.escape(needle), haystack, re.IGNORECASE))


def infer_module_names(options: Options, report: Report) -> tuple[str, str]:
    source = options.input_path
    if source.is_dir() and (source / "bibleqt.ini").is_file():
        module = parse_ini_module(source / "bibleqt.ini", options.encoding, Report())
        name = get_setting(module, "BibleName") or source.name
        short = get_setting(module, "BibleShortName") or source.name
        return normalize_spaces(name), normalize_spaces(short) or normalize_spaces(source.name)
    if source.is_file():
        return normalize_spaces(source.stem), source.stem
    return normalize_spaces(source.name), source.name


def safe_output_name(value: str, fallback: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or fallback


def prepare_output_directory(options: Options) -> None:
    source = options.input_path.resolve()
    output = options.output_path.resolve()
    if source == output or output.is_relative_to(source):
        raise ConversionError("Каталог результата не должен совпадать с исходным или находиться внутри него.")
    if output.exists():
        if not output.is_dir():
            raise ConversionError(f"Путь результата занят файлом: {output}")
        if any(output.iterdir()):
            raise ConversionError(f"Каталог результата должен быть пустым: {output}")
    else:
        output.mkdir(parents=True)


def cleanup_output(options: Options) -> None:
    try:
        if options.output_path.exists() and options.output_path.is_dir():
            shutil.rmtree(options.output_path)
    except OSError:
        pass


def convert_native(options: Options, report: Report) -> tuple[list[Book], list[tuple[str, str]]]:
    source_dir = options.input_path
    ini_path = source_dir / "bibleqt.ini"
    module = parse_ini_module(ini_path, options.encoding, report)
    declared_book_qty = get_setting(module, "BookQty", "0")
    if declared_book_qty.isdigit() and int(declared_book_qty) != len(module.book_records):
        report.warning(
            f"BookQty={declared_book_qty}, но описано книг: {len(module.book_records)}. "
            "В результате будет записано фактическое количество."
        )

    lookup = build_file_lookup(source_dir, report)
    books: list[Book] = []
    resolved_sources: set[Path] = set()

    for index, record in enumerate(module.book_records, start=1):
        declared_name = record.get("pathname", "")
        full_name = normalize_spaces(record.get("fullname", ""))
        short_name = normalize_spaces(record.get("shortname", ""))
        if not declared_name:
            report.warning(f"Книга {index}: отсутствует PathName, запись пропущена.")
            report.skipped_books += 1
            continue
        resolved = resolve_module_file(source_dir, declared_name, lookup)
        if resolved is None:
            report.warning(
                f"Книга {index} «{full_name or declared_name}»: файл не найден ({declared_name}), запись пропущена."
            )
            report.skipped_books += 1
            continue
        resolved_sources.add(resolved.resolve())
        if normalize_module_file_name(declared_name) != declared_name:
            report.warning(
                f"Книга {index}: «{declared_name}» найдена как «{resolved.name}», имя нормализовано."
            )
        try:
            content, detected = read_text_file(resolved, "auto")
        except OSError as exc:
            report.warning(f"Книга {index} «{full_name or declared_name}»: не удалось прочитать файл: {exc}")
            report.skipped_books += 1
            continue
        chapter_sign = get_setting(module, "ChapterSign", "<h2>")
        actual_qty = count_case_insensitive(content, chapter_sign)
        declared_qty_text = record.get("chapterqty", "0")
        try:
            declared_qty = int(declared_qty_text)
        except ValueError:
            report.warning(
                f"Книга {index} «{full_name or declared_name}»: ChapterQty «{declared_qty_text}» не является числом."
            )
            declared_qty = 0
        chapter_qty = actual_qty if actual_qty > 0 else max(declared_qty, 1)
        books.append(
            Book(
                full_name=full_name or resolved.stem,
                short_name=short_name or full_name or resolved.stem,
                source_path=resolved,
                source_file_name=declared_name,
                chapters=[content],
                declared_chapter_qty=declared_qty,
                actual_chapter_qty=chapter_qty,
            )
        )

    if declared_book_qty.isdigit() and int(declared_book_qty) != len(books):
        report.warning(
            f"После проверки файлов доступно книг: {len(books)} из объявленных {declared_book_qty}."
        )

    settings = list(module.settings)
    # BibleQuote 7.5.0.900's background module scanner fails while reading
    # DefaultEncoding here and then leaves only the first cached modules.
    # The legacy loader defaults to Windows-1251, so the explicit key is
    # unnecessary and must be omitted for compatibility.
    settings = [
        (key, value)
        for key, value in settings
        if normalize_ini_key(key) != normalize_ini_key("DefaultEncoding")
    ]
    settings = set_setting(settings, "BookQty", str(len(books)))
    return books, settings


def detect_usfm(text: str) -> bool:
    sample = "\n".join(text.splitlines()[:100])
    return bool(re.search(r"(?m)^\\(?:id|c|v|h|mt)\b", sample))


def parse_usfm_file(path: Path, encoding: str, report: Report) -> list[Book]:
    text, detected = read_text_file(path, encoding)
    report.input_files += 1
    books: list[Book] = []
    current: Optional[Book] = None
    current_chapter = -1

    def ensure_chapter(chapter_number: int) -> None:
        nonlocal current, current_chapter
        if current is None:
            current = Book(path.stem, path.stem, source_path=path)
            books.append(current)
            current_chapter = -1
        if chapter_number <= 0:
            chapter_number = 1
        while len(current.chapters) < chapter_number:
            current.chapters.append("")
        current_chapter = chapter_number

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tag_match = re.match(r"^\\([A-Za-z]+)(?:\s+(.*))?$", line)
        if not tag_match:
            if current_chapter <= 0:
                ensure_chapter(1)
            current.chapters[current_chapter - 1] += "\n<p>" + html.escape(line, quote=False) + "</p>"
            continue
        tag, value = tag_match.group(1).lower(), tag_match.group(2) or ""
        if tag == "id":
            if current is not None and not current.full_name:
                current.full_name = current.short_name
            current = Book(value.split()[0] if value else f"Книга {len(books) + 1}",
                           value.split()[0] if value else f"К{len(books) + 1}",
                           source_path=path)
            books.append(current)
            current_chapter = -1
        elif tag in {"h", "mt", "mt1", "mt2"}:
            if current is None:
                current = Book(path.stem, path.stem, source_path=path)
                books.append(current)
            if value:
                current.full_name = strip_html_markup(value)
        elif tag == "c":
            number_match = re.search(r"\d+", value)
            ensure_chapter(int(number_match.group(0)) if number_match else len((current or Book('', '')).chapters) + 1)
        elif tag == "v":
            verse_match = re.match(r"\s*(\d+)(?:[-–](\d+))?\s*(.*)$", value)
            if current_chapter <= 0:
                ensure_chapter(1)
            if verse_match:
                verse = verse_match.group(1)
                verse_text = verse_match.group(3)
            else:
                verse = "0"
                verse_text = value
            current.chapters[current_chapter - 1] += (
                f"\n<p><b>{html.escape(verse)}</b> {html.escape(verse_text.strip(), quote=False)}</p>"
            )
        elif tag in {"ide", "rem", "sts", "usfm"}:
            continue
        else:
            value = strip_html_markup(value)
            if current_chapter <= 0:
                ensure_chapter(1)
            if value:
                current.chapters[current_chapter - 1] += "\n<p>" + html.escape(value, quote=False) + "</p>"

    for book in books:
        if not book.full_name:
            book.full_name = book.short_name
        if not book.chapters:
            book.chapters = [""]
        book.actual_chapter_qty = len(book.chapters)
    return books


BOOK_NAME_PATTERN = r"(?:[1-3]\s*)?[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё .\-]*?"
REFERENCE_PATTERNS = [
    re.compile(
        rf"^\s*(?P<book>{BOOK_NAME_PATTERN})\s+(?P<chapter>\d{{1,3}})\s*[:\.]\s*(?P<verse>\d{{1,3}})(?:\s*[-–—]\s*\d{{1,3}})?\s*(?P<text>.*)$",
        re.UNICODE,
    ),
    re.compile(
        rf"^\s*(?P<book>{BOOK_NAME_PATTERN})\s+(?P<chapter>\d{{1,3}})\s+(?P<verse>\d{{1,3}})(?:\s*[-–—]\s*\d{{1,3}})?\s+(?P<text>.*)$",
        re.UNICODE,
    ),
]

CHAPTER_HEADING = re.compile(r"^\s*(?:#{1,6}\s*)?(?:глава|chapter)\s+([0-9]+|[IVXLCDM]+)\s*\.?\s*$", re.IGNORECASE)
VERSE_PREFIX = re.compile(r"^\s*(?:\(?\b([0-9]{1,3}|[IVXLCDM]{1,8})\b\)?[\).:]?\s+)(?=\S)", re.IGNORECASE)
POSSIBLE_BOOK_HEADING = re.compile(r"^\s*(?:#{1,6}\s*)?([A-Za-zА-Яа-яЁё0-9][^!?…]{1,100})$")
STANDALONE_ROMAN = re.compile(r"^\s*([IVXLCDM]{1,7})\s*\.?\s*$")
STANDALONE_NUMBER = re.compile(r"^\s*(\d{1,3})\s*\.?\s*$")
END_PUNCTUATION = tuple(".!?:;,")

# Встроенное HTML-форматирование, которое понимает BibleQuote (и которое
# сохраняется при вставке из Word/браузера и при чтении DOCX/PDF).
INLINE_TAG_RE = re.compile(
    r"</?(?:b|i|u|em|strong|sup|sub|font|span|br|p|div|h[1-6])\b", re.IGNORECASE
)

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(token: str) -> Optional[int]:
    """Преобразовать римскую цифру в число; None если запись некорректна."""
    if not token or any(ch not in ROMAN_VALUES for ch in token):
        return None
    total = 0
    prev = 0
    for ch in reversed(token):
        value = ROMAN_VALUES[ch]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    # отбрасываем неканоничные записи вида IIII или IM
    canonical = int_to_roman(total) if 0 < total <= 3999 else None
    if canonical != token:
        return None
    return total


def int_to_roman(value: int) -> str:
    result = ""
    for numeral, worth in (("M", 1000), ("CM", 900), ("D", 500), ("CD", 400),
                           ("C", 100), ("XC", 90), ("L", 50), ("XL", 40),
                           ("X", 10), ("IX", 9), ("V", 5), ("IV", 4), ("I", 1)):
        while value >= worth:
            result += numeral
            value -= worth
    return result



def canonical_book(value: str) -> Optional[tuple[str, str]]:
    key = unicodedata.normalize("NFKC", value).casefold().strip(" .")
    key = re.sub(r"\s+", " ", key)
    return BOOK_LOOKUP.get(key)


def reference_from_line(line: str, custom_pattern: str = "") -> Optional[re.Match[str]]:
    if custom_pattern:
        try:
            match = re.match(custom_pattern, line)
        except re.error as exc:
            raise ConversionError(f"Недопустимое пользовательское выражение: {exc}") from exc
        if match and all(name in match.groupdict() for name in ("book", "chapter", "verse")):
            return match
    stripped = line.strip()
    if len(stripped) < 7 or not re.search(r"\d\s*[:.]\s*\d", stripped):
        return None
    for pattern in REFERENCE_PATTERNS:
        match = pattern.match(stripped)
        if not match:
            continue
        book = normalize_spaces(match.group("book"))
        if canonical_book(book) is None and (len(book) < 3 or len(book) > 40):
            continue
        return match
    return None


def parse_reference_text(path: Path, text: str, options: Options, report: Report) -> list[Book]:
    grouped: dict[str, Book] = {}
    order: list[str] = []
    fallback_book = Book(path.stem, path.stem, source_path=path)
    current_book = fallback_book
    grouped[path.stem.casefold()] = fallback_book
    order.append(path.stem.casefold())

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        match = reference_from_line(line, options.pattern)
        if match is None:
            current_book.chapters.append(html.escape(normalize_spaces(strip_html_markup(line)), quote=False))
            continue
        book_name = normalize_spaces(match.group("book"))
        chapter_number = int(match.group("chapter"))
        verse_number = match.group("verse")
        verse_text = match.groupdict().get("text") or ""
        canonical = canonical_book(book_name)
        full_name, short_name = canonical or (book_name, book_name)
        key = full_name.casefold()
        if key not in grouped:
            grouped[key] = Book(full_name, short_name, source_path=path)
            order.append(key)
        current_book = grouped[key]
        while len(current_book.chapters) < chapter_number:
            current_book.chapters.append("")
        paragraph = f"<p><b>{html.escape(verse_number)}</b> {html.escape(normalize_spaces(strip_html_markup(verse_text)), quote=False)}</p>"
        current_book.chapters[chapter_number - 1] = (
            current_book.chapters[chapter_number - 1] + "\n" + paragraph
        )
        report.input_files += 0  # счётчик файлов увеличивается один раз ниже

    books = [grouped[key] for key in order]
    books = [book for book in books if any(chapter.strip() for chapter in book.chapters)]
    for book in books:
        book.chapters = [chapter.strip() or "<p></p>" for chapter in book.chapters]
        book.actual_chapter_qty = len(book.chapters)
    return books


def parse_generic_text(
    path: Path,
    text: str,
    options: Options,
    report: Report,
    marked_lines: Optional[set[int]] = None,
    page_edge_lines: Optional[set[int]] = None,
) -> list[Book]:
    """Разбор произвольного текста в одну книгу с главами.

    Главы определяются по: явным «Глава N»/«# Заголовок» (всегда), одиноким
    римским цифрам и числам (только по порядку), жирным/крупным строкам
    (по скорингу). Режим выбирается options.chapters.
    marked_lines — номера строк (0-based), выделенных жирным/крупным шрифтом
    (DOCX/PDF); page_edge_lines — первые/последние строки страниц PDF
    (там одинокие числа — обычно номера страниц).
    """
    book = Book(path.stem, path.stem, source_path=path)
    in_html = path.suffix.lower() in {".htm", ".html"}
    marked_lines = marked_lines or set()
    page_edge_lines = page_edge_lines or set()
    mode = options.chapters
    current_chapter: list[str] = []
    current_title: list[str] = []
    expected_number = 1  # ожидаемый номер следующей найденной главы
    lines = text.splitlines()

    def flush_chapter() -> None:
        nonlocal current_chapter
        if current_chapter:
            if in_html:
                book.chapters.append("\n".join(current_chapter))
            else:
                # Строки-разметка (<h2>..., <p><b>... или вставленный HTML с
                # <b>/<i>/<u>) не экранируем: иначе BibleQuote не найдёт метки
                # ChapterSign/VerseSign, а форматирование потеряется.
                parts = []
                for item in current_chapter:
                    if item.lstrip().startswith("<") or INLINE_TAG_RE.search(item):
                        parts.append(item)
                    elif item.strip():
                        parts.append(
                            f"<p>{html.escape(normalize_spaces(strip_html_markup(item)), quote=False)}</p>"
                        )
                book.chapters.append("\n".join(parts))
            current_chapter = []

    def start_numbered_chapter(number: int, label: str, line_index: int) -> None:
        nonlocal expected_number
        flush_chapter()
        expected_number = number + 1
        current_title.append(f"Глава {number}")
        current_chapter.append(f"<h2>Глава {number}</h2>")
        report.headings.append(f"строка {line_index + 1}: Глава {number} ({label})")

    def start_titled_chapter(title: str, line_index: int) -> None:
        flush_chapter()
        title = normalize_spaces(strip_html_markup(title))
        current_title.append(title)
        current_chapter.append(f"<h2>{html.escape(title, quote=False)}</h2>")
        report.headings.append(f"строка {line_index + 1}: {title} (заголовок)")

    for line_index, raw_line in enumerate(lines):
        line = raw_line.rstrip()
        stripped = line.strip()
        # все проверки ведём по тексту без HTML-разметки, чтобы теги
        # форматирования не мешали определению глав и стихов
        plain = strip_html_markup(stripped) if INLINE_TAG_RE.search(stripped) else stripped
        if not plain:
            if current_chapter and current_chapter[-1] != "":
                current_chapter.append("")
            continue
        heading = CHAPTER_HEADING.match(plain)
        if heading:
            token = heading.group(1)
            value = int(token) if token.isdigit() else (roman_to_int(token.upper()) or 0)
            start_numbered_chapter(value or expected_number, token, line_index)
            continue
        if plain.startswith("#"):
            start_titled_chapter(normalize_spaces(plain.lstrip("# ")), line_index)
            continue

        # --- эвристики скоринга (одинокие цифры, жирные строки) ---
        if not in_html and mode != "none":
            standalone_value: Optional[int] = None
            label = ""
            if mode in {"auto", "roman"}:
                match = STANDALONE_ROMAN.match(plain)
                if match:
                    value = roman_to_int(match.group(1))
                    if value is not None and value == expected_number:
                        standalone_value = value
                        label = f"римская цифра {match.group(1)}"
            if standalone_value is None and mode in {"auto", "numbers"}:
                match = STANDALONE_NUMBER.match(plain)
                if match:
                    value = int(match.group(1))
                    # одинокое число на краю страницы — скорее номер страницы
                    if value == expected_number and line_index not in page_edge_lines:
                        standalone_value = value
                        label = f"число {value}"
            marked = line_index in marked_lines
            if standalone_value is None and mode in {"auto", "bold"} and marked:
                # жирная/крупная строка: короткая, без финальной пунктуации,
                # отделена пустой строкой (или начало текста)
                short = len(plain) <= 60
                clean_end = not plain.endswith(END_PUNCTUATION)
                surrounded = line_index == 0 or not lines[line_index - 1].strip()
                if short and clean_end and surrounded:
                    start_titled_chapter(plain, line_index)
                    continue
            if standalone_value is not None:
                start_numbered_chapter(standalone_value, label, line_index)
                continue

        # строка со встроенным HTML-форматированием (вставка из Word/браузера)
        # проходит в модуль как есть — BibleQuote отрисует <b>, <i>, <u>
        if not in_html and INLINE_TAG_RE.search(stripped):
            current_chapter.append(line)
            continue

        if in_html:
            current_chapter.append(line)
        else:
            verse = VERSE_PREFIX.match(stripped)
            if verse and not reference_from_line(stripped, options.pattern):
                current_chapter.append(f"<p><b>{html.escape(verse.group(1))}</b> {html.escape(verse.group(0)[verse.end(1):].lstrip(' ).:'), quote=False)}</p>")
            else:
                current_chapter.append(html.escape(normalize_spaces(strip_html_markup(line)), quote=False))

    flush_chapter()
    if not book.chapters:
        if in_html:
            book.chapters = [text]
        else:
            book.chapters = [escape_text_paragraphs(text)]
    elif not book.chapters[0].lstrip().startswith("<h2>") and len(book.chapters) > 1:
        # текст перед первой меткой (вступление, титульный лист) приклеиваем
        # к первой главе — иначе число меток в файле окажется на одну меньше
        # объявленного ChapterQty и последняя глава не откроется
        book.chapters[1] = book.chapters[0] + "\n" + book.chapters[1]
        del book.chapters[0]
    if not book.full_name:
        book.full_name = " ".join(current_title[:1]) or path.stem
    book.actual_chapter_qty = len(book.chapters)
    return [book]



# Подмена кириллицы в некоторых старых PDF: текст хранится как похожие
# латинские/IPA-глифы (файл визуально русский, а извлекается «ɚɩɨɤɪɢɮ»).
# Два варианта глифа на одну букву — документ собран из разных шрифтов.
PDF_SPOOF_MAP = str.maketrans(
    "ȺȻȼȽȾȿɀɁɂɄɅɆɇɈɉɊɋɌɍɎɏɘ"
    "ɐɑɒɗəɚɛɜɝɞɟɠɡɢɣɤɥɦɧɨɩɪɫɬɭɮɯɰɱɲɳɴɵɶɷɸɹ",
    "АБВГДЕЖЗИКЛМНОПРСТУФХЮ"
    "цчшэяабвгдежзийклмнопрстуфхцчшщъыьэюя",
)


def looks_like_pdf_spoof(text: str) -> bool:
    """True, если текст похож на подменённую кириллицу (много IPA-глифов,
    настоящей кириллицы почти нет)."""
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 100:
        return False
    spoofed = sum(1 for ch in letters if "Ⱥ" <= ch <= "ɹ")
    cyrillic = sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ")
    return spoofed > len(letters) * 0.3 and cyrillic < len(letters) * 0.1


def extract_pdf_text(path: Path, report: Report) -> tuple[str, set[int], set[int]]:
    """Извлечь текст из PDF через pypdf (доступен в поставке Python).

    Возвращает (текст, края_страниц, крупный_шрифт):
    - края страниц — номера первых/последних непустых строк каждой страницы
      (там одинокие числа — обычно номера страниц, не главы);
    - крупный шрифт — номера строк, набранных заметно крупнее основного текста
      (кандидаты в заголовки). Жирный и курсив сохраняются тегами <b>/<i>."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ConversionError(
            "Для чтения PDF нужен пакет pypdf. Установите: pip install pypdf"
        ) from exc
    reader = PdfReader(str(path))
    pages: list[str] = []
    all_lines: list[str] = []
    page_edge_lines: set[int] = set()
    big_fragments: list[str] = []
    for page in reader.pages:
        fragments: list[tuple[str, float, bool, bool]] = []

        def visitor(text_fragment, _cm, _tm, font_dict, font_size) -> None:
            if text_fragment and text_fragment.strip():
                base_font = str((font_dict or {}).get("/BaseFont", ""))
                fragments.append(
                    (
                        text_fragment,
                        float(font_size or 0),
                        "bold" in base_font.lower(),
                        "italic" in base_font.lower() or "oblique" in base_font.lower(),
                    )
                )

        try:
            clean_text = page.extract_text() or ""
            page.extract_text(visitor_text=visitor)
        except Exception as exc:
            report.warning(f"{path.name}: страница не прочитана: {exc}")
            continue
        # накладываем жирный/курсив на чистый текст по совпадению фрагментов
        # (самостоятельная сборка строк из фрагментов теряет переносы)
        styled_parts: list[str] = []
        position = 0
        for frag, _size, bold, italic in fragments:
            index = clean_text.find(frag, position)
            if index < 0:
                index = clean_text.find(frag)
            if index < 0:
                continue
            styled_parts.append(clean_text[position:index])
            chunk = frag
            if italic:
                chunk = f"<i>{chunk}</i>"
            if bold:
                chunk = f"<b>{chunk}</b>"
            styled_parts.append(chunk)
            position = index + len(frag)
        styled_parts.append(clean_text[position:])
        page_text = "".join(styled_parts)
        pages.append(page_text)
        page_lines = [ln for ln in page_text.splitlines() if ln.strip()]
        if page_lines:
            page_edge_lines.add(len(all_lines))  # первая строка страницы
            all_lines.extend(page_lines)
            page_edge_lines.add(len(all_lines) - 1)  # последняя строка страницы
        else:
            all_lines.extend(page_text.splitlines())
        sizes = sorted(size for _frag, size, _b, _i in fragments)
        if len(sizes) >= 4 and sizes[-1] > sizes[len(sizes) // 2] * 1.15:
            median = sizes[len(sizes) // 2]
            for frag, size, _b, _i in fragments:
                if size > median * 1.15 and len(frag.strip()) >= 4:
                    big_fragments.append(normalize_spaces(frag.strip()))
    text = "\n\n".join(pages).strip()
    if not text:
        raise ConversionError(
            f"{path.name}: в PDF не извлечён текст — возможно, это скан без текстового слоя."
        )
    if looks_like_pdf_spoof(text):
        fixed = text.translate(PDF_SPOOF_MAP)
        report.warning(
            f"{path.name}: текст PDF был закодирован латинскими «двойниками» кириллицы; "
            f"восстановлена русская кодировка."
        )
        text = fixed
        big_fragments = [frag.translate(PDF_SPOOF_MAP) for frag in big_fragments]
    # переводим крупные фрагменты в номера строк итогового текста
    big_lines: set[int] = set()
    if big_fragments:
        wanted = {normalize_spaces(strip_html_markup(frag)) for frag in big_fragments}
        for index, ln in enumerate(text.splitlines()):
            norm = normalize_spaces(strip_html_markup(ln.strip()))
            if norm and norm in wanted:
                big_lines.add(index)
    return text, page_edge_lines, big_lines


def extract_docx_text(path: Path) -> tuple[str, set[int]]:
    """Извлечь текст из DOCX через python-docx. Заголовки оформляются как '# ...',
    чтобы конвертер разбил документ на главы. Возвращает (текст, жирные строки) —
    номера строк, полностью набранных жирным (кандидаты в заголовки)."""
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise ConversionError(
            "Для чтения DOCX нужен пакет python-docx. Установите: pip install python-docx"
        ) from exc
    document = docx.Document(str(path))
    lines: list[str] = []
    bold_lines: set[int] = set()

    def styled_run(run) -> str:
        """Текст пробега с сохранением форматирования, понятного BibleQuote."""
        chunk = run.text
        if not chunk:
            return ""
        if run.underline:
            chunk = f"<u>{chunk}</u>"
        if run.italic:
            chunk = f"<i>{chunk}</i>"
        if run.bold:
            chunk = f"<b>{chunk}</b>"
        return chunk

    for paragraph in document.paragraphs:
        raw = "".join(styled_run(run) for run in paragraph.runs) or paragraph.text
        text = normalize_spaces(strip_html_markup(raw))
        if not text:
            lines.append("")
            continue
        runs = [run for run in paragraph.runs if run.text.strip()]
        if runs and all(run.bold for run in runs):
            bold_lines.add(len(lines))
        style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
        if style_name.startswith("heading") or style_name.startswith("заголовок"):
            level_match = re.search(r"(\d+)", style_name)
            level = int(level_match.group(1)) if level_match else 1
            lines.append("#" * min(level, 6) + " " + raw)
        else:
            lines.append(raw)
    return "\n".join(lines), bold_lines


def parse_plain_file(path: Path, options: Options, report: Report) -> list[Book]:
    report.input_files += 1
    ext = path.suffix.lower()
    if options.source_format == "pdf" or (options.source_format == "auto" and ext == ".pdf"):
        text, page_edges, big_lines = extract_pdf_text(path, report)
        return parse_generic_text(path, text, options, report, marked_lines=big_lines, page_edge_lines=page_edges)
    if options.source_format == "docx" or (options.source_format == "auto" and ext == ".docx"):
        text, bold_lines = extract_docx_text(path)
        return parse_generic_text(path, text, options, report, marked_lines=bold_lines)
    text, detected = read_text_file(path, options.encoding)
    if options.source_format == "usfm" or (options.source_format == "auto" and ext in {".usfm", ".sfm"}):
        return parse_usfm_file(path, options.encoding, report)
    if options.source_format == "text":
        return parse_generic_text(path, text, options, report)
    reference_books = parse_reference_text(path, text, options, report)
    if len(reference_books) > 1 or any(book.full_name != path.stem for book in reference_books):
        return reference_books
    return parse_generic_text(path, text, options, report)


def collect_plain_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    result = [
        path
        for path in input_path.iterdir()
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS and path.name.lower() != "bibleqt.ini"
    ]
    return sorted(result, key=lambda path: path.name.casefold())


def convert_plain(options: Options, report: Report) -> tuple[list[Book], list[tuple[str, str]]]:
    files = collect_plain_files(options.input_path)
    if not files:
        raise ConversionError("Не найдено текстовых файлов для преобразования.")
    books: list[Book] = []
    for path in files:
        try:
            books.extend(parse_plain_file(path, options, report))
        except UnicodeError as exc:
            report.warning(f"Не удалось декодировать {path.name}: {exc}")
    if not books:
        raise ConversionError("Не удалось распознать ни одной книги.")
    name, short = infer_module_names(options, report)
    settings: list[tuple[str, str]] = [
        ("BibleName", options.module_name or name),
        ("BibleShortName", options.short_name or short),
        ("Copyright", ""),
        ("Bible", "N"),
        ("OldTestament", "N"),
        ("NewTestament", "N"),
        ("Apocrypha", "N"),
        ("ChapterZero", "N"),
        ("Alphabet", "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"),
        ("DesiredFontCharset", "204"),
        ("HTMLFilter", "<a </a> <font </font> <br> <sup </sup> <table </table> <tr </tr> <td </td> <img"),
        ("Categories", "|Конвертированные модули|"),
        ("ChapterSign", "<h2>"),
        ("VerseSign", "<p>"),
        ("BookQty", str(len(books))),
        ("ModuleCompiler", "BQModuleConverter 1.0"),
    ]

    canonical_count = sum(1 for book in books if book.full_name.casefold() in BOOK_LOOKUP)
    if options.module_kind == "bible" or (
        options.module_kind == "auto" and canonical_count >= 40
    ):
        settings = set_setting(settings, "Bible", "Y")
        old_count = sum(1 for book in books[:39] if book.full_name.casefold() in BOOK_LOOKUP)
        new_count = sum(1 for book in books[39:66] if book.full_name.casefold() in BOOK_LOOKUP)
        settings = set_setting(settings, "OldTestament", "Y" if old_count >= 30 else "N")
        settings = set_setting(settings, "NewTestament", "Y" if new_count >= 20 else "N")
    return books, settings


# Дореволюционная кириллица (ѣ, і, ѳ, ѵ и т.п.) не влезает в Windows-1251.
# При необходимости приводим её к современным буквам — это лучше, чем «?».
OLD_CYRILLIC_MAP = str.maketrans(
    "ѢѣІіѲѳѴѵѶѷѠѡѾѿꙊꙋѮѯѰѱѪѫѬѭѨѩꙖꙗѤѥ",
    "ЕеИиФфИиИиОоОоУуКсПсАаЯяЯяЕеЕе",
)


def encode_windows_lines(text: str, report: Optional[Report] = None, source_name: str = "") -> bytes:
    """Write exact CRLF in the legacy Windows-1251 module format."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "\r\n")
    try:
        return normalized.encode("cp1251")
    except UnicodeEncodeError:
        modernized = normalized.translate(OLD_CYRILLIC_MAP)
        if modernized != normalized:
            if report is not None:
                report.warning(
                    f"{source_name}: дореволюционные буквы (ѣ, і, ѳ, ѵ) приведены к современным."
                )
            try:
                return modernized.encode("cp1251")
            except UnicodeEncodeError:
                normalized = modernized
        if report is not None:
            report.warning(
                f"{source_name} содержит символы вне Windows-1251; они заменены на «?»."
            )
        return normalized.encode("cp1251", errors="replace")


def normalize_sign(value: str, default: str) -> str:
    """Возвращает метку только если она похожа на корректный тег `<...>`.
    Обрезанные значения вида '<DIV align=' или '<P' ломают поиск глав
    в BibleQuote («invalid chapter 1») и заменяются на дефолт."""
    candidate = value.strip()
    if len(candidate) >= 3 and candidate.startswith("<") and candidate.endswith(">"):
        return candidate
    return default


def write_module(options: Options, books: list[Book], settings: list[tuple[str, str]], report: Report) -> None:
    output = options.output_path
    report.input_books = len(books)
    module_name, short_name = infer_module_names(options, report)
    settings = set_setting(settings, "BibleName", options.module_name or module_name)
    settings = set_setting(settings, "BibleShortName", options.short_name or short_name)
    if not get_setting(IniModule(settings, []), "BibleName", "").strip():
        raise ConversionError(
            "Пустое BibleName: такой модуль роняет сканер BibleQuote. "
            "Задайте имя через --name."
        )
    if not get_setting(IniModule(settings, []), "BibleShortName", "").strip():
        raise ConversionError("Пустое BibleShortName: задайте через --short.")
    settings = set_setting(settings, "BookQty", str(len(books)))
    settings = [
        (key, value)
        for key, value in settings
        if normalize_ini_key(key) != normalize_ini_key("DefaultEncoding")
    ]
    settings = set_setting(settings, "DesiredFontCharset", "204")
    settings = set_setting(settings, "ChapterSign", normalize_sign(get_setting(IniModule(settings, []), "ChapterSign", ""), "<h2>"))
    settings = set_setting(settings, "VerseSign", normalize_sign(get_setting(IniModule(settings, []), "VerseSign", ""), "<p>"))

    chapter_sign = get_setting(IniModule(settings, []), "ChapterSign", "<h2>") or "<h2>"
    verse_sign = get_setting(IniModule(settings, []), "VerseSign", "<p>") or "<p>"

    ini_lines: list[str] = []
    for key, value in settings:
        ini_lines.append(f"{key.strip()} = {value.strip()}")
    ini_lines.append("")

    for index, book in enumerate(books, start=1):
        target_name = f"book-{index:04d}.htm"
        target_path = output / target_name
        content = "\n".join(book.chapters) if len(book.chapters) > 1 else book.chapters[0]
        # BibleQuote находит главы только по метке ChapterSign в теле книги
        # (регистрозависимый Pos по строкам). Книга без единой метки не
        # открывается («invalid chapter 1»), поэтому гарантируем заголовок
        # хотя бы одной главы.
        if content.count(chapter_sign) == 0:
            title = book.full_name.strip() or f"Книга {index}"
            content = f"{chapter_sign}{html.escape(title, quote=False)}{chapter_sign.replace('<', '</')}\n" + content
            book.actual_chapter_qty = 1
        # Теги абзацев в старых модулях часто набраны в верхнем регистре (<P>),
        # а VerseSign у нас строчный <p>: регистрозависимый Pos их не увидит.
        # Приводим регистр открывающих/закрывающих P-тегов к нижнему — это
        # безопасно для HTML и делает VerseSign надёжным.
        content = re.sub(r"</?P(?=[ >])", lambda m: m.group(0).lower(), content)
        # BibleQuote собирает текст главы только из строк, содержащих VerseSign.
        # Книга без единого VerseSign дала бы пустую главу и ошибку
        # «Passage not found» при открытии, поэтому вставляем голую метку <p>
        # сразу после первой метки главы — весь текст станет одним стихом.
        if content.count(verse_sign) == 0:
            head, sep, tail = content.partition(chapter_sign)
            close_chapter = chapter_sign.replace("<", "</")
            end = tail.find(close_chapter)
            if sep and end >= 0:
                ch_head = tail[: end + len(close_chapter)]
                body = tail[end + len(close_chapter):]
                content = f"{head}{sep}{ch_head}\n{verse_sign}{body}"
            else:
                content = f"{verse_sign}\n{content}"
        target_path.write_bytes(
            encode_windows_lines(ensure_html(content, "windows-1251"), report, target_name)
        )
        chapter_qty = book.actual_chapter_qty if book.actual_chapter_qty > 0 else len(book.chapters)
        if not book.full_name:
            book.full_name = f"Книга {index}"
        if not book.short_name:
            book.short_name = book.full_name
        ini_lines.extend(
            [
                f"PathName = {target_name}",
                f"FullName = {book.full_name}",
                f"ShortName = {book.short_name}",
                f"ChapterQty = {chapter_qty}",
                "",
            ]
        )
        report.output_chapters += chapter_qty

    ini_path = output / "bibleqt.ini"
    ini_path.write_bytes(encode_windows_lines("\n".join(ini_lines), report, ini_path.name))
    report.output_books = len(books)


def copy_unreferenced_assets(options: Options, report: Report) -> None:
    source_dir = options.input_path
    if not source_dir.is_dir():
        return
    referenced = set()
    if (source_dir / "bibleqt.ini").is_file():
        # Resolve again to know every source file explicitly referenced by PathName.
        dummy = Report()
        module = parse_ini_module(source_dir / "bibleqt.ini", options.encoding, dummy)
        lookup = build_file_lookup(source_dir, dummy)
        for record in module.book_records:
            name = record.get("pathname", "")
            found = resolve_module_file(source_dir, name, lookup) if name else None
            if found is not None:
                referenced.add(found.resolve())
    else:
        referenced = {path.resolve() for path in collect_plain_files(source_dir)}

    for path in source_dir.rglob("*"):
        if not path.is_file() or path.name.casefold() == "bibleqt.ini" or path.resolve() in referenced:
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS:
            continue
        relative = path.relative_to(source_dir)
        target = options.output_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        report.copied_assets += 1


def validate_output(options: Options, report: Report) -> None:
    ini_path = options.output_path / "bibleqt.ini"
    if not ini_path.is_file():
        raise ConversionError("После преобразования не создан bibleqt.ini.")
    check_report = Report()
    module = parse_ini_module(ini_path, "windows-1251", check_report)
    if len(module.book_records) == 0:
        raise ConversionError("В результате нет ни одной книги.")
    for index, record in enumerate(module.book_records, start=1):
        name = record.get("pathname", "")
        if not (options.output_path / name).is_file():
            raise ConversionError(f"В bibleqt.ini указан отсутствующий файл книги {index}: {name}")
        chapter_qty = record.get("chapterqty", "0")
        if not chapter_qty.isdigit() or int(chapter_qty) < 1:
            raise ConversionError(f"У книги {index} недопустимый ChapterQty: {chapter_qty}")
    declared_qty = get_setting(module, "BookQty", "0")
    if not declared_qty.isdigit() or int(declared_qty) != len(module.book_records):
        raise ConversionError("BookQty не совпадает с фактическим числом книг.")


def write_report(options: Options, report: Report) -> None:
    lines = [
        "Отчёт BQModuleConverter",
        "======================",
        f"Источник: {options.input_path}",
        f"Результат: {options.output_path}",
        f"Формат: {options.source_format}",
        f"Кодировка: {options.encoding}",
        "",
        f"Прочитано файлов: {report.input_files}",
        f"Распознано книг до записи: {report.input_books}",
        f"Записано книг: {report.output_books}",
        f"Записано глав: {report.output_chapters}",
        f"Пропущено недоступных книг: {report.skipped_books}",
        f"Скопировано дополнительных файлов: {report.copied_assets}",
        "",
    ]
    if report.headings:
        lines.append(f"Метки глав ({len(report.headings)}):")
        lines.extend(f"- {item}" for item in report.headings)
        lines.append("")
    lines.append("Предупреждения:")
    lines.extend(f"- {item}" for item in report.warnings)
    if report.errors:
        lines.append("")
        lines.append("Ошибки:")
        lines.extend(f"- {item}" for item in report.errors)
    if not report.warnings:
        lines.append("- нет")
    (options.output_path / "conversion-report.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def convert(options: Options) -> Report:
    report = Report()
    options.input_path = options.input_path.resolve()
    options.output_path = options.output_path.resolve()
    source_format = options.source_format
    if source_format == "auto":
        source_format = "native" if options.input_path.is_dir() and (options.input_path / "bibleqt.ini").is_file() else "text"
    if not options.input_path.exists():
        raise ConversionError(f"Источник не найден: {options.input_path}")

    created_output = False
    try:
        if source_format == "native":
            if not options.input_path.is_dir() or not (options.input_path / "bibleqt.ini").is_file():
                raise ConversionError("Нативный формат требует каталог модуля с файлом bibleqt.ini.")
            books, settings = convert_native(options, report)
            report.input_files = max(report.input_files, 1)
        else:
            books, settings = convert_plain(options, report)
        if not books:
            raise ConversionError("Не удалось получить ни одной доступной книги.")
        prepare_output_directory(options)
        created_output = True
        write_module(options, books, settings, report)
        copy_unreferenced_assets(options, report)
        validate_output(options, report)
        write_report(options, report)
        return report
    except Exception:
        if created_output and not options.keep_on_error:
            cleanup_output(options)
        raise


def sanitize_ini_file(ini_path: Path) -> list[str]:
    """Чинит bibleqt.ini: убирает UTF-8 BOM (он ломает чтение BibleName сканером
    BibleQuote и роняет сортировку модулями), при необходимости добавляет
    DefaultEncoding = UTF-8. Возвращает список выполненных действий."""
    actions: list[str] = []
    raw = ini_path.read_bytes()
    data = raw
    if data.startswith(codecs.BOM_UTF8):
        data = data[len(codecs.BOM_UTF8):]
        actions.append("убран UTF-8 BOM")
    # попытка определить, является ли содержимое UTF-8
    is_utf8 = False
    try:
        decoded = data.decode("utf-8")
        # эвристика: много не-ASCII, и они осмысленные UTF-8 последовательности
        non_ascii = sum(1 for ch in decoded if ord(ch) > 127)
        if non_ascii > 0 and data.decode("cp1251", errors="replace") != decoded:
            is_utf8 = True
    except UnicodeDecodeError:
        decoded = data.decode("cp1251", errors="replace")
    low = data.lower()
    if b"bibleshortname" not in low:
        actions.append("ВНИМАНИЕ: не найден BibleShortName")
    if b"biblename" not in low.replace(b"\xef\xbb\xbf", b""):
        actions.append("ВНИМАНИЕ: не найден BibleName")
    if is_utf8 and b"defaultencoding" not in low:
        lines = data.split(b"\n")
        out = None
        for i, ln in enumerate(lines[:30]):
            if ln.lower().startswith(b"bibleshortname"):
                out = lines[:i+1] + [b"DefaultEncoding = UTF-8\r"] + lines[i+1:]
                break
        if out is None:
            out = lines[:1] + [b"DefaultEncoding = UTF-8\r"] + lines[1:]
        data = b"\n".join(out)
        actions.append("добавлен DefaultEncoding = UTF-8")
    if actions:
        ini_path.write_bytes(data)
    return actions


def sanitize_library(root: Path) -> tuple[int, list[str]]:
    """Рекурсивно чинит все bibleqt.ini в каталоге библиотеки."""
    fixed: list[str] = []
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name.lower() == "bibleqt.ini":
            count += 1
            actions = sanitize_ini_file(path)
            if actions:
                fixed.append(f"{path}: {'; '.join(actions)}")
    return count, fixed


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Конвертер модулей BibleQuote и произвольных текстовых книг.",
    )
    parser.add_argument("--input", required=True, help="Файл или каталог источника")
    parser.add_argument("--output", required=True, help="Новый пустой каталог результата")
    parser.add_argument("--name", default="", help="Название итогового модуля")
    parser.add_argument("--short", default="", help="Короткое имя итогового модуля")
    parser.add_argument(
        "--format",
        choices=["auto", "native", "text", "usfm", "pdf", "docx"],
        default="auto",
        help="Формат источника (auto распознаёт PDF и DOCX по расширению файла)",
    )
    parser.add_argument(
        "--kind",
        choices=["auto", "bible", "book"],
        default="auto",
        help="Тип итогового модуля",
    )
    parser.add_argument(
        "--encoding",
        choices=sorted(ENCODINGS.keys()),
        default="auto",
        help="Кодировка источника",
    )
    parser.add_argument(
        "--pattern",
        default="",
        help="Дополнительное регулярное выражение со строками book, chapter, verse, text",
    )
    parser.add_argument("--keep-on-error", action="store_true", help="Не удалять каталог результата при ошибке")
    parser.add_argument(
        "--chapters",
        choices=["auto", "roman", "numbers", "bold", "none"],
        default="auto",
        help="Как определять главы в текстовых источниках: авто (все сигналы), "
        "только римские цифры, только числа, только жирные строки, не разбивать",
    )
    parser.add_argument(
        "--sanitize",
        action="store_true",
        help="Режим починки: обработать --input как каталог библиотеки BibleQuote "
        "(убрать BOM из bibleqt.ini, добавить DefaultEncoding). Остальные ключи не нужны.",
    )
    return parser


def print_report(report: Report) -> None:
    print(f"Прочитано файлов: {report.input_files}")
    print(f"Записано книг: {report.output_books}")
    print(f"Записано глав: {report.output_chapters}")
    if report.headings:
        shown = ", ".join(report.headings[:12])
        more = f" … (+{len(report.headings) - 12})" if len(report.headings) > 12 else ""
        print(f"Метки глав ({len(report.headings)}): {shown}{more}")
    if report.warnings:
        print("\nПредупреждения:")
        for warning in report.warnings:
            print(f"  - {warning}")


def run_cli(argv: Optional[list[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    if args.sanitize:
        root = Path(args.input)
        if not root.is_dir():
            print(f"Ошибка: {root} не является каталогом", file=sys.stderr)
            return 2
        count, fixed = sanitize_library(root)
        print(f"Проверено bibleqt.ini: {count}")
        if fixed:
            print(f"Исправлено файлов: {len(fixed)}")
            for line in fixed:
                print(f"  {line}")
        else:
            print("Проблем не найдено — библиотека уже в порядке.")
        return 0
    options = Options(
        input_path=Path(args.input),
        output_path=Path(args.output),
        module_name=args.name,
        short_name=args.short,
        source_format=args.format,
        module_kind=args.kind,
        encoding=args.encoding,
        pattern=args.pattern,
        keep_on_error=args.keep_on_error,
        chapters=args.chapters,
    )
    try:
        report = convert(options)
    except (ConversionError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    print_report(report)
    print(f"Готово: {options.output_path}")
    return 0


def run_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    root = tk.Tk()
    root.title("Конвертер модулей BibleQuote")
    root.geometry("900x960")
    root.minsize(760, 860)

    input_var = tk.StringVar()
    output_var = tk.StringVar()
    name_var = tk.StringVar()
    short_var = tk.StringVar()
    format_var = tk.StringVar(value="auto")
    kind_var = tk.StringVar(value="auto")
    encoding_var = tk.StringVar(value="auto")
    pattern_var = tk.StringVar()
    chapters_var = tk.StringVar(value="auto")

    main = ttk.Frame(root, padding=12)
    main.pack(fill=tk.BOTH, expand=True)
    main.columnconfigure(1, weight=1)
    main.rowconfigure(8, weight=2)
    main.rowconfigure(9, weight=1)

    def choose_input() -> None:
        filename = filedialog.askopenfilename(
            title="Выберите книгу",
            filetypes=[
                ("Книги и документы", "*.txt *.md *.markdown *.htm *.html *.usfm *.sfm *.pdf *.docx"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx"),
                ("Все файлы", "*.*"),
            ],
        )
        if filename:
            input_var.set(filename)
            if not name_var.get():
                name_var.set(Path(filename).stem)
            if not output_var.get():
                output_var.set(str(Path(filename).with_suffix("").parent / (Path(filename).stem + "_converted")))
            return
        dirname = filedialog.askdirectory(title="Выберите каталог модуля или каталог с книгами")
        if dirname:
            input_var.set(dirname)
            if not name_var.get():
                name_var.set(Path(dirname).name)
            if not output_var.get():
                output_var.set(str(Path(dirname).with_name(Path(dirname).name + "_converted")))

    def choose_output() -> None:
        dirname = filedialog.askdirectory(title="Выберите родительский каталог результата")
        if dirname:
            base = Path(input_var.get()).stem if input_var.get() else "module"
            output_var.set(str(Path(dirname) / (base + "_converted")))

    def show_pattern_help() -> None:
        messagebox.showinfo(
            "Пользовательский формат",
            "Укажите регулярное выражение Python с именованными группами:\n\n"
            "(?P<book>...)\n(?P<chapter>...)\n(?P<verse>...)\n(?P<text>...)\n\n"
            "Группа text необязательна. Пример:\n"
            r"^\s*(?P<book>.+?)\s+(?P<chapter>\d+):(?P<verse>\d+)\s*(?P<text>.*)$",
        )

    paste_holder: list[Path] = []

    def do_convert() -> None:
        log.delete("1.0", tk.END)
        pasted = paste_to_markup().strip()
        temp_input: Optional[Path] = None
        if pasted and not input_var.get().strip():
            # Вставленный текст складываем во временный файл и конвертируем как text.
            import tempfile

            handle = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", prefix="bq_pasted_", delete=False
            )
            with handle:
                handle.write(pasted)
            temp_input = Path(handle.name)
            paste_holder.append(temp_input)
            source = temp_input
            source_format = "text"
        elif input_var.get().strip():
            source = Path(input_var.get())
            source_format = format_var.get()
        else:
            messagebox.showwarning(
                "Конвертер",
                "Укажите источник: выберите файл/папку или вставьте текст в поле ниже.",
            )
            return
        if not output_var.get():
            messagebox.showwarning("Конвертер", "Укажите новый пустой каталог результата.")
            return
        options = Options(
            input_path=source,
            output_path=Path(output_var.get()),
            module_name=name_var.get(),
            short_name=short_var.get(),
            source_format=source_format,
            module_kind=kind_var.get(),
            encoding=encoding_var.get(),
            pattern=pattern_var.get(),
            chapters=chapters_var.get(),
        )
        convert_button.state(["disabled"])
        root.update_idletasks()
        try:
            report = convert(options)
        except Exception as exc:
            log.insert(tk.END, f"Ошибка: {exc}\n")
            messagebox.showerror("Конвертер", str(exc))
        else:
            log.insert(tk.END, "Преобразование завершено.\n\n")
            if temp_input is not None:
                log.insert(tk.END, "Источник: вставленный текст\n")
            else:
                log.insert(tk.END, f"Источник: {options.input_path}\n")
            log.insert(tk.END, f"Результат: {options.output_path}\n")
            log.insert(tk.END, f"Книг: {report.output_books}\n")
            log.insert(tk.END, f"Глав: {report.output_chapters}\n")
            if report.headings:
                shown = "; ".join(report.headings[:10])
                more = f" … (+{len(report.headings) - 10})" if len(report.headings) > 10 else ""
                log.insert(tk.END, f"Метки глав ({len(report.headings)}): {shown}{more}\n")
            if report.warnings:
                log.insert(tk.END, "\nПредупреждения:\n")
                for warning in report.warnings:
                    log.insert(tk.END, f"- {warning}\n")
            messagebox.showinfo("Конвертер", f"Модуль создан:\n{options.output_path}")
        finally:
            convert_button.state(["!disabled"])

    ttk.Label(main, text="Источник:").grid(row=0, column=0, sticky=tk.W, pady=3)
    ttk.Entry(main, textvariable=input_var).grid(row=0, column=1, sticky=tk.EW, pady=3)
    ttk.Button(main, text="Файл / папка…", command=choose_input).grid(row=0, column=2, padx=(8, 0), pady=3)

    ttk.Label(main, text="Результат:").grid(row=1, column=0, sticky=tk.W, pady=3)
    ttk.Entry(main, textvariable=output_var).grid(row=1, column=1, sticky=tk.EW, pady=3)
    ttk.Button(main, text="Выбрать…", command=choose_output).grid(row=1, column=2, padx=(8, 0), pady=3)

    ttk.Label(main, text="Название модуля:").grid(row=2, column=0, sticky=tk.W, pady=3)
    ttk.Entry(main, textvariable=name_var).grid(row=2, column=1, sticky=tk.EW, pady=3)

    ttk.Label(main, text="Короткое имя:").grid(row=3, column=0, sticky=tk.W, pady=3)
    ttk.Entry(main, textvariable=short_var).grid(row=3, column=1, sticky=tk.EW, pady=3)

    ttk.Label(main, text="Формат источника:").grid(row=4, column=0, sticky=tk.W, pady=3)
    format_box = ttk.Combobox(
        main,
        textvariable=format_var,
        values=["auto", "native", "text", "usfm", "pdf", "docx"],
        state="readonly",
        width=18,
    )
    format_box.grid(row=4, column=1, sticky=tk.W, pady=3)

    ttk.Label(main, text="Тип модуля:").grid(row=5, column=0, sticky=tk.W, pady=3)
    kind_box = ttk.Combobox(
        main,
        textvariable=kind_var,
        values=["auto", "bible", "book"],
        state="readonly",
        width=18,
    )
    kind_box.grid(row=5, column=1, sticky=tk.W, pady=3)
    chapters_box = ttk.Combobox(
        main,
        textvariable=chapters_var,
        values=["auto", "roman", "numbers", "bold", "none"],
        state="readonly",
        width=10,
    )
    chapters_box.grid(row=5, column=2, sticky=tk.W, pady=3)
    ttk.Label(main, text="Главы (auto — все сигналы)").grid(row=5, column=2, sticky=tk.W, padx=(120, 0), pady=3)

    ttk.Label(main, text="Кодировка:").grid(row=6, column=0, sticky=tk.W, pady=3)
    encoding_box = ttk.Combobox(
        main,
        textvariable=encoding_var,
        values=sorted(ENCODINGS.keys()),
        state="readonly",
        width=18,
    )
    encoding_box.grid(row=6, column=1, sticky=tk.W, pady=3)

    ttk.Label(main, text="Свой шаблон строки:").grid(row=7, column=0, sticky=tk.W, pady=3)
    ttk.Entry(main, textvariable=pattern_var).grid(row=7, column=1, sticky=tk.EW, pady=3)
    ttk.Button(main, text="?", width=3, command=show_pattern_help).grid(row=7, column=2, padx=(8, 0), pady=3)

    paste_frame = ttk.Labelframe(
        main,
        text=" Или вставьте текст сюда (работает, если поле «Источник» пустое; "
        "вставка из Word/браузера сохраняет жирный, курсив, подчёркивание) ",
    )
    paste_frame.grid(row=8, column=0, columnspan=3, sticky=tk.NSEW, pady=(8, 4))
    paste_frame.columnconfigure(0, weight=1)
    paste_frame.rowconfigure(0, weight=1)
    paste_text = scrolledtext.ScrolledText(paste_frame, height=16, wrap=tk.WORD)
    paste_text.grid(row=0, column=0, sticky=tk.NSEW)

    # WYSIWYG-форматирование в поле вставки: теги fmt_<b><i><u> (цифры 0/1).
    import tkinter.font as tkfont

    _base_font = tkfont.nametofont("TkTextFont")
    _font_cache = {}

    def _fmt_font(bold: bool, italic: bool, underline: bool):
        key = (bold, italic, underline)
        if key not in _font_cache:
            f = tkfont.Font(family=_base_font.cget("family"), size=_base_font.cget("size"))
            if bold:
                f.configure(weight="bold")
            if italic:
                f.configure(slant="italic")
            if underline:
                f.configure(underline=True)
            _font_cache[key] = f
        return _font_cache[key]

    for _b in (0, 1):
        for _i in (0, 1):
            for _u in (0, 1):
                paste_text.tag_configure(
                    f"fmt_{_b}{_i}{_u}", font=_fmt_font(bool(_b), bool(_i), bool(_u))
                )

    class _RichRenderer(HTMLParser):
        """Отрисовывает HTML-фрагмент из буфера обмена в Text с тегами fmt_*."""

        _BLOCK = {"p", "div", "li", "tr", "table", "ul", "ol", "blockquote"}

        def __init__(self, widget):
            super().__init__(convert_charrefs=True)
            self.w = widget
            self.bold = 0
            self.italic = 0
            self.underline = 0
            self.heading = 0

        def _newline(self) -> None:
            if self.w.index("end-1c") != "1.0" and not self.w.get("end-2c", "end-1c").endswith("\n"):
                self.w.insert(tk.INSERT, "\n", "fmt_000")

        def _insert(self, data: str) -> None:
            if not data:
                return
            b = 1 if (self.bold or self.heading) else 0
            i = 1 if self.italic else 0
            u = 1 if self.underline else 0
            self.w.insert(tk.INSERT, data, f"fmt_{b}{i}{u}")

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            if tag in ("b", "strong"):
                self.bold += 1
            elif tag in ("i", "em"):
                self.italic += 1
            elif tag == "u":
                self.underline += 1
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self._newline()
                if tag in ("h1", "h2", "h3"):
                    self.heading += 1
            elif tag in self._BLOCK:
                self._newline()
            elif tag == "br":
                self._newline()

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag in ("b", "strong") and self.bold:
                self.bold -= 1
            elif tag in ("i", "em") and self.italic:
                self.italic -= 1
            elif tag == "u" and self.underline:
                self.underline -= 1
            elif tag in ("h1", "h2", "h3") and self.heading:
                self.heading -= 1
                self._newline()
            elif tag in ("p", "div", "li", "tr"):
                self._newline()

        def handle_data(self, data):
            self._insert(data)

    def paste_to_markup() -> str:
        """Сериализует поле вставки обратно в текст с тегами <b>/<i>/<u>,
        чтобы учитывались и ручные правки после вставки."""
        import html as _html

        out = []
        active = set()
        for item in paste_text.dump("1.0", "end-1c", tag=True, text=True):
            kind = item[0]
            if kind == "tagon":
                if item[1].startswith("fmt_"):
                    active.add(item[1])
            elif kind == "tagoff":
                active.discard(item[1])
            elif kind == "text" and item[1]:
                b = any(t[4] == "1" for t in active)
                i = any(t[5] == "1" for t in active)
                u = any(t[6] == "1" for t in active)
                chunk = _html.escape(item[1])
                if u:
                    chunk = f"<u>{chunk}</u>"
                if i:
                    chunk = f"<i>{chunk}</i>"
                if b:
                    chunk = f"<b>{chunk}</b>"
                out.append(chunk)
        return "".join(out)

    def clipboard_html() -> str:
        """HTML из буфера обмена Windows (CF_HTML), если его туда положили
        Word/браузер. CF_HTML хранится байтами (обычно UTF-8)."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            kernel32.GlobalLock.restype = ctypes.c_void_p
            user32.GetClipboardData.restype = ctypes.c_void_p
            cf_html = user32.RegisterClipboardFormatW("HTML Format")
            if not user32.OpenClipboard(0):
                return ""
            try:
                handle = user32.GetClipboardData(cf_html)
                if not handle:
                    return ""
                pointer = kernel32.GlobalLock(handle)
                if not pointer:
                    return ""
                try:
                    raw_bytes = ctypes.string_at(pointer)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
            raw = ""
            for enc in ("utf-8", "cp1251", "latin-1"):
                try:
                    raw = raw_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            match = re.search(
                r"<!--StartFragment-->(.*?)<!--EndFragment-->", raw, re.S | re.I
            )
            return match.group(1) if match else ""
        except Exception:
            return ""

    def paste_rich(_event=None):
        """Ctrl+V: вставляем HTML из буфера с сохранением форматирования
        (жирный/курсив/подчёркивание отображаются прямо в поле); иначе — текст."""
        fragment = clipboard_html()
        if fragment:
            _RichRenderer(paste_text).feed(fragment)
        else:
            try:
                plain = paste_text.clipboard_get()
            except Exception:
                return "break"
            paste_text.insert(tk.INSERT, plain, "fmt_000")
        return "break"

    paste_text.bind("<Control-v>", paste_rich)
    paste_text.bind("<Control-V>", paste_rich)

    log = scrolledtext.ScrolledText(main, height=7, wrap=tk.WORD)
    log.grid(row=9, column=0, columnspan=3, sticky=tk.NSEW, pady=(12, 8))

    buttons = ttk.Frame(main)
    buttons.grid(row=10, column=0, columnspan=3, sticky=tk.E)

    def do_sanitize() -> None:
        target = Path(input_var.get().strip()) if input_var.get().strip() else filedialog.askdirectory(title="Каталог библиотеки BibleQuote")
        if not target or not Path(target).is_dir():
            messagebox.showwarning("Починка библиотеки", "Укажите в поле «Источник» каталог библиотеки (например, папку Library).")
            return
        try:
            count, fixed = sanitize_library(Path(target))
        except OSError as exc:
            messagebox.showerror("Починка библиотеки", f"Ошибка: {exc}")
            return
        log.configure(state=tk.NORMAL)
        log.insert(tk.END, f"Проверено bibleqt.ini: {count}; исправлено: {len(fixed)}\n")
        for line in fixed:
            log.insert(tk.END, f"  {line}\n")
        if not fixed:
            log.insert(tk.END, "Проблем не найдено — библиотека в порядке.\n")
        log.insert(tk.END, "\n")
        log.configure(state=tk.DISABLED)
        messagebox.showinfo("Починка библиотеки", f"Проверено файлов: {count}\nИсправлено: {len(fixed)}")

    ttk.Button(buttons, text="Починить библиотеку", command=do_sanitize).pack(side=tk.RIGHT, padx=(0, 8))
    convert_button = ttk.Button(buttons, text="Преобразовать", command=do_convert)
    convert_button.pack(side=tk.RIGHT)
    ttk.Button(buttons, text="Закрыть", command=root.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    ttk.Label(
        main,
        text=(
            "Поддерживаются нативные модули BibleQuote (каталог с bibleqt.ini), TXT/MD/HTML, USFM, "
            "PDF (текстовый слой) и DOCX (заголовки Word становятся главами). "
            "Исходные файлы не изменяются; результат должен быть новым пустым каталогом."
        ),
        wraplength=810,
    ).grid(row=11, column=0, columnspan=3, sticky=tk.W, pady=(8, 0))

    root.mainloop()
    return 0


def main() -> int:
    # Windows can give a GUI-launched process a legacy ANSI stdout even when
    # the executable was built without a console. Conversion itself is UTF-8;
    # make diagnostics independent from the current code page.
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) > 1:
        return run_cli()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
