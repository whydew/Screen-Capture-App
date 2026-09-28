"""
Screen Capture to PDF
Takes a screenshot of a chosen monitor or app window, presses a key (default Alt+Right),
and repeats until you press Esc. Then it can combine the screenshots into a PDF,
with OCR so the text is searchable.

Windows only.
"""
import ctypes
import ctypes.wintypes as wintypes
import io
import os
import queue
import re
import shutil
import sys
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Make window coordinates match real pixels on scaled (125%, 150%) displays
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import keyboard
import mss
import mss.tools
import pytesseract
from PIL import Image
from pypdf import PdfReader, PdfWriter

APP_NAME = "Screen Capture to PDF"
AFTER_OPTIONS = ["Searchable PDF (OCR)", "Plain PDF (no OCR)", "Screenshots only"]

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi


# ---------------------------------------------------------------- helpers
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_tesseract():
    candidates = [
        os.path.join(app_dir(), "Tesseract-OCR", "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which("tesseract")


def is_cloaked(hwnd):
    cloaked = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return cloaked.value != 0


def list_windows():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4) and not is_cloaked(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title and title != "Program Manager":
                    found.append((hwnd, title))
        return True

    user32.EnumWindows(callback, 0)
    return found


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def window_region(hwnd):
    r = RECT()
    # Extended frame bounds excludes the invisible resize border Windows 10/11 adds
    if dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return {"left": r.left, "top": r.top,
            "width": max(1, r.right - r.left), "height": max(1, r.bottom - r.top)}


def activate_window(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip().rstrip(".")
    return name or "Screenshots"


def unique_folder(path):
    if not os.path.exists(path):
        return path
    n = 2
    while os.path.exists(f"{path} ({n})"):
        n += 1
    return f"{path} ({n})"


# ---------------------------------------------------------------- app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.resizable(False, False)
        self.targets = {}
        self.stop_event = threading.Event()
        self.hotkey = None
        self.worker = None
        self.msgs = queue.Queue()

        f = ttk.Frame(self, padding=12)
        f.grid(sticky="nsew")
        pad = {"padx": 6, "pady": 5}
        r = 0

        ttk.Label(f, text="Capture:").grid(row=r, column=0, sticky="w", **pad)
        self.target_var = tk.StringVar()
        self.target_cb = ttk.Combobox(f, textvariable=self.target_var, state="readonly", width=52)
        self.target_cb.grid(row=r, column=1, sticky="we", **pad)
        ttk.Button(f, text="Refresh", command=self.refresh_targets).grid(row=r, column=2, sticky="we", **pad)

        r += 1
        ttk.Label(f, text="Seconds between screenshots:").grid(row=r, column=0, sticky="w", **pad)
        self.delay_var = tk.StringVar(value="1.0")
        ttk.Spinbox(f, from_=0.2, to=60, increment=0.1, textvariable=self.delay_var, width=8
                    ).grid(row=r, column=1, sticky="w", **pad)
        ttk.Label(f, text="Raise this on slower PCs").grid(row=r, column=1, sticky="e", **pad)

        r += 1
        ttk.Label(f, text="Key to press after each shot:").grid(row=r, column=0, sticky="w", **pad)
        self.key_var = tk.StringVar(value="alt+right")
        ttk.Entry(f, textvariable=self.key_var, width=20).grid(row=r, column=1, sticky="w", **pad)
        ttk.Label(f, text="e.g. alt+right, page down, right (blank = none)"
                  ).grid(row=r, column=1, sticky="e", **pad)

        r += 1
        ttk.Label(f, text="Countdown before start (sec):").grid(row=r, column=0, sticky="w", **pad)
        self.countdown_var = tk.StringVar(value="3")
        ttk.Spinbox(f, from_=0, to=30, increment=1, textvariable=self.countdown_var, width=8
                    ).grid(row=r, column=1, sticky="w", **pad)

        r += 1
        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky="we", pady=8)

        r += 1
        ttk.Label(f, text="Folder name:").grid(row=r, column=0, sticky="w", **pad)
        self.name_var = tk.StringVar(value=datetime.now().strftime("Screenshots_%Y-%m-%d_%H%M"))
        ttk.Entry(f, textvariable=self.name_var).grid(row=r, column=1, sticky="we", **pad)

        r += 1
        ttk.Label(f, text="Save in:").grid(row=r, column=0, sticky="w", **pad)
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        self.dir_var = tk.StringVar(value=docs if os.path.isdir(docs) else os.path.expanduser("~"))
        ttk.Entry(f, textvariable=self.dir_var).grid(row=r, column=1, sticky="we", **pad)
        ttk.Button(f, text="Browse...", command=self.browse).grid(row=r, column=2, sticky="we", **pad)

        r += 1
        ttk.Label(f, text="When stopped, create:").grid(row=r, column=0, sticky="w", **pad)
        self.after_var = tk.StringVar(value=AFTER_OPTIONS[0])
        ttk.Combobox(f, textvariable=self.after_var, values=AFTER_OPTIONS, state="readonly", width=24
                     ).grid(row=r, column=1, sticky="w", **pad)

        r += 1
        self.minimize_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Minimize this window while capturing", variable=self.minimize_var
                        ).grid(row=r, column=1, sticky="w", **pad)

        r += 1
        btns = ttk.Frame(f)
        btns.grid(row=r, column=0, columnspan=3, pady=(10, 4))
        self.start_btn = ttk.Button(btns, text="Start", command=self.start, width=14)
        self.start_btn.grid(row=0, column=0, padx=6)
        self.stop_btn = ttk.Button(btns, text="Stop (Esc)", command=self.stop, width=14, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=6)
        self.open_btn = ttk.Button(btns, text="Open folder", command=self.open_folder, width=14, state="disabled")
        self.open_btn.grid(row=0, column=2, padx=6)

        r += 1
        self.status_var = tk.StringVar(value="Pick what to capture, then press Start. Press Esc anytime to stop.")
        ttk.Label(f, textvariable=self.status_var, wraplength=560, foreground="#333"
                  ).grid(row=r, column=0, columnspan=3, sticky="w", **pad)

        self.last_folder = None
        self.refresh_targets()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll)

    # ---------- UI actions
    def refresh_targets(self):
        self.targets.clear()
        with mss.mss() as sct:
            for i, m in enumerate(sct.monitors[1:], 1):
                self.targets[f"Monitor {i}  ({m['width']}x{m['height']})"] = ("monitor", dict(m))
        for hwnd, title in list_windows():
            if title == APP_NAME:
                continue
            label = base = f"App: {title[:70]}"
            n = 2
            while label in self.targets:
                label = f"{base} ({n})"
                n += 1
            self.targets[label] = ("window", hwnd)
        values = list(self.targets)
        self.target_cb["values"] = values
        if self.target_var.get() not in self.targets and values:
            self.target_var.set(values[0])

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get() or None, title="Choose where to save")
        if d:
            self.dir_var.set(d)

    def open_folder(self):
        if self.last_folder and os.path.isdir(self.last_folder):
            os.startfile(self.last_folder)

    def set_status(self, text):
        self.msgs.put(("status", text))

    def poll(self):
        try:
            while True:
                kind, val = self.msgs.get_nowait()
                if kind == "status":
                    self.status_var.set(val)
                    self.title(f"{APP_NAME} - {val}" if self.worker else APP_NAME)
                elif kind == "done":
                    self.finish(val)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    # ---------- start / stop
    def start(self):
        label = self.target_var.get()
        if label not in self.targets:
            messagebox.showerror(APP_NAME, "Pick a monitor or app to capture.")
            return
        kind, target = self.targets[label]
        if kind == "window" and not user32.IsWindow(target):
            messagebox.showerror(APP_NAME, "That window is closed. Press Refresh and pick again.")
            return

        try:
            delay = float(self.delay_var.get())
            countdown = int(float(self.countdown_var.get()))
            if delay < 0.1 or countdown < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_NAME, "Seconds between screenshots must be 0.1 or more, and the countdown 0 or more.")
            return

        key = self.key_var.get().strip().lower()
        if key:
            try:
                keyboard.parse_hotkey(key)
            except Exception:
                messagebox.showerror(APP_NAME, f"'{key}' isn't a key combo I recognize.\nExamples: alt+right, page down, ctrl+tab")
                return

        save_dir = self.dir_var.get().strip()
        if not save_dir or not os.path.isdir(save_dir):
            messagebox.showerror(APP_NAME, "The 'Save in' location doesn't exist. Use Browse to pick one.")
            return

        after = self.after_var.get()
        if after == AFTER_OPTIONS[0]:
            tess = find_tesseract()
            if not tess:
                messagebox.showerror(APP_NAME, "OCR needs Tesseract, and it wasn't found.\n\n"
                                     "Put the Tesseract-OCR folder next to this program, or install it from "
                                     "github.com/UB-Mannheim/tesseract/wiki.\n\n"
                                     "Or choose 'Plain PDF (no OCR)'.")
                return
            pytesseract.pytesseract.tesseract_cmd = tess

        folder = unique_folder(os.path.join(save_dir, safe_name(self.name_var.get())))
        os.makedirs(folder)
        self.last_folder = folder

        cfg = {"kind": kind, "target": target, "delay": delay, "countdown": countdown,
               "key": key, "folder": folder, "after": after}

        self.stop_event.clear()
        self.hotkey = keyboard.add_hotkey("esc", self.stop_event.set)
        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"
        self.open_btn["state"] = "disabled"

        if self.minimize_var.get():
            self.iconify()
        if kind == "window":
            activate_window(target)

        self.worker = threading.Thread(target=self.run, args=(cfg,), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()

    def finish(self, message):
        if self.hotkey is not None:
            try:
                keyboard.remove_hotkey(self.hotkey)
            except Exception:
                pass
            self.hotkey = None
        self.worker = None
        self.start_btn["state"] = "normal"
        self.stop_btn["state"] = "disabled"
        self.open_btn["state"] = "normal" if self.last_folder else "disabled"
        self.status_var.set(message)
        self.title(APP_NAME)
        self.deiconify()
        self.lift()
        # fresh default name for the next run
        self.name_var.set(datetime.now().strftime("Screenshots_%Y-%m-%d_%H%M"))

    def on_close(self):
        self.stop_event.set()
        self.destroy()

    # ---------- worker thread
    def run(self, cfg):
        files = []
        try:
            for i in range(cfg["countdown"], 0, -1):
                self.set_status(f"Starting in {i}... (Esc to stop)")
                if self.stop_event.wait(1):
                    break

            with mss.mss() as sct:
                while not self.stop_event.is_set():
                    if cfg["kind"] == "monitor":
                        region = cfg["target"]
                    else:
                        hwnd = cfg["target"]
                        if not user32.IsWindow(hwnd):
                            self.set_status("The window was closed. Stopping.")
                            break
                        if user32.IsIconic(hwnd):
                            self.set_status("Window is minimized, waiting...")
                            self.stop_event.wait(0.5)
                            continue
                        region = window_region(hwnd)

                    shot = sct.grab(region)
                    path = os.path.join(cfg["folder"], f"{len(files) + 1:04d}.png")
                    mss.tools.to_png(shot.rgb, shot.size, output=path)
                    files.append(path)
                    self.set_status(f"Captured {len(files)} (Esc to stop)")

                    if cfg["key"]:
                        keyboard.send(cfg["key"])
                    if self.stop_event.wait(cfg["delay"]):
                        break

            if not files:
                self.msgs.put(("done", "Stopped. No screenshots were taken."))
                return

            if cfg["after"] == AFTER_OPTIONS[2]:
                self.msgs.put(("done", f"Done. {len(files)} screenshots saved in:\n{cfg['folder']}"))
                return

            ocr = cfg["after"] == AFTER_OPTIONS[0]
            pdf_path = os.path.join(cfg["folder"], os.path.basename(cfg["folder"]) + ".pdf")
            writer = PdfWriter()
            for i, f in enumerate(files, 1):
                self.set_status(f"{'Running OCR on' if ocr else 'Adding'} page {i} of {len(files)}...")
                with Image.open(f) as im:
                    if ocr:
                        data = pytesseract.image_to_pdf_or_hocr(im, extension="pdf")
                    else:
                        buf = io.BytesIO()
                        im.convert("RGB").save(buf, "PDF")
                        data = buf.getvalue()
                for page in PdfReader(io.BytesIO(data)).pages:
                    writer.add_page(page)
            with open(pdf_path, "wb") as fh:
                writer.write(fh)

            self.msgs.put(("done", f"Done. {len(files)} screenshots and PDF saved in:\n{cfg['folder']}"))
        except Exception as e:
            self.msgs.put(("done", f"Error: {e}\n{len(files)} screenshots were saved in {cfg['folder']}"))


if __name__ == "__main__":
    App().mainloop()
