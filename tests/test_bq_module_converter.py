from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bq_module_converter", ROOT / "converter" / "bq_module_converter.py"
)
assert SPEC is not None and SPEC.loader is not None
converter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = converter
SPEC.loader.exec_module(converter)


class BQModuleConverterTests(unittest.TestCase):
    def options(self, source: Path, output: Path, **kwargs) -> converter.Options:
        values = {
            "input_path": source,
            "output_path": output,
            "module_name": "Тестовый модуль",
            "short_name": "TEST",
            "source_format": "auto",
            "module_kind": "auto",
            "encoding": "auto",
            "pattern": "",
        }
        values.update(kwargs)
        return converter.Options(**values)

    def test_native_module_book_qty_is_normalized_and_spaces_in_name_are_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "bad_module"
            output = base / "fixed_module"
            source.mkdir()
            ini = (
                "BibleName = Повреждённый модуль\r\n"
                "BibleShortName = BAD\r\n"
                "Bible = N\r\n"
                "ChapterSign = <h2>\r\n"
                "VerseSign = <p>\r\n"
                "BookQty = 3\r\n"
                "PathName = one.htm\r\n"
                "FullName = Первая книга\r\n"
                "ShortName = Один\r\n"
                "ChapterQty = 1\r\n"
                "PathName = two .htm\r\n"
                "FullName = Вторая книга\r\n"
                "ShortName = Два\r\n"
                "ChapterQty = broken\r\n"
                "PathName = missing.htm\r\n"
                "FullName = Отсутствующая\r\n"
                "ShortName = Miss\r\n"
                "ChapterQty = 1\r\n"
            )
            (source / "bibleqt.ini").write_bytes(ini.encode("cp1251"))
            (source / "one.htm").write_bytes(
                "<h2></h2>\r\n<p>1 Первая строка".encode("cp1251")
            )
            (source / "two .htm").write_bytes(
                "<h2></h2>\r\n<p>1 Вторая строка".encode("cp1251")
            )

            report = converter.convert(self.options(source, output))

            ini_bytes = (output / "bibleqt.ini").read_bytes()
            self.assertNotIn(b"\r\r\n", ini_bytes)
            self.assertEqual(ini_bytes.count(b"\r\n"), ini_bytes.count(b"\n"))
            result_ini = ini_bytes.decode("cp1251")
            self.assertIn("BookQty = 2", result_ini)
            self.assertNotIn("DefaultEncoding", result_ini)
            self.assertIn("DesiredFontCharset = 204", result_ini)
            self.assertIn("FullName = Вторая книга", result_ini)
            self.assertIn("ChapterQty = 1", result_ini)
            self.assertEqual(2, report.output_books)
            self.assertEqual(1, report.skipped_books)
            self.assertEqual(2, len(list(output.glob("book-*.htm"))))
            content = (output / "book-0002.htm").read_text(encoding="cp1251")
            self.assertIn("charset=windows-1251", content)
            self.assertIn("Вторая строка", content)
            self.assertTrue((output / "conversion-report.txt").is_file())

    def test_plain_text_with_bible_references_is_grouped_into_books_and_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "references.txt"
            output = base / "references_module"
            source.write_text(
                "Бытие 1:1 В начале сотворил Бог небо и землю.\n"
                "Бытие 1:2 Земля же была безвидна и пуста.\n"
                "Ин 1:1 В начале было Слово.\n",
                encoding="utf-8",
            )

            report = converter.convert(self.options(source, output))

            result_ini = (output / "bibleqt.ini").read_text(encoding="cp1251")
            self.assertIn("BookQty = 2", result_ini)
            self.assertIn("FullName = Бытие", result_ini)
            self.assertIn("FullName = Иоанна", result_ini)
            first = (output / "book-0001.htm").read_text(encoding="cp1251")
            second = (output / "book-0002.htm").read_text(encoding="cp1251")
            self.assertIn("В начале сотворил Бог", first)
            self.assertIn("Земля же была безвидна", first)
            self.assertIn("В начале было Слово", second)
            self.assertEqual(2, report.output_books)
            self.assertEqual(2, report.output_chapters)

    def test_usfm_file_is_converted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "sample.usfm"
            output = base / "usfm_module"
            source.write_text(
                "\\id GEN\n\\h Бытие\n\\mt Бытие\n"
                "\\c 1\n\\v 1 В начале сотворил Бог небо и землю.\n"
                "\\v 2 Земля же была безвидна и пуста.\n",
                encoding="utf-8",
            )

            report = converter.convert(self.options(source, output, source_format="usfm"))

            result_ini = (output / "bibleqt.ini").read_text(encoding="cp1251")
            self.assertIn("BookQty = 1", result_ini)
            self.assertIn("FullName = Бытие", result_ini)
            content = (output / "book-0001.htm").read_text(encoding="cp1251")
            self.assertIn("В начале сотворил Бог", content)
            self.assertEqual(1, report.output_books)
            self.assertEqual(1, report.output_chapters)

    def test_refuses_nonempty_output_and_never_modifies_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "book.txt"
            output = base / "occupied"
            source.write_text("Простая книга", encoding="utf-8")
            output.mkdir()
            (output / "existing.txt").write_text("не трогать", encoding="utf-8")
            original = source.read_bytes()

            with self.assertRaises(converter.ConversionError):
                converter.convert(self.options(source, output))

            self.assertEqual(original, source.read_bytes())
            self.assertEqual("не трогать", (output / "existing.txt").read_text(encoding="utf-8"))

    def test_custom_reference_pattern_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "custom.txt"
            output = base / "custom_module"
            source.write_text(
                "Книга А|1|1|Первый стих\nКнига А|1|2|Второй стих\n",
                encoding="utf-8",
            )
            pattern = r"^\s*(?P<book>[^|]+)\|(?P<chapter>\d+)\|(?P<verse>\d+)\|(?P<text>.*)$"

            report = converter.convert(self.options(source, output, pattern=pattern))

            result_ini = (output / "bibleqt.ini").read_text(encoding="cp1251")
            self.assertIn("BookQty = 1", result_ini)
            content = (output / "book-0001.htm").read_text(encoding="cp1251")
            self.assertIn("Первый стих", content)
            self.assertIn("Второй стих", content)
            self.assertEqual(1, report.output_books)


if __name__ == "__main__":
    unittest.main()
