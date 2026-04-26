#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiM Solo 2 DL CSV -> AI-friendly Markdown converter

使い方:
  python aim_csv_to_md.py input.csv
  python aim_csv_to_md.py input.csv -o output.md
  python aim_csv_to_md.py input.csv --all-laps
  python aim_csv_to_md.py input.csv --sample-step 1.0

出力:
  - セッション情報
  - ラップ一覧
  - ベストラップ分析
  - 低速区間 / アクセル遅れ候補
  - AIに読ませやすいテレメトリ抜粋
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass
class AimSession:
    metadata: dict[str, str]
    beacon_markers: list[float]
    segment_times_raw: list[str]
    columns: list[str]
    units: list[str]
    data: pd.DataFrame


def parse_time_to_seconds(value: str) -> Optional[float]:
    """
    '1:23.763' -> 83.763
    '5:03.381' -> 303.381
    '83.763' -> 83.763
    """
    if value is None:
        return None

    s = str(value).strip().strip('"')
    if not s:
        return None

    try:
        if ":" in s:
            parts = s.split(":")
            if len(parts) == 2:
                minutes = float(parts[0])
                seconds = float(parts[1])
                return minutes * 60 + seconds
            if len(parts) == 3:
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        return float(s)
    except ValueError:
        return None


def fmt_time(seconds: float) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "n/a"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}" if m else f"{s:.3f}s"


def clean_col(name: str) -> str:
    return str(name).strip().strip('"')


