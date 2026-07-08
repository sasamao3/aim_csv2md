#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiM CSV to Markdown GUI Application
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import threading
import math
import time
import traceback

# 重いライブラリ (numpy/pandas) は起動時にロードしない。
# 変換スレッド内で初回のみインポートする（lazy import）。
_aim = None

def _load_aim():
    """aim_csv_to_md を初回呼び出し時にのみインポートする。"""
    global _aim
    if _aim is None:
        import aim_csv_to_md as _mod
        _aim = _mod
    return _aim


class AimConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AiM CSV to Markdown")
        self.root.geometry("900x650")
        
        self.csv_paths = []
        self.csv_path = None
        self.output_dir = Path.home()
        self.output_path = None
        self.output_paths = []
        self.debug_window = None
        self.debug_text = None
        self.debug_lines = []
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = ttk.Label(main_frame, text="AiM Solo 2 CSV to Markdown", font=("Helvetica", 18, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 20))
        
        # ===== Input CSV File =====
        ttk.Label(main_frame, text="📁 Input CSV:", font=("Helvetica", 12, "bold")).grid(row=1, column=0, sticky=tk.W, pady=(10, 5))
        
        csv_frame = ttk.Frame(main_frame)
        csv_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10), padx=0)
        
        ttk.Button(csv_frame, text="Select Files...", command=self.select_csv_file, width=15).pack(side=tk.LEFT, padx=(0, 10))
        self.csv_label = ttk.Label(csv_frame, text="No file selected", foreground="gray")
        self.csv_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # ===== Output Directory =====
        ttk.Label(main_frame, text="💾 Output Directory:", font=("Helvetica", 12, "bold")).grid(row=3, column=0, sticky=tk.W, pady=(20, 5))
        
        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))
        
        ttk.Button(output_frame, text="Change Dir...", command=self.change_output_dir, width=15).pack(side=tk.LEFT, padx=(0, 10))
        self.output_label = ttk.Label(output_frame, text=str(self.output_dir), foreground="blue")
        self.output_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # ===== Options =====
        ttk.Label(main_frame, text="⚙️ Options:", font=("Helvetica", 12, "bold")).grid(row=5, column=0, sticky=tk.W, pady=(20, 10))
        
        options_frame = ttk.Frame(main_frame)
        options_frame.grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=20, pady=5)
        
        self.lap_mode = tk.StringVar(value="best")
        ttk.Radiobutton(options_frame, text="Best Lap Only", variable=self.lap_mode, value="best").pack(anchor=tk.W, pady=3)
        ttk.Radiobutton(options_frame, text="All Laps Stats", variable=self.lap_mode, value="all").pack(anchor=tk.W, pady=3)
        
        # Sample step
        step_frame = ttk.Frame(main_frame)
        step_frame.grid(row=7, column=0, columnspan=2, sticky=tk.W, padx=20, pady=10)
        ttk.Label(step_frame, text="Sample Interval (sec):").pack(side=tk.LEFT, padx=(0, 10))
        self.sample_step = ttk.Spinbox(step_frame, from_=0.5, to=5.0, increment=0.5, width=8)
        self.sample_step.set(1.0)
        self.sample_step.pack(side=tk.LEFT)
        
        # ===== Action Buttons =====
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(30, 10))
        
        self.convert_btn = ttk.Button(btn_frame, text="▶ CONVERT", command=self.convert)
        self.convert_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Button(btn_frame, text="📂 Open Output", command=self.open_output_folder).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="🐛 Debug Log", command=self.show_debug_window).pack(side=tk.LEFT, padx=(15, 0))
        
        # ===== Status =====
        ttk.Label(main_frame, text="Status:", font=("Helvetica", 12, "bold")).grid(row=9, column=0, sticky=tk.W, pady=(20, 5))
        
        self.status = tk.Text(main_frame, height=8, width=100, wrap=tk.WORD, bg="white", relief=tk.SUNKEN)
        self.status.grid(row=10, column=0, columnspan=2, sticky=tk.NSEW, pady=5)
        
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.status.yview)
        scrollbar.grid(row=10, column=2, sticky=tk.NS)
        self.status.config(yscroll=scrollbar.set)
        
        self.status.insert(tk.END, "Ready. Select CSV file and click CONVERT.")
        self.status.config(state=tk.DISABLED)

        # Configure weights
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(10, weight=1)
        self.log_debug("App initialized")
    
    
    def select_csv_file(self):
        """Select CSV files"""
        self.log_debug("Opening CSV file picker")
        file_paths = filedialog.askopenfilenames(
            title="Select CSV Files",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_paths:
            self.log_debug(f"Selected {len(file_paths)} file(s)")
            self.load_csv(file_paths)
        else:
            self.log_debug("File picker canceled")
    
    def load_csv(self, file_path):
        """Load one or more CSV files into the current batch selection"""
        if isinstance(file_path, (str, Path)):
            paths = [Path(file_path)]
        else:
            paths = [Path(p) for p in file_path]

        self.csv_paths = paths
        self.csv_path = paths[0] if paths else None
        self.output_paths = []
        self.output_path = None
        self.log_debug(f"Loaded selection: {len(paths)} file(s)")

        if not paths:
            self.csv_label.config(text="No file selected", foreground="gray")
            self.update_status("Ready. Select CSV files and click CONVERT.")
            return

        if len(paths) == 1:
            label_text = f"✓ {paths[0].name}"
        else:
            shown = ", ".join(path.name for path in paths[:3])
            if len(paths) > 3:
                shown += f", +{len(paths) - 3} more"
            label_text = f"✓ {len(paths)} files selected: {shown}"

        self.csv_label.config(text=label_text, foreground="green")
        self.update_status(f"✓ Selected {len(paths)} CSV file(s)")
        self.log_debug(f"Selection label updated: {label_text}")
    
    def change_output_dir(self):
        """Change output directory"""
        folder = filedialog.askdirectory(title="Select Output Directory", initialdir=str(self.output_dir))
        if folder:
            self.output_dir = Path(folder)
            self.output_label.config(text=str(self.output_dir))
            self.log_debug(f"Output directory changed to {self.output_dir}")
    
    def setup_drag_drop(self):
        """Setup drag and drop support"""
        pass
    
    
    def convert(self):
        """Convert CSV to Markdown"""
        if not self.csv_paths:
            messagebox.showwarning("Warning", "Please select one or more CSV files")
            self.log_debug("Convert requested with no CSV selected")
            return
        
        self.log_debug(f"Convert requested for {len(self.csv_paths)} file(s)")
        self.convert_btn.config(state=tk.DISABLED)
        self.update_status("Converting... Please wait.")
        self.root.update()
        
        thread = threading.Thread(target=self._convert_thread, daemon=True)
        thread.start()
        self.log_debug(f"Conversion thread started: {thread.name}")
    
    def _convert_thread(self):
        """Thread worker for conversion"""
        try:
            self.log_debug("Conversion thread entered")
            aim = _load_aim()
            all_laps = self.lap_mode.get() == "all"
            sample_step = float(self.sample_step.get())
            total = len(self.csv_paths)
            successes = []
            failures = []
            used_output_paths = set()
            self.log_debug(f"Conversion options: all_laps={all_laps}, sample_step={sample_step}, total={total}")

            for index, csv_path in enumerate(self.csv_paths, start=1):
                try:
                    self.log_debug(f"[{index}/{total}] Reading {csv_path}")
                    self.update_status(f"📖 [{index}/{total}] Reading CSV: {csv_path.name}...")
                    session = aim.read_aim_csv(str(csv_path))

                    self.log_debug(f"[{index}/{total}] Generating markdown for {csv_path.name}")
                    self.update_status(f"🔄 [{index}/{total}] Generating markdown: {csv_path.name}...")
                    md = aim.generate_markdown(session, all_laps=all_laps, sample_step=sample_step)

                    output_path = self._resolve_output_path(csv_path, used_output_paths)
                    output_path.write_text(md, encoding="utf-8")
                    gps_summary = self._build_gps_summary(aim, session)

                    successes.append((csv_path, output_path, gps_summary))
                    self.log_debug(f"[{index}/{total}] Wrote {output_path}")
                except Exception as e:
                    error_text = traceback.format_exc()
                    failures.append((csv_path, type(e).__name__, str(e), error_text))
                    self.log_debug(f"[{index}/{total}] Failed for {csv_path.name}: {type(e).__name__}: {e}")
                    self.log_debug(error_text)

            self.root.after(0, self._convert_batch_complete, successes, failures)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.log_debug(f"Fatal conversion error: {error_msg}")
            self.log_debug(traceback.format_exc())
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.root.after(0, self._convert_failed)

    def _resolve_output_path(self, csv_path: Path, used_output_paths: set[Path]) -> Path:
        """Create a unique output path for batch conversion"""
        candidate = self.output_dir / f"{csv_path.stem}_aim_ai.md"
        suffix = 2
        while candidate in used_output_paths or candidate.exists():
            candidate = self.output_dir / f"{csv_path.stem}_aim_ai_{suffix}.md"
            suffix += 1
        used_output_paths.add(candidate)
        return candidate

    def _convert_batch_complete(self, successes, failures):
        """Handle batch conversion completion"""
        self.output_paths = [output_path for _, output_path, _ in successes]
        self.output_path = self.output_paths[-1] if self.output_paths else None
        self.log_debug(f"Batch complete: {len(successes)} success, {len(failures)} failure(s)")

        if not successes and failures:
            lines = ["✗ Conversion failed."]
            for csv_path, err_type, err_msg, _ in failures:
                lines.append(f"- {csv_path.name}: {err_type}: {err_msg}")
            self.update_status("\n".join(lines))
            self.convert_btn.config(state=tk.NORMAL)
            messagebox.showerror("Error", "\n".join(lines))
            return

        lines = [f"✓ {len(successes)} file(s) converted."]
        for csv_path, output_path, gps_summary in successes:
            lines.append(f"- {csv_path.name} -> {output_path.name}")
            if gps_summary:
                lines.append(gps_summary)

        if failures:
            lines.append("")
            lines.append(f"⚠ {len(failures)} file(s) failed.")
            for csv_path, err_type, err_msg, _ in failures:
                lines.append(f"- {csv_path.name}: {err_type}: {err_msg}")

        self.update_status("\n".join(lines))
        self.convert_btn.config(state=tk.NORMAL)

        if failures:
            messagebox.showwarning(
                "Done with warnings",
                f"{len(successes)} file(s) converted, {len(failures)} file(s) failed.\n\n"
                + "\n".join(f"- {csv_path.name}: {err_type}: {err_msg}" for csv_path, err_type, err_msg, _ in failures)
            )
        elif len(successes) == 1:
            output_path = successes[0][1]
            messagebox.showinfo("Done", f"✓ 変換完了\n\n{output_path.name}\n→ {output_path.parent}")
        else:
            messagebox.showinfo(
                "Done",
                f"✓ 変換完了\n\n{len(successes)} file(s)\n→ {self.output_dir}"
            )

    def _build_gps_summary(self, aim, session) -> str:
        """ベストラップのGPS情報サマリー文字列を返す"""
        try:
            laps = aim.split_laps(session)
            lap_times = aim.get_lap_times(session, laps)
            valid = [(i, t) for i, t in enumerate(lap_times)
                     if t and math.isfinite(t) and 20 <= t <= 300]
            if not valid:
                valid = [(i, t) for i, t in enumerate(lap_times)
                         if t and math.isfinite(t)]
            if not valid:
                return ""

            best_idx, _ = min(valid, key=lambda x: x[1])
            best_lap = laps[best_idx]
            stats = aim.lap_stats(best_lap)
            slow_zones = aim.find_slow_zones(
                best_lap, stats.get("speed_col"), stats.get("throttle_col")
            )

            lines = ["\n📍 GPS Info (Best Lap):"]

            lat = stats.get("min_speed_lat")
            lon = stats.get("min_speed_lon")
            min_spd = stats.get("min_speed")
            min_t = stats.get("min_speed_time")
            if lat is not None and lon is not None:
                lines.append(
                    f"  最低速ポイント: {min_spd:.1f} km/h @ {min_t:.2f}s"
                    f"  → {lat:.6f}, {lon:.6f}"
                )
            elif min_spd is not None:
                lines.append(
                    f"  最低速ポイント: {min_spd:.1f} km/h @ {min_t:.2f}s  (GPS なし)"
                )

            gps_zones = [z for z in slow_zones if "lat" in z and "lon" in z]
            lines.append(
                f"  低速候補: {len(slow_zones)} 箇所 "
                f"(うち GPS 付き {len(gps_zones)} 箇所)"
            )
            for z in gps_zones:
                lines.append(
                    f"    {z['time']:.2f}s  {z['speed']:.1f} km/h"
                    f"  → {z['lat']:.6f}, {z['lon']:.6f}"
                )

            return "\n".join(lines)
        except Exception:
            return ""
    
    def _convert_success(self, output_path, gps_summary: str = ""):
        """Handle successful conversion"""
        msg = (
            f"✓ SUCCESS!\n\nOutput: {output_path.name}\nLocation: {output_path.parent}"
            + gps_summary
        )
        self.update_status(msg)
        self.convert_btn.config(state=tk.NORMAL)
        messagebox.showinfo("Done", f"✓ 変換完了\n\n{output_path.name}\n→ {output_path.parent}")
    
    def _convert_failed(self):
        """Handle conversion failure"""
        self.update_status("✗ Conversion failed.")
        self.convert_btn.config(state=tk.NORMAL)
        self.log_debug("Conversion failed and UI restored")
    
    def update_status(self, msg):
        """Update status display"""
        def _apply():
            self.status.config(state=tk.NORMAL)
            self.status.delete(1.0, tk.END)
            self.status.insert(tk.END, msg)
            self.status.config(state=tk.DISABLED)

        if threading.current_thread() is threading.main_thread():
            _apply()
        else:
            self.root.after(0, _apply)

    def log_debug(self, msg: str):
        """Append a debug line and mirror it to the debug window if open."""
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        self.debug_lines.append(line)
        print(line, flush=True)

        def _apply():
            if self.debug_text is None:
                return
            self.debug_text.config(state=tk.NORMAL)
            self.debug_text.insert(tk.END, line + "\n")
            self.debug_text.see(tk.END)
            self.debug_text.config(state=tk.DISABLED)

        if threading.current_thread() is threading.main_thread():
            _apply()
        else:
            self.root.after(0, _apply)

    def show_debug_window(self):
        """Open a scrollable debug log window."""
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.lift()
            self.debug_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        window.title("Debug Log")
        window.geometry("800x420")
        window.minsize(640, 320)
        window.protocol("WM_DELETE_WINDOW", self._close_debug_window)
        self.debug_window = window

        frame = ttk.Frame(window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(frame, text="Debug Log", font=("Helvetica", 14, "bold"))
        header.pack(anchor=tk.W, pady=(0, 8))

        text = tk.Text(frame, wrap=tk.WORD, height=18)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.config(yscrollcommand=scroll.set, state=tk.DISABLED)
        self.debug_text = text

        for line in self.debug_lines:
            self.debug_text.config(state=tk.NORMAL)
            self.debug_text.insert(tk.END, line + "\n")
            self.debug_text.config(state=tk.DISABLED)
        self.debug_text.see(tk.END)

    def _close_debug_window(self):
        """Close the debug window without losing the log buffer."""
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.destroy()
        self.debug_window = None
        self.debug_text = None
    
    def open_output_folder(self):
        """Open output folder"""
        import subprocess
        try:
            subprocess.run(["open", str(self.output_dir)])
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open folder: {e}")


def main():
    root = tk.Tk()
    app = AimConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
