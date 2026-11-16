#!/usr/bin/env python3
"""
SMT Lab Desktop App Ã¢â‚¬â€ Click-to-run interface for the research framework.
Run: python smt_lab_app.py
"""
import sys
import os
import subprocess
import threading
import queue
import re
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
from pathlib import Path

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Config Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
BASE_DIR = Path(__file__).parent.resolve()
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
DATABENTO_KEY = os.environ.get("DATABENTO_API_KEY", "")  # set via env or .env

COMMANDS = {
    "Ã°Å¸â€Â§ Setup / Re-install": {
        "cmd": [str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"],
        "cwd": BASE_DIR,
        "description": "Install/reinstall all dependencies from requirements.txt"
    },
    "Ã°Å¸Â§Âª Unit Tests (pytest)": {
        "cmd": [str(VENV_PYTHON), "-m", "pytest", "tests/", "-q"],
        "cwd": BASE_DIR,
        "description": "Run look-ahead and fill-logic tests (10 tests)"
    },
    "Ã°Å¸Å½Â² Generate Synthetic Data": {
        "cmd": [str(VENV_PYTHON), "make_synthetic.py"],
        "cwd": BASE_DIR,
        "description": "Create random-walk NQ/ES data for plumbing tests"
    },
    "Ã°Å¸â€œÂ¥ Fetch Real Data (Databento)": {
        "cmd": [str(VENV_PYTHON), "fetch_data.py", "databento",
                "--start", "2023-01-01", "--end", "2025-01-01", "--yes"],
        "cwd": BASE_DIR,
        "env": {"DATABENTO_API_KEY": DATABENTO_KEY},
        "description": "Download CME MDP3 1-min NQ/ES (2023-2024) Ã¢â‚¬â€ costs ~$5"
    },
    "Ã°Å¸â€œÂ¥ Fetch Real Data (yfinance free)": {
        "cmd": [str(VENV_PYTHON), "fetch_data.py", "yfinance"],
        "cwd": BASE_DIR,
        "description": "Free but limited (~60 days, 5-min bars)"
    },
    "Ã¢â€“Â¶Ã¯Â¸Â Quick Backtest (Sanity Check)": {
        "cmd": [str(VENV_PYTHON), "run_backtest.py",
                "--a", "data/NQ_1m.parquet", "--b", "data/ES_1m.parquet"],
        "cwd": BASE_DIR,
        "description": "Single pass over ALL data Ã¢â‚¬â€ NOT out-of-sample"
    },
    "Ã°Å¸Å½Â¯ WALK-FORWARD (Main Validation)": {
        "cmd": [str(VENV_PYTHON), "run_walkforward.py",
                "--a", "data/NQ_1m.parquet", "--b", "data/ES_1m.parquet", "--quick"],
        "cwd": BASE_DIR,
        "description": "6m train Ã¢â€ â€™ 1m test, stitched OOS Ã¢â‚¬â€ THE MAIN TEST"
    },
    "Ã°Å¸â€Â NOISE CHECK (Reality Check)": {
        "cmd": [str(VENV_PYTHON), "noise_check.py",
                "--days", "500", "--my-t", "AUTO", "--quick"],
        "cwd": BASE_DIR,
        "description": "How lucky does noise get? Run AFTER walk-forward; paste its t-stat"
    },
}

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ App Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
class SMTLabApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SMT Lab Ã¢â‚¬â€ Research Framework")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)

        # State
        self.proc = None
        self.output_queue = queue.Queue()
        self.last_t_stat = None

        # UI
        self._build_ui()
        self._check_venv()

        # Start output reader
        self.root.after(100, self._poll_output)

    def _build_ui(self):
        # Toolbar
        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="SMT Lab", font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(toolbar, text="Open Folder", command=self._open_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Clear Output", command=self._clear_output).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Stop Running", command=self._stop_process, style="Accent.TButton").pack(side=tk.RIGHT, padx=5)

        # Main paned window
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Left: Command buttons
        left_frame = ttk.Frame(paned, padding=10)
        paned.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Commands", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 8))

        self.btn_frame = ttk.Frame(left_frame)
        self.btn_frame.pack(fill=tk.BOTH, expand=True)

        for name, info in COMMANDS.items():
            btn = ttk.Button(
                self.btn_frame,
                text=name,
                command=lambda n=name: self._run_command(n),
                width=35
            )
            btn.pack(fill=tk.X, pady=3)
            # Tooltip
            self._create_tooltip(btn, info["description"])

        # Right: Output console
        right_frame = ttk.Frame(paned, padding=10)
        paned.add(right_frame, weight=3)

        ttk.Label(right_frame, text="Console Output", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))

        self.console = scrolledtext.ScrolledText(
            right_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white"
        )
        self.console.pack(fill=tk.BOTH, expand=True)
        self.console.tag_config("stdout", foreground="#d4d4d4")
        self.console.tag_config("stderr", foreground="#f44747")
        self.console.tag_config("system", foreground="#4ec9b0")
        self.console.tag_config("cmd", foreground="#9cdcfe")

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(0, 10))

    def _create_tooltip(self, widget, text):
        def enter(event):
            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            ttk.Label(self.tooltip, text=text, background="#ffffe0", relief=tk.SOLID, borderwidth=1, padding=5).pack()
        def leave(event):
            if hasattr(self, "tooltip"):
                self.tooltip.destroy()
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _check_venv(self):
        if not VENV_PYTHON.exists():
            self._log("Ã¢Å¡Â Ã¯Â¸Â Virtual environment not found at .venv/", "system")
            self._log("Run 'Setup / Re-install' first", "system")
        else:
            self._log("Ã¢Å“â€¦ Virtual environment found", "system")
            self._log(f"Python: {VENV_PYTHON}", "system")

    def _open_folder(self):
        os.startfile(BASE_DIR)

    def _clear_output(self):
        self.console.delete(1.0, tk.END)

    def _stop_process(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self._log("Ã°Å¸â€ºâ€˜ Process terminated by user", "system")
            self.status_var.set("Stopped")

    def _log(self, msg, tag="stdout"):
        self.console.insert(tk.END, msg + "\n", tag)
        self.console.see(tk.END)

    def _poll_output(self):
        try:
            while True:
                line, tag = self.output_queue.get_nowait()
                self._log(line, tag)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_output)

    def _run_command(self, name):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Busy", "A command is already running. Stop it first.")
            return

        info = COMMANDS[name]
        cmd = info["cmd"]
        cwd = info.get("cwd", BASE_DIR)
        env = os.environ.copy()
        env.update(info.get("env", {}))

        # Auto-fill t-stat for noise check
        if "AUTO" in " ".join(cmd) and self.last_t_stat is not None:
            cmd = [c if c != "AUTO" else str(self.last_t_stat) for c in cmd]
        elif "AUTO" in " ".join(cmd):
            t_stat = tk.simpledialog.askfloat("Noise Check", "Enter t-stat from walk-forward output:")
            if t_stat is None:
                return
            self.last_t_stat = t_stat
            cmd = [c if c != "AUTO" else str(t_stat) for c in cmd]

        self._log(f">>> {' '.join(cmd)}", "cmd")
        self._log(f"CWD: {cwd}", "system")
        self.status_var.set(f"Running: {name}")

        def worker():
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                # Stream stdout
                for line in self.proc.stdout:
                    self.output_queue.put((line.rstrip(), "stdout"))
                # Stream stderr
                for line in self.proc.stderr:
                    self.output_queue.put((line.rstrip(), "stderr"))
                self.proc.wait()
                self.output_queue.put((f"Exit code: {self.proc.returncode}", "system"))
                # Try to extract t-stat from walk-forward output
                if "walkforward" in " ".join(cmd).lower():
                    self._extract_t_stat()
            except Exception as e:
                self.output_queue.put((f"Error: {e}", "stderr"))
            finally:
                self.proc = None
                self.root.after(0, lambda: self.status_var.set("Ready"))

        threading.Thread(target=worker, daemon=True).start()

    def _extract_t_stat(self):
        # Scan console for t-stat pattern
        content = self.console.get(1.0, tk.END)
        import re
        matches = re.findall(r"avg R / trade\s+[+-]?\d+\.\d+\s+\(t-stat\s+([+-]?\d+\.\d+)\)", content)
        if matches:
            self.last_t_stat = float(matches[-1])
            self._log(f"Ã°Å¸â€œÅ  Captured t-stat: {self.last_t_stat:+.2f}", "system")

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Entry Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
if __name__ == "__main__":
    # Ensure we're in the right directory
    os.chdir(BASE_DIR)

    root = tk.Tk()
    # Windows DPI awareness
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = SMTLabApp(root)
    root.mainloop()