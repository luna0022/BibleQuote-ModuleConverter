import ctypes, struct, sys, time
import ctypes.wintypes as w
from ctypes import windll, c_void_p, byref, sizeof, POINTER

k32 = windll.kernel32
k32.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, c_void_p, c_void_p, w.BOOL, w.DWORD, c_void_p, w.LPCWSTR, c_void_p, c_void_p]
k32.WaitForDebugEvent.argtypes = [c_void_p, w.DWORD]
k32.ContinueDebugEvent.argtypes = [w.DWORD, w.DWORD, w.DWORD]
k32.ReadProcessMemory.argtypes = [w.HANDLE, c_void_p, c_void_p, ctypes.c_size_t, c_void_p]
k32.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k32.OpenThread.restype = w.HANDLE
k32.CloseHandle.argtypes = [w.HANDLE]
k32.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
k32.Wow64GetThreadContext.argtypes = [w.HANDLE, c_void_p]

class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ('cb', w.DWORD), ('lpReserved', w.LPWSTR), ('lpDesktop', w.LPWSTR), ('lpTitle', w.LPWSTR),
        ('dwX', w.DWORD), ('dwY', w.DWORD), ('dwXSize', w.DWORD), ('dwYSize', w.DWORD),
        ('dwXCountChars', w.DWORD), ('dwYCountChars', w.DWORD), ('dwFillAttribute', w.DWORD),
        ('dwFlags', w.DWORD), ('wShowWindow', w.WORD), ('cbReserved2', w.WORD), ('lpReserved2', w.LPVOID),
        ('hStdInput', w.HANDLE), ('hStdOutput', w.HANDLE), ('hStdError', w.HANDLE)]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', w.HANDLE), ('hThread', w.HANDLE),
                ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD)]

class CONTEXT32(ctypes.Structure):
    _fields_ = [
        ('ContextFlags', w.DWORD), ('Dr0', w.DWORD), ('Dr1', w.DWORD), ('Dr2', w.DWORD),
        ('Dr3', w.DWORD), ('Dr6', w.DWORD), ('Dr7', w.DWORD),
        ('FloatSave', ctypes.c_byte * 112),
        ('SegGs', w.DWORD), ('SegFs', w.DWORD), ('SegEs', w.DWORD), ('SegDs', w.DWORD),
        ('Edi', w.DWORD), ('Esi', w.DWORD), ('Ebx', w.DWORD), ('Edx', w.DWORD),
        ('Ecx', w.DWORD), ('Eax', w.DWORD), ('Ebp', w.DWORD), ('Eip', w.DWORD),
        ('SegCs', w.DWORD), ('EFlags', w.DWORD), ('Esp', w.DWORD), ('SegSs', w.DWORD),
        ('Ext', ctypes.c_byte * 512)]

si = STARTUPINFO(); si.cb = sizeof(STARTUPINFO)
pi = PROCESS_INFORMATION()
k32.CreateProcessW(r'C:\BibleQuote\BibleQuote.exe', None, None, None, False, 0x2, None, None, byref(si), byref(pi))
hproc = pi.hProcess

def read_mem(addr, size):
    buf = ctypes.create_string_buffer(size)
    rd = w.ULONG(0)
    k32.ReadProcessMemory(hproc, c_void_p(addr), buf, size, byref(rd))
    return buf.raw[:rd.value]

def read_u32(addr):
    d = read_mem(addr, 4)
    return struct.unpack('<I', d)[0] if len(d) == 4 else None

def read_str(addr):
    # Delphi UnicodeString: ptr -> [data-4]=len, data = UTF-16
    if not addr: return None
    try:
        ln = read_u32(addr - 4)
        if ln is None or ln > 300: return None
        raw = read_mem(addr, ln * 2)
        return raw.decode('utf-16-le', errors='replace')
    except Exception:
        return None

