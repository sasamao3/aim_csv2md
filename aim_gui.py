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
        
        self.csv_path = None
        self.output_dir = Path.home()
        self.output_path = None
        
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
        
        ttk.Button(csv_frame, text="Select File...", command=self.select_csv_file, width=15).pack(side=tk.LEFT, padx=(0, 10))
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
    
    
    def select_csv_file(self):
        """Select CSV file"""
        file_path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.load_csv(file_path)
    
    def load_csv(self, file_path):
        """Load and validate CSV (runs in background thread to keep UI responsive)"""
        def _worker():
            try:
                path = Path(file_path)
                if not path.exists():
                    raise FileNotFoundError(f"File not found: {file_path}")
                aim = _load_aim()
                session = aim.read_aim_csv(str(path))
                self.csv_path = path
                self.root.after(0, lambda: (
                    self.csv_label.config(
                        text=f"✓ {path.name} ({len(session.data)} rows)",
                        foreground="green"
                    ),
                    self.update_status(f"✓ Loaded: {path.name}\n{len(session.data)} data points")
                ))
            except Exception as e:
                self.root.after(0, lambda: (
                    self.csv_label.config(text="Error loading file", foreground="red"),
                    self.update_status(f"✗ Error: {type(e).__name__}\n{str(e)}"),
                    messagebox.showerror("Error", f"{type(e).__name__}: {e}")
                ))
        self.update_status("📂 Loading CSV...")
        threading.Thread(target=_worker, daemon=True).start()
    
    def change_output_dir(self):
        """Change output directory"""
        folder = filedialog.askdirectory(title="Select Output Directory", initialdir=str(self.output_dir))
        if folder:
            self.output_dir = Path(folder)
            self.output_label.config(text=str(self.output_dir))
    
    def setup_drag_drop(self):
        """Setup drag and drop support"""
        pass
    
    
    def convert(self):
        """Convert CSV to Markdown"""
        if not self.csv_path:
            messagebox.showwarning("Warning", "Please select a CSV file")
            return
        
        self.convert_btn.config(state=tk.DISABLED)
        self.update_status("Converting... Please wait.")
        self.root.update()
        
        thread = threading.Thread(target=self._convert_thread, daemon=True)
        thread.start()
    
    def _convert_thread(self):
        """Thread worker for conversion"""
        try:
            aim = _load_aim()
            self.update_status("📖 Reading CSV...")
            session = aim.read_aim_csv(str(self.csv_path))

            self.update_status("🔄 Generating markdown...")
            all_laps = self.lap_mode.get() == "all"

            md = aim.generate_markdown(session, all_laps=all_laps, sample_step=1.0)

            output_path = self.output_dir / (self.csv_path.stem + "_aim_ai.md")
            output_path.write_text(md, encoding="utf-8")
            self.output_path = output_path

            # GPS サマリーを作成
            gps_summary = self._build_gps_summary(aim, session)

            self.root.after(0, self._convert_success, output_path, gps_summary)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.root.after(0, self._convert_failed)

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
    
    def update_status(self, msg):
        """Update status display"""
        self.status.config(state=tk.NORMAL)
        self.status.delete(1.0, tk.END)
        self.status.insert(tk.END, msg)
        self.status.config(state=tk.DISABLED)
        self.root.update()
    
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
