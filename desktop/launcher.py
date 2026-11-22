"""Windows & cross-platform Desktop Launcher for DZ Car Rental Finder.

Starts the local FastAPI backend (which also serves the built web dashboard),
opens the browser automatically, and provides desktop controls for collection,
progress monitoring, record review, exports, logs, and clean shutdown.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import json
import webbrowser
from pathlib import Path
from typing import Any

# Resolve root path whether running from source or PyInstaller bundle
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS")).resolve()
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    BUNDLE_DIR = Path(__file__).resolve().parent.parent
    ROOT_DIR = BUNDLE_DIR

BACKEND_DIR = BUNDLE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DZ_ROOT_DIR", str(ROOT_DIR))

HOST = os.environ.get("DZ_HOST", "127.0.0.1")
PORT = int(os.environ.get("DZ_PORT", "8000"))
BASE_URL = f"http://{HOST}:{PORT}"


def _api_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _open_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(folder))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])


class ServerThread(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="dz-uvicorn-server")
        self.server: Any = None
        self.startup_error: str = ""

    def run(self) -> None:
        try:
            import uvicorn
            from app.main import app

            config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
            self.server = uvicorn.Server(config)
            self.server.run()
        except Exception as exc:
            self.startup_error = str(exc)

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True


def wait_for_backend(server_thread: ServerThread, timeout_s: float = 20.0) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if server_thread.startup_error:
            return False, server_thread.startup_error
        try:
            res = _api_request("GET", "/api/health")
            if res.get("status") == "ok":
                return True, ""
        except Exception:
            time.sleep(0.25)
    return False, "Backend timed out while starting on port 8000."


def run_gui() -> int:
    import tkinter as tk
    from tkinter import messagebox

    server_thread = ServerThread()
    server_thread.start()

    ok, err = wait_for_backend(server_thread)
    if not ok:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("DZ Car Rental Finder — Startup Error", f"Failed to start local backend:\n\n{err}")
        return 1

    webbrowser.open(BASE_URL)

    root = tk.Tk()
    root.title("DZ Car Rental Finder — Desktop Controller")
    root.geometry("560x430")
    root.resizable(False, False)

    status_var = tk.StringVar(value=f"Backend running at {BASE_URL}")
    metrics_var = tk.StringVar(value="Loading registry metrics…")
    run_var = tk.StringVar(value="No active collection run")

    frame = tk.Frame(root, padx=20, pady=16)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="DZ Car Rental Finder", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    tk.Label(frame, textvariable=status_var, fg="#475569", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 12))

    info_box = tk.LabelFrame(frame, text="Registry & Collection Progress", padx=12, pady=10)
    info_box.pack(fill="x", pady=(0, 14))
    tk.Label(info_box, textvariable=metrics_var, justify="left", font=("Consolas", 9)).pack(anchor="w")
    tk.Label(info_box, textvariable=run_var, justify="left", fg="#0f766e", font=("Segoe UI", 9, "bold")).pack(
        anchor="w", pady=(6, 0)
    )

    def refresh_status() -> None:
        try:
            s = _api_request("GET", "/api/dashboard/summary")
            metrics_var.set(
                f"Unique Businesses : {s['total_businesses']}  (Verified: {s['verified_count']})\n"
                f"Needs Review      : {s['review_count']}  |  Suspected Duplicates: {s['suspected_duplicates_count']}\n"
                f"Collection Runs   : {s['collection_runs_count']}"
            )
            if s.get("active_run_id"):
                detail = _api_request("GET", f"/api/collections/{s['active_run_id']}")
                r = detail["run"]
                run_var.set(
                    f"Running #{r['id']}: {r['completed_tasks']}/{r['total_tasks']} tasks · Discovered {r['discovered_count']}"
                )
            else:
                run_var.set("Collection idle")
        except Exception as exc:
            run_var.set(f"Status refresh warning: {exc}")
        root.after(2500, refresh_status)

    def start_collection() -> None:
        try:
            res = _api_request("POST", "/api/collections/start", {"search_depth": "standard"})
            run_var.set(f"Started collection run #{res['run_id']}")
        except urllib.error.HTTPError as exc:
            messagebox.showwarning("Collection", exc.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            messagebox.showerror("Collection Error", str(exc))

    def stop_collection() -> None:
        try:
            s = _api_request("GET", "/api/dashboard/summary")
            if s.get("active_run_id"):
                _api_request("POST", f"/api/collections/{s['active_run_id']}/stop")
                run_var.set("Stop requested — finishing current step safely…")
            else:
                messagebox.showinfo("Collection", "No collection run is currently active.")
        except Exception as exc:
            messagebox.showerror("Stop Error", str(exc))

    def export_excel() -> None:
        try:
            res = _api_request("POST", "/api/exports", {"format": "xlsx", "scope": "all"})
            messagebox.showinfo("Export Complete", f"Saved workbook:\nexports/{res['filename']}")
            _open_folder(ROOT_DIR / "exports")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    btn_grid = tk.Frame(frame)
    btn_grid.pack(fill="x", pady=4)
    buttons = [
        ("Open Web Dashboard", lambda: webbrowser.open(BASE_URL)),
        ("Start Collection (69 Wilayas)", start_collection),
        ("Stop Collection Safely", stop_collection),
        ("Review Records & Duplicates", lambda: webbrowser.open(BASE_URL)),
        ("Export Excel (.xlsx)", export_excel),
        ("Open Exports Folder", lambda: _open_folder(ROOT_DIR / "exports")),
        ("Open Logs Folder", lambda: _open_folder(ROOT_DIR / "logs")),
    ]
    for idx, (label, cmd) in enumerate(buttons):
        b = tk.Button(btn_grid, text=label, command=cmd, width=28, pady=6)
        b.grid(row=idx // 2, column=idx % 2, padx=4, pady=4, sticky="ew")

    def on_close() -> None:
        try:
            s = _api_request("GET", "/api/dashboard/summary")
            if s.get("active_run_id"):
                _api_request("POST", f"/api/collections/{s['active_run_id']}/stop")
                time.sleep(0.5)
        except Exception:
            pass
        server_thread.stop()
        root.destroy()

    tk.Button(frame, text="Shut Down Cleanly", command=on_close, bg="#0f172a", fg="#ffffff", pady=7).pack(
        fill="x", pady=(14, 0)
    )

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(500, refresh_status)
    root.mainloop()
    return 0


def main() -> int:
    if "--headless" in sys.argv:
        server_thread = ServerThread()
        server_thread.start()
        ok, err = wait_for_backend(server_thread)
        if not ok:
            print(f"Startup failed: {err}", file=sys.stderr)
            return 1
        webbrowser.open(BASE_URL)
        print(f"DZ Car Rental Finder running at {BASE_URL}. Press Ctrl+C to quit.")
        try:
            while server_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            server_thread.stop()
        return 0
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