DEBUG_EVENT = ctypes.create_string_buffer(4096)
t0 = time.time()
while time.time() - t0 < 60:
    if not k32.WaitForDebugEvent(byref(DEBUG_EVENT), 3000):
        continue
    code = struct.unpack_from('<I', DEBUG_EVENT, 0)[0]
    pid = struct.unpack_from('<I', DEBUG_EVENT, 4)[0]
    tid = struct.unpack_from('<I', DEBUG_EVENT, 8)[0]
    if code == 1:
        rec = DEBUG_EVENT[16:16+152]
        ex_code = struct.unpack_from('<I', rec, 0)[0]
        if ex_code in (0x40000003, 0x80000003, 0x4000001f, 0x406d1388, 0xEEDFADE):
            k32.ContinueDebugEvent(pid, tid, 0x00010002); continue
        hthr = k32.OpenThread(0x1F03FF, False, tid)
        ctx = CONTEXT32(); ctx.ContextFlags = 0x10000F
        k32.Wow64GetThreadContext(hthr, byref(ctx))
        print(f'AV at EIP=0x{ctx.Eip:x} EBX=0x{ctx.Ebx:x} ECX=0x{ctx.Ecx:x}', flush=True)
        # идём по EBP вверх: первый же сохранённый EBP -> фрейм QuickSort
        ebp = ctx.Ebp
        captured = None
        frames = []
        for level in range(6):
            pair = read_mem(ebp, 8)
            if len(pair) < 8: break
            saved, ret = struct.unpack('<II', pair)
            v8 = read_u32(ebp+8)
            frames.append((ret, v8))
            print(f'  level{level}: ebp=0x{ebp:x} ret=0x{ret:x} [ebp+8]=0x{v8} [ebp+C]=0x{read_u32(ebp+12)} [ebp-4]=0x{read_u32(ebp-4)} [ebp-8]=0x{read_u32(ebp-8)} [ebp-10]=0x{read_u32(ebp-16)}', flush=True)
            ebp = saved
            if not ebp or ebp < 0x10000: break
        # кандидаты на указатель TList (TCachedModules):
        #  - [ebp+8] фрейма Sort (level3, ret в _Sort) = Self
        #  - [ebp+8] фреймов QuickSort (level1/2)
        cands = []
        if len(frames) >= 4 and frames[3][1]:
            cands.append(('level3/Self', frames[3][1]))
        for lvl in (1, 2):
            if len(frames) > lvl and frames[lvl][1]:
                cands.append((f'level{lvl}', frames[lvl][1]))
        lst = None
        for tag, cand in cands:
            hdr = read_mem(cand, 16)
            if len(hdr) < 16: continue
            vmt, items, count, cap = struct.unpack('<IIII', hdr)
            ok = items and (0 < count <= cap < 10000) and (count < 500)
            print(f'  >>> кандидат {tag}=0x{cand:x}: items=0x{items:x} count={count} cap={cap} {"OK" if ok else "нет"}', flush=True)
            if ok and lst is None:
                lst = cand
        if lst is None:
            print('  >>> ни один кандидат не похож на TList', flush=True)
            k32.CloseHandle(hthr); break
        hdr = read_mem(lst, 16)
        vmt, items, count, cap = struct.unpack('<IIII', hdr)
        if items and 0 < count < 500:
            raw = read_mem(items, count * 4)
            ptrs = struct.unpack(f'<{count}I', raw[:count*4])
            nils = [i for i, p2 in enumerate(ptrs) if p2 == 0]
            print(f'  >>> NIL на индексах: {nils}', flush=True)
            for i, p2 in enumerate(ptrs):
                if p2 == 0:
                    for j in (i - 1, i + 1):
                        if 0 <= j < count and ptrs[j]:
                            fn = read_str(read_u32(ptrs[j] + 4))
                            sp = read_str(read_u32(ptrs[j] + 12))
                            print(f'      сосед [{j}]: FullName={fn!r} ShortPath={sp!r}', flush=True)
                    break
            else:
                print('  >>> nil нет; имена всех модулей:', flush=True)
                for i, p2 in enumerate(ptrs):
                    fn = read_str(read_u32(p2 + 4)) if p2 else None
                    sn = read_str(read_u32(p2 + 8)) if p2 else None
                    sp = read_str(read_u32(p2 + 12)) if p2 else None
                    mt = read_u32(p2 + 20) if p2 else None
                    mt2 = read_u32(p2 + 24) if p2 else None
                    print(f'      [{i}] +20={mt} +24={mt2} full={fn!r} short={sn!r} path={sp!r}', flush=True)
        k32.CloseHandle(hthr)
        break
    k32.ContinueDebugEvent(pid, tid, 0x00010002)

k32.TerminateProcess(hproc, 0)
print('exit')