def read_aim_csv(path: str | Path) -> AimSession:
    path = Path(path)

    # AiM CSVは上部にメタデータ、途中に列名、その次に単位行がある
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        rows = list(csv.reader(f))

    metadata: dict[str, str] = {}
    beacon_markers: list[float] = []
    segment_times_raw: list[str] = []

    header_idx: Optional[int] = None

    for i, row in enumerate(rows):
        if not row:
            continue

        key = clean_col(row[0])

        if key == "Time" and len(row) > 3:
            header_idx = i
            break

        if key == "Beacon Markers":
            beacon_markers = [float(x) for x in row[1:] if str(x).strip()]
        elif key == "Segment Times":
            segment_times_raw = [str(x).strip() for x in row[1:] if str(x).strip()]
        elif len(row) >= 2:
            metadata[key] = str(row[1]).strip()

    if header_idx is None:
        raise ValueError("AiM CSVのデータ列ヘッダ（Time行）が見つかりません。")

    columns = [clean_col(c) for c in rows[header_idx]]
    units = [clean_col(c) for c in rows[header_idx + 1]] if header_idx + 1 < len(rows) else []

    # 空行を飛ばしてデータ開始行を探す
    data_start = header_idx + 2
    while data_start < len(rows) and not rows[data_start]:
        data_start += 1

    data_rows = rows[data_start:]

    # 行末カラム欠け対策
    fixed_rows = []
    ncols = len(columns)
    for row in data_rows:
        if not row:
            continue
        if len(row) < ncols:
            row = row + [""] * (ncols - len(row))
        elif len(row) > ncols:
            row = row[:ncols]
        fixed_rows.append(row)

    df = pd.DataFrame(fixed_rows, columns=columns)

   # 数値化できる列は数値化
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() > 0:
            df[col] = converted

    if "Time" not in df.columns:
        raise ValueError("Time列が見つかりません。")

    df["Time"] = pd.to_numeric(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"]).reset_index(drop=True)

    return AimSession(
        metadata=metadata,
        beacon_markers=beacon_markers,
        segment_times_raw=segment_times_raw,
        columns=columns,
        units=units,
        data=df,
    )


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """
    列名ゆれ吸収。候補文字列が全部含まれるものを優先。
    """
    cols = list(df.columns)
    lowered = {c: c.lower() for c in cols}

    for cand in candidates:
        tokens = [t.lower() for t in re.split(r"\s+", cand.strip()) if t]
        for col, low in lowered.items():
            if all(t in low for t in tokens):
                return col

    return None


def split_laps(session: AimSession) -> list[pd.DataFrame]:
    df = session.data

    if session.beacon_markers:
        starts = [0.0] + session.beacon_markers[:-1]
        ends = session.beacon_markers
        laps = []
        for start, end in zip(starts, ends):
            lap = df[(df["Time"] >= start) & (df["Time"] <= end)].copy()
            if not lap.empty:
                lap["LapTime"] = lap["Time"] - start
                laps.append(lap.reset_index(drop=True))
        return laps

    # Beaconが無い場合の保険：Time巻き戻りでラップ判定
    times = df["Time"].to_numpy()
    resets = np.where(np.diff(times) < -1.0)[0] + 1
    indices = [0] + resets.tolist() + [len(df)]
    laps = []
    for a, b in zip(indices[:-1], indices[1:]):
        lap = df.iloc[a:b].copy()
        if not lap.empty:
            lap["LapTime"] = lap["Time"] - lap["Time"].iloc[0]
            laps.append(lap.reset_index(drop=True))
    return laps


def get_lap_times(session: AimSession, laps: list[pd.DataFrame]) -> list[float]:
    raw = [parse_time_to_seconds(x) for x in session.segment_times_raw]
    if raw and len(raw) == len(laps) and all(x is not None for x in raw):
        return [float(x) for x in raw]

    result = []
    for lap in laps:
        result.append(float(lap["LapTime"].iloc[-1] - lap["LapTime"].iloc[0]))
    return result


def numeric_series(df: pd.DataFrame, col: Optional[str]) -> Optional[pd.Series]:
    if not col or col not in df.columns:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def get_gps_at(lap: pd.DataFrame, idx: int) -> tuple[Optional[float], Optional[float]]:
    """指定インデックス行のGPS緯度経度を返す。列がなければNone。"""
    lat_col = find_col(lap, ["GPS Latitude", "Latitude"])
    lon_col = find_col(lap, ["GPS Longitude", "Longitude"])
    lat = None
    lon = None
    if lat_col and lat_col in lap.columns:
        v = pd.to_numeric(lap.loc[idx, lat_col], errors="coerce")
        if pd.notna(v):
            lat = float(v)
    if lon_col and lon_col in lap.columns:
        v = pd.to_numeric(lap.loc[idx, lon_col], errors="coerce")
        if pd.notna(v):
            lon = float(v)
    return lat, lon


def lap_stats(lap: pd.DataFrame) -> dict[str, Any]:
    speed_col = find_col(lap, ["GPS Speed", "Speed Rear", "speed"])
    throttle_col = find_col(lap, ["ECU Throttle", "Throttle"])
    gear_col = find_col(lap, ["Gear"])
    rpm_col = find_col(lap, ["RPM"])
    lean_col = find_col(lap, ["Lean Angle", "Lean"])
    rear_speed_col = find_col(lap, ["Speed Rear"])
    lat_col = find_col(lap, ["GPS Latitude", "Latitude"])
    lon_col = find_col(lap, ["GPS Longitude", "Longitude"])

    speed = numeric_series(lap, speed_col)
    throttle = numeric_series(lap, throttle_col)
    lean = numeric_series(lap, lean_col)
    rpm = numeric_series(lap, rpm_col)
    gear = numeric_series(lap, gear_col)
    rear_speed = numeric_series(lap, rear_speed_col)

    stats: dict[str, Any] = {
        "speed_col": speed_col,
        "throttle_col": throttle_col,
        "gear_col": gear_col,
        "rpm_col": rpm_col,
        "lean_col": lean_col,
        "rear_speed_col": rear_speed_col,
        "lat_col": lat_col,
        "lon_col": lon_col,
    }

    if speed is not None:
        stats.update(
            max_speed=float(speed.max()),
            min_speed=float(speed.min()),
            avg_speed=float(speed.mean()),
        )

        # 最低速ポイント
        idx = int(speed.idxmin())
        stats["min_speed_time"] = float(lap.loc[idx, "LapTime"])
        stats["min_speed_abs_time"] = float(lap.loc[idx, "Time"])

        # 最低速ポイントのGPS座標
        lat, lon = get_gps_at(lap, idx)
        if lat is not None:
            stats["min_speed_lat"] = lat
        if lon is not None:
            stats["min_speed_lon"] = lon

    if throttle is not None:
        stats.update(
            avg_throttle=float(throttle.mean()),
            max_throttle=float(throttle.max()),
            throttle_open_ratio=float((throttle > 5).mean() * 100),
            full_throttle_ratio=float((throttle > 95).mean() * 100),
        )

    if lean is not None:
        stats.update(
            max_lean_abs=float(lean.abs().max()),
            avg_lean_abs=float(lean.abs().mean()),
        )

    if rpm is not None:
        stats.update(
            max_rpm=float(rpm.max()),
            avg_rpm=float(rpm.mean()),
        )

    if gear is not None:
        valid_gear = gear.dropna()
        if not valid_gear.empty:
            stats["gear_mode"] = int(valid_gear.mode().iloc[0])

    if speed is not None and rear_speed is not None:
        diff = rear_speed - speed
        stats["rear_vs_gps_speed_diff_max"] = float(diff.max())
        stats["rear_vs_gps_speed_diff_avg"] = float(diff.mean())

    return stats


def find_slow_zones(lap: pd.DataFrame, speed_col: Optional[str], throttle_col: Optional[str], max_points: int = 5) -> list[dict[str, Any]]:
    speed = numeric_series(lap, speed_col)
    if speed is None:
        return []

    throttle = numeric_series(lap, throttle_col)
    lap_time = pd.to_numeric(lap["LapTime"], errors="coerce")
    lat_col = find_col(lap, ["GPS Latitude", "Latitude"])
    lon_col = find_col(lap, ["GPS Longitude", "Longitude"])

    # 局所的な最低速候補を探す
    values = speed.to_numpy()
    zones = []
    for i in range(2, len(values) - 2):
        if not np.isfinite(values[i]):
            continue
        if values[i] <= values[i - 1] and values[i] <= values[i + 1]:
            zones.append(i)

    # 近すぎる候補をまとめる
    zones = sorted(zones, key=lambda i: values[i])
    selected = []
    for i in zones:
        t = float(lap_time.iloc[i])
        if all(abs(t - z["time"]) > 3.0 for z in selected):
            row_idx = lap.index[i]
            item = {
                "time": t,
                "speed": float(values[i]),
            }
            if throttle is not None and i < len(throttle):
                item["throttle"] = float(throttle.iloc[i])
            # GPS座標
            if lat_col and lat_col in lap.columns:
                v = pd.to_numeric(lap.loc[row_idx, lat_col], errors="coerce")
                if pd.notna(v):
                    item["lat"] = float(v)
            if lon_col and lon_col in lap.columns:
                v = pd.to_numeric(lap.loc[row_idx, lon_col], errors="coerce")
                if pd.notna(v):
                    item["lon"] = float(v)
            selected.append(item)
        if len(selected) >= max_points:
            break

    return sorted(selected, key=lambda x: x["time"])


def telemetry_sample_table(lap: pd.DataFrame, stats: dict[str, Any], sample_step: float = 1.0) -> pd.DataFrame:
    keep = ["LapTime"]
    for key in ["speed_col", "throttle_col", "gear_col", "rpm_col", "lean_col", "rear_speed_col"]:
        col = stats.get(key)
        if col and col in lap.columns and col not in keep:
            keep.append(col)
    # GPS列を追加
    for key in ["lat_col", "lon_col"]:
        col = stats.get(key)
        if col and col in lap.columns and col not in keep:
            keep.append(col)

    tmp = lap[keep].copy()
    tmp["sample_bin"] = (tmp["LapTime"] / sample_step).round().astype(int)
    sampled = tmp.groupby("sample_bin", as_index=False).first().drop(columns=["sample_bin"])
    sampled = sampled.rename(columns={"LapTime": "t"})
    return sampled


def md_table_from_df(df: pd.DataFrame, max_rows: int = 120) -> str:
    d = df.head(max_rows).copy()

    for col in d.columns:
        if pd.api.types.is_numeric_dtype(d[col]):
            d[col] = d[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.2f}")

    return d.to_markdown(index=False)


def generate_insights(stats: dict[str, Any], slow_zones: list[dict[str, Any]]) -> list[str]:
    insights = []

    min_speed = stats.get("min_speed")
    avg_throttle = stats.get("avg_throttle")
    full_ratio = stats.get("full_throttle_ratio")
    max_lean = stats.get("max_lean_abs")
    rear_diff = stats.get("rear_vs_gps_speed_diff_max")

    if min_speed is not None and min_speed < 50:
        insights.append("最低速が50km/h未満。低速コーナーで落としすぎ、または向き変え待ちが長い可能性。")
    elif min_speed is not None:
        insights.append("最低速は極端には低くない。課題はボトム速度より、減速開始・アクセルON位置・ラインの可能性。")

    if avg_throttle is not None and avg_throttle < 35:
        insights.append("平均スロットルが低め。コース特性を考慮しても、開け始めが遅い可能性。")
    if full_ratio is not None and full_ratio < 20:
        insights.append("全開率が低め。立ち上がりから直線へのつながりを確認。")

    if max_lean is not None and max_lean < 40:
        insights.append("最大バンク角が控えめ。バンク量不足というより、初期旋回の作り方を確認したい。")
    elif max_lean is not None and max_lean > 55:
        insights.append("最大バンク角は大きめ。これ以上寝かせるより、早く向きを変えて早く起こす方向が安全。")

    if rear_diff is not None and rear_diff > 8:
        insights.append("リア速度がGPS速度より大きく出る区間あり。立ち上がりでスリップ/ホイールスピン傾向の可能性。")

    if slow_zones:
        z = min(slow_zones, key=lambda x: x["speed"])
        insights.append(f"最重要チェック地点はLapTime {z['time']:.2f}s付近。最低速 {z['speed']:.1f}km/h。")

    return insights


def generate_markdown(session: AimSession, all_laps: bool = False, sample_step: float = 1.0) -> str:
    laps = split_laps(session)
    lap_times = get_lap_times(session, laps)

    valid = [(i, t) for i, t in enumerate(lap_times) if t and math.isfinite(t) and 20 <= t <= 300]
    if not valid:
        valid = [(i, t) for i, t in enumerate(lap_times) if t and math.isfinite(t)]

    best_idx, best_time = min(valid, key=lambda x: x[1])
    best_lap = laps[best_idx]
    stats = lap_stats(best_lap)
    slow_zones = find_slow_zones(best_lap, stats.get("speed_col"), stats.get("throttle_col"))
    insights = generate_insights(stats, slow_zones)

    lines: list[str] = []

    lines.append("# AiM Solo 2 DL CSV Analysis\n")

    lines.append("## Session Info\n")
    for key in ["Session", "Vehicle", "Racer", "Date", "Time", "Sample Rate", "Duration", "Comment"]:
        if key in session.metadata:
            lines.append(f"- **{key}**: {session.metadata[key]}")
    lines.append("")

    lines.append("## Lap Summary\n")
    lap_rows = []
    for i, t in enumerate(lap_times, start=1):
        note = "BEST" if i - 1 == best_idx else ""
        if i == 1 and t > 180:
            note = (note + " / " if note else "") + "Out lap候補"
        if i == len(lap_times) and t > 120:
            note = (note + " / " if note else "") + "In lap候補"
        lap_rows.append({"Lap": i, "Time": fmt_time(t), "Seconds": f"{t:.3f}", "Note": note})
    lines.append(pd.DataFrame(lap_rows).to_markdown(index=False))
    lines.append("")

    lines.append("## Best Lap Dashboard\n")
    lines.append(f"- **Best Lap**: Lap {best_idx + 1}")
    lines.append(f"- **Lap Time**: {fmt_time(best_time)}")
    if stats.get("max_speed") is not None:
        lines.append(f"- **Max Speed**: {stats['max_speed']:.1f} km/h")
    if stats.get("min_speed") is not None:
        min_spd_str = f"- **Min Speed**: {stats['min_speed']:.1f} km/h @ {stats.get('min_speed_time', 0):.2f}s"
        lat = stats.get("min_speed_lat")
        lon = stats.get("min_speed_lon")
        if lat is not None and lon is not None:
            min_spd_str += f" | GPS: [{lat:.6f}, {lon:.6f}](https://maps.google.com/?q={lat:.6f},{lon:.6f})"
        lines.append(min_spd_str)
    if stats.get("avg_speed") is not None:
        lines.append(f"- **Avg Speed**: {stats['avg_speed']:.1f} km/h")
    if stats.get("avg_throttle") is not None:
        lines.append(f"- **Avg Throttle**: {stats['avg_throttle']:.1f} %")
    if stats.get("full_throttle_ratio") is not None:
        lines.append(f"- **Full Throttle Ratio >95%**: {stats['full_throttle_ratio']:.1f} %")
    if stats.get("max_lean_abs") is not None:
        lines.append(f"- **Max Lean Angle(abs)**: {stats['max_lean_abs']:.1f} deg")
    if stats.get("max_rpm") is not None:
        lines.append(f"- **Max RPM**: {stats['max_rpm']:.0f}")
    if stats.get("gear_mode") is not None:
        lines.append(f"- **Most Used Gear**: {stats['gear_mode']}")
    lines.append("")

    lines.append("## Weak Point Candidates\n")
    if slow_zones:
        rows = []
        for z in slow_zones:
            lat = z.get("lat")
            lon = z.get("lon")
            if lat is not None and lon is not None:
                gps_str = f"[{lat:.6f}, {lon:.6f}](https://maps.google.com/?q={lat:.6f},{lon:.6f})"
            else:
                gps_str = ""
            rows.append({
                "LapTime": f"{z['time']:.2f}s",
                "Speed": f"{z['speed']:.1f} km/h",
                "Throttle": "" if "throttle" not in z else f"{z['throttle']:.1f} %",
                "GPS": gps_str,
                "Interpretation": "低速/向き変え/開け始め確認ポイント",
            })
        lines.append(pd.DataFrame(rows).to_markdown(index=False))
    else:
        lines.append("- 速度列が見つからないため、低速区間は抽出できませんでした。")
    lines.append("")

    lines.append("## AI Insight\n")
    for item in insights:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Improvement Actions\n")
    lines.append("- 低速区間では「さらに寝かせる」より、ブレーキリリース後の向き変え完了を早める。")
    lines.append("- アクセルONは大きく一気に開けるより、早い位置から小さく一定開度で開始する。")
    lines.append("- ベストラップだけで判断せず、2番手ラップと同じ地点の最低速・スロットルON位置を比較する。")
    lines.append("- リアが逃げる感覚がある場合は、ライン/開け方/リア低速圧側の順で疑う。いきなりサスだけで解決しようとしない。")
    lines.append("")

    lines.append("## Detected Channels\n")
    channel_rows = []
    for col, unit in zip(session.columns, session.units + [""] * max(0, len(session.columns) - len(session.units))):
        channel_rows.append({"Column": col, "Unit": unit})
    lines.append(pd.DataFrame(channel_rows).to_markdown(index=False))
    lines.append("")

    lines.append(f"## Best Lap Telemetry Sample ({sample_step:.2f}s step)\n")
    sample = telemetry_sample_table(best_lap, stats, sample_step=sample_step)
    lines.append(md_table_from_df(sample, max_rows=160))
    lines.append("")

    if all_laps:
        lines.append("## All Laps Compact Stats\n")
        rows = []
        for i, lap in enumerate(laps):
            s = lap_stats(lap)
            rows.append({
                "Lap": i + 1,
                "Time": fmt_time(lap_times[i]),
                "MaxSpeed": "" if s.get("max_speed") is None else f"{s['max_speed']:.1f}",
                "MinSpeed": "" if s.get("min_speed") is None else f"{s['min_speed']:.1f}",
                "AvgThrottle": "" if s.get("avg_throttle") is None else f"{s['avg_throttle']:.1f}",
                "MaxLeanAbs": "" if s.get("max_lean_abs") is None else f"{s['max_lean_abs']:.1f}",
            })
        lines.append(pd.DataFrame(rows).to_markdown(index=False))
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert AiM Solo 2 DL CSV to AI-friendly Markdown.")
    parser.add_argument("csv", help="AiM CSV file path")
    parser.add_argument("-o", "--output", help="Output Markdown path. Default: <csv stem>_aim_ai.md")
    parser.add_argument("--all-laps", action="store_true", help="Include compact stats for all laps")
    parser.add_argument("--sample-step", type=float, default=1.0, help="Telemetry sample interval in seconds. Default: 1.0")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    output = Path(args.output) if args.output else csv_path.with_name(csv_path.stem + "_aim_ai.md")

    session = read_aim_csv(csv_path)
    md = generate_markdown(session, all_laps=args.all_laps, sample_step=args.sample_step)

    output.write_text(md, encoding="utf-8")
    print(f"Done: {output}")


if __name__ == "__main__":
    main()
