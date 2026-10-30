# -*- coding: utf-8 -*-
"""Установка тестового модуля в Library/Books/<catalog>, запуск BibleQuote,
ожидание сканирования, парсинг cached.lst правильным парсером."""
import os, sys, shutil, subprocess, time, re

BQ = r"C:\BibleQuote\BibleQuote.exe"
LIB = r"C:\BibleQuote\Library\Books"
CACHE = r"C:\Users\User\AppData\Roaming\BibleQuote\cached.lst"

def parse_cache():
    with open(CACHE, 'rb') as f:
        text = f.read().decode('utf-8-sig', errors='replace')
    lines = text.splitlines()
    records = []
    cur = []
    for l in lines:
        if l.strip() == '***':
            records.append(cur); cur = []
        else:
            cur.append(l)
    records.append(cur)
    mods = []
    for r in records:
        # пропускаем заголовок ('v5') и пустые хвосты
        if len(r) >= 5 and r[0].strip() == 'v5':
            r = r[2:]  # 'v5', count
        if len(r) >= 5 and r[0].strip().lstrip('-').isdigit():
            mods.append({
                'type': r[0].strip(),
                'full': r[1] if len(r) > 1 else '',
                'short': r[2] if len(r) > 2 else '',
                'path': r[3] if len(r) > 3 else '',
                'fullpath': r[4] if len(r) > 4 else '',
            })
    return mods

def run_test(src_dir, catalog, wait=35):
    dst = os.path.join(LIB, catalog)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src_dir, dst)
    print(f"[+] installed {src_dir} -> {catalog}")
    # запускаем BibleQuote
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    proc = subprocess.Popen([BQ], startupinfo=si)
    time.sleep(wait)
    # корректное закрытие: WM_CLOSE главному окну -> программа пишет cached.lst
    import ctypes
    u32 = ctypes.windll.user32
    hwnd = u32.FindWindowW(None, "BibleQuote")
    if not hwnd:
        # перебираем окна процесса
        hwnd = u32.FindWindowW("TMainForm", None)
    if hwnd:
        u32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    time.sleep(2)
    mods = parse_cache()
    print(f"[=] cache: {len(mods)} modules")
    return mods

if __name__ == '__main__':
    src = sys.argv[1]
    cat = sys.argv[2]
    wait = int(sys.argv[3]) if len(sys.argv) > 3 else 35
    mods = run_test(src, cat, wait)
    for m in mods:
        print('   ', m)
