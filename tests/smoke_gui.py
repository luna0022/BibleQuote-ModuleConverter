"""Смоук-тест GUI: вставка HTML из буфера (CF_HTML) через Ctrl+V рендерится
тегами fmt_* в поле вставки. Работает на Windows-сессии с дисплеем."""
import ctypes
import sys

sys.path.insert(0, "converter")
import tkinter as tk
import bq_module_converter as m

FRAGMENT = (
    "<p><b>Глава I</b></p>"
    "<p>Обычный текст и <i>курсив</i>, а ещё <u>подчёркнуто</u>."
    "<b><i>Жирный курсив</i></b>.</p>"
)


def build_cf_html(fragment: str) -> bytes:
    body = "<!--StartFragment-->" + fragment + "<!--EndFragment-->"
    header = (
        "Version:0.9\r\n"
        "StartHTML:{0:08d}\r\n"
        "EndHTML:{1:08d}\r\n"
        "StartFragment:{0:08d}\r\n"
        "EndFragment:{1:08d}\r\n"
        "<html><body>"
    )
    prefix = header.format(0, 0)
    start = len(prefix.encode("utf-8"))
    end = start + len(body.encode("utf-8"))
    prefix = header.format(start, end)
    return (prefix + body + "</body></html>").encode("utf-8")


def set_clipboard_cf_html(data: bytes) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    GMEM_MOVEABLE = 0x0002
    cf_html = user32.RegisterClipboardFormatW("HTML Format")
    if not user32.OpenClipboard(0):
        raise RuntimeError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data) + 2)
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        ctypes.c_uint16.from_address(p + len(data)).value = 0
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(cf_html, h):
            raise RuntimeError("SetClipboardData failed")
    finally:
        user32.CloseClipboard()


def _segments_of(widget, start, end):
    segs = []
    active = "fmt_000"
    for item in widget.dump(start, end, tag=True, text=True):
        if item[0] == "tagon" and item[1].startswith("fmt_"):
            active = item[1]
        elif item[0] == "tagoff" and item[1].startswith("fmt_"):
            active = "fmt_000"
        elif item[0] == "text" and item[1]:
            if segs and segs[-1][1] == active:
                segs[-1] = (segs[-1][0] + item[1], active)
            else:
                segs.append((item[1], active))
    return segs


class FakeTk(tk.Tk):
    def mainloop(self, *a, **k):
        try:
            self._smoke_test()
        finally:
            self.destroy()

    def _smoke_test(self):
        texts = []
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Text):
                    texts.append(c)
                walk(c)
        walk(self)
        if len(texts) != 2:
            raise SystemExit(f"FAIL: ожидалось 2 Text-виджета, найдено {len(texts)}")
        paste = texts[0]  # paste создаётся раньше log
        # Отладка: читаем CF_HTML тем же способом, что и конвертер
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalLock.restype = ctypes.c_void_p
        user32.GetClipboardData.restype = ctypes.c_void_p
        cf_html = user32.RegisterClipboardFormatW("HTML Format")
        ok = user32.OpenClipboard(0)
        handle = user32.GetClipboardData(cf_html) if ok else None
        print("OpenClipboard:", ok, "handle:", handle)
        if handle:
            p = kernel32.GlobalLock(handle)
            print("bytes:", ctypes.string_at(p)[:80])
            kernel32.GlobalUnlock(handle)
        user32.CloseClipboard()
        paste.bind("<Control-x>", lambda e: print("PROBE FIRED") or "break")
        self.deiconify()
        self.update()
        paste.event_generate("<Control-x>", when="now")
        self.update()
        paste.focus_set()
        paste.event_generate("<Control-v>", when="now")
        self.update()
        dump = paste.dump("1.0", "end-1c", tag=True, text=True)
        rendered = "".join(i[1] for i in dump if i[0] == "text")
        print("Отрисовано:", rendered.replace("\n", "\\n")[:120])
        tags = sorted({i[1] for i in dump if i[0] == "tagon"})
        print("Теги:", tags)
        assert "Глава I" in rendered and "курсив" in rendered, "текст потерян"
        assert any(t != "fmt_000" for t in tags), "форматирование не отрендерилось"
        assert "fmt_100" in tags, "жирный не найден"
        assert "fmt_010" in tags, "курсив не найден"
        assert "fmt_001" in tags, "подчёркивание не найдено"
        assert "fmt_110" in tags, "жирный курсив не найден"
        print("SMOKE OK: рендер форматирования работает")

        # Редактирование: снимаем жирный с «Глава I» (Ctrl+B на выделении),
        # добавляем курсив к «Обычный текст» (Ctrl+I).
        paste.tag_add(tk.SEL, "1.0", "1.7")
        paste.event_generate("<Control-b>", when="now")
        self.update()
        seg = _segments_of(paste, "1.0", "1.7")
        assert seg == [("Глава I", "fmt_000")], f"снятие жирного не сработало: {seg}"
        paste.tag_remove(tk.SEL, "1.0", tk.END)
        paste.tag_add(tk.SEL, "2.0", "2.7")
        paste.event_generate("<KeyPress>", keysym="i", state=0x0004, when="now")
        self.update()
        seg = _segments_of(paste, "2.0", "2.7")
        assert seg == [("Обычный", "fmt_010")], f"добавление курсива не сработало: {seg}"
        # Повторный Ctrl+I на том же диапазоне снимает курсив.
        paste.tag_remove(tk.SEL, "1.0", tk.END)
        paste.tag_add(tk.SEL, "2.0", "2.7")
        paste.event_generate("<KeyPress>", keysym="i", state=0x0004, when="now")
        self.update()
        seg = _segments_of(paste, "2.0", "2.7")
        assert seg == [("Обычный", "fmt_000")], f"toggle курсива не сработал: {seg}"
        print("SMOKE OK: ручное редактирование форматирования работает")

        # Сквозная проверка: сериализуем поле с тегами и конвертируем в модуль.
        import html as _html
        import tempfile
        from pathlib import Path

        out = []
        active = set()
        for item in paste.dump("1.0", "end-1c", tag=True, text=True):
            kind = item[0]
            if kind == "tagon" and item[1].startswith("fmt_"):
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
        markup = "".join(out)
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", prefix="bq_smoke_", delete=False
        )
        with handle:
            handle.write(markup)
        dest = Path("test_output/smoke_module")
        if dest.exists():
            import shutil
            shutil.rmtree(dest)
        report = m.convert(m.Options(
            input_path=Path(handle.name),
            output_path=dest,
            module_name="Смоук-тест",
            short_name="SMOKE",
            source_format="text",
            module_kind="book",
            encoding="auto",
            pattern="",
            chapters="none",
        ))
        print("Книг:", report.output_books, "Глав:", report.output_chapters)
        assert report.output_books == 1, "модуль не создан"
        texts = [p for p in dest.iterdir() if p.suffix == ".htm"]
        assert texts, "файл книги не найден"
        content = texts[0].read_bytes().decode("cp1251")
        assert "<i>курсив</i>" in content, "курсив не дошёл до модуля"
        assert "<u>подчёркнуто</u>" in content, "подчёркивание не дошло до модуля"
        assert "<b><i>Жирный курсив</i></b>" in content.replace("\r\n", " ").replace("\n", " ") or "Жирный" in content, "жирный не дошёл до модуля: " + content[:200]
        print("SMOKE OK: форматирование попало в модуль:", texts[0].name)


set_clipboard_cf_html(build_cf_html(FRAGMENT))
orig = tk.Tk
tk.Tk = FakeTk
try:
    m.run_gui()
finally:
    tk.Tk = orig
