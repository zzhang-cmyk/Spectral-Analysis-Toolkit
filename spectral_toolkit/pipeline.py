"""流程编排模块：读取 -> 分组 -> 校验 -> 平滑 -> 绘图 -> 导出 -> 记录。"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import plotting
from .config import ToolkitConfig
from .data_io import Spectrum, list_txt_files, read_spectrum_txt
from .grouping import group_by_sample, parse_filename
from .smoothing import smooth_spectrum
from .validation import (
    validate_plot_config,
    validate_processing_config,
    validate_sg_params,
    wavelength_interval_stats,
)

log = logging.getLogger("spectral_toolkit.pipeline")


def _run_dir(base: Path) -> Path:
    """创建不覆盖历史的时间戳运行目录。"""
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = base / f"run_{stamp}"
    i = 2
    while d.exists():
        d = base / f"run_{stamp}_{i}"
        i += 1
    d.mkdir(parents=True)
    return d


def _select_files(cfg: ToolkitConfig) -> list[Path]:
    """确定待处理文件：file_list 优先，否则按 file_glob 处理整个文件夹。"""
    data_dir = cfg.input.data_dir
    if cfg.input.file_list:
        files = []
        for name in cfg.input.file_list:
            p = Path(name)
            p = p if p.is_absolute() else data_dir / p
            if not p.is_file():
                raise FileNotFoundError(f"指定文件不存在: {p}")
            files.append(p)
        return files
    files = list_txt_files(data_dir, cfg.input.file_glob)
    if not files:
        raise SystemExit(f"在 {data_dir} 中未找到匹配 {cfg.input.file_glob} 的 TXT 文件")
    return files


def run(cfg: ToolkitConfig) -> dict:
    """执行完整预处理流程。

    Returns:
        处理摘要 dict（含输出路径、运行时间、输入文件等）
    """
    t0 = time.time()

    # 1. 参数校验
    validate_sg_params(cfg.sg)
    validate_processing_config(cfg.processing)
    validate_plot_config(cfg.plot)

    # 2. 列出输入文件（支持选择文件或整个文件夹）
    files = _select_files(cfg)

    # 3. 读取 + 分组
    spectra: list[Spectrum] = []
    for f in files:
        spec, warns = read_spectrum_txt(f, cfg.input)
        for w in warns:
            log.warning("%s", w)
        sample_id, scan_id = parse_filename(f, cfg.grouping)
        spec.sample_id = sample_id
        spec.scan_id = scan_id
        spec.wavelength_stats = wavelength_interval_stats(spec.wavelengths)
        spectra.append(spec)

    # 4. 跨文件波长范围 / 采样间隔检查
    _check_cross_file(spectra)

    # 5. 逐条独立平滑（绝不跨样本）；含处理范围 + 重采样
    for s in spectra:
        s.smoothed, s.smooth_info = smooth_spectrum(s, cfg.sg, cfg.processing)

    # 6. 输出目录（独立、不覆盖原始文件）
    run_dir = _run_dir(cfg.output.out_dir)
    log.info("输出目录: %s", run_dir)

    # 7. 导出
    summary = _export(cfg, spectra, run_dir)
    summary["runtime_seconds"] = round(time.time() - t0, 3)
    summary["n_spectra"] = len(spectra)
    summary["input_files"] = [s.source_file.name for s in spectra]

    # 8. 处理记录
    if cfg.output.export_record:
        summary["record"] = str(_save_record(cfg, spectra, summary, run_dir))

    log.info("处理完成: %d 个文件，用时 %.2f s", len(spectra), summary["runtime_seconds"])
    return summary


def _check_cross_file(spectra: list[Spectrum]) -> None:
    """检查不同文件的波长范围及采样间隔一致性（提示，不中断）。"""
    if len(spectra) < 2:
        return
    ranges = [(float(s.wavelengths.min()), float(s.wavelengths.max())) for s in spectra]
    steps = [s.wavelength_stats.get("median_step") for s in spectra if s.wavelength_stats]
    r_min = min(r[0] for r in ranges)
    r_max = max(r[1] for r in ranges)
    if max(r[1] - r[0] for r in ranges) - min(r[1] - r[0] for r in ranges) > 1e-6:
        log.warning("不同文件的波长范围不一致：整体覆盖 %.4f–%.4f nm", r_min, r_max)
    steps = [x for x in steps if x is not None]
    if steps and (max(steps) - min(steps)) > 1e-4 * max(steps):
        log.warning("不同文件的采样间隔存在差异：%.5g–%.5g nm", min(steps), max(steps))
    for s in spectra:
        if s.wavelength_stats and not s.wavelength_stats.get("uniform"):
            log.warning("%s: %s", s.source_file.name, s.wavelength_stats.get("msg"))


def _export(cfg: ToolkitConfig, spectra: list[Spectrum], run_dir: Path) -> dict:
    out: dict = {}

    if cfg.output.export_smoothed_txt:
        txt_dir = run_dir / "smoothed_txt"
        txt_dir.mkdir(parents=True, exist_ok=True)
        for s in spectra:
            _write_smoothed_txt(txt_dir / f"{s.source_file.stem}_smoothed.txt", s)
        out["smoothed_txt_dir"] = str(txt_dir)

    if cfg.output.export_excel:
        xlsx = run_dir / "summary.xlsx"
        _write_excel(cfg, spectra, xlsx)
        out["excel"] = str(xlsx)

    if cfg.output.export_png:
        plot_dir = run_dir / "plots"
        _write_plots(cfg, spectra, plot_dir)
        out["plots_dir"] = str(plot_dir)

    return out


def _write_smoothed_txt(path: Path, s: Spectrum) -> None:
    """导出平滑后 TXT，保留原始波长坐标。"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("Wavelength\tIntensity_smoothed\n")
        for w, r in zip(s.wavelengths, s.smoothed):
            f.write(f"{w:.6f}\t{r:.8f}\n")


def _write_excel(cfg: ToolkitConfig, spectra: list[Spectrum], path: Path) -> None:
    raw_series = {s.label: pd.Series(s.reflectance, index=s.wavelengths) for s in spectra}
    sm_series = {s.label: pd.Series(s.smoothed, index=s.wavelengths) for s in spectra}

    raw_df = pd.concat(list(raw_series.values()), axis=1)
    raw_df.columns = list(raw_series.keys())
    raw_df.index.name = "wavelength"
    raw_df = raw_df.sort_index().reset_index()

    sm_df = pd.concat(list(sm_series.values()), axis=1)
    sm_df.columns = list(sm_series.keys())
    sm_df.index.name = "wavelength"
    sm_df = sm_df.sort_index().reset_index()

    first = spectra[0].smooth_info or {}
    params = [
        ("window_length", cfg.sg.window_length),
        ("polyorder", cfg.sg.polyorder),
        ("deriv", cfg.sg.deriv),
        ("mode", cfg.sg.mode),
        ("处理范围下限(processing_min)", cfg.processing.wavelength_min),
        ("处理范围上限(processing_max)", cfg.processing.wavelength_max),
        ("重采样(resample)", cfg.processing.resample),
        ("重采样方法(resample_method)", cfg.processing.resample_method),
        ("重采样步长(resample_step)", first.get("resample_step")),
        ("是否重采样", first.get("resampled")),
        ("绘图范围下限(plot.x_min)", cfg.plot.x_min),
        ("绘图范围上限(plot.x_max)", cfg.plot.x_max),
        ("绘图范围下限(plot.y_min)", cfg.plot.y_min),
        ("绘图范围上限(plot.y_max)", cfg.plot.y_max),
        ("figure_dpi", cfg.plot.figure_dpi),
        ("title", cfg.plot.title),
        ("n_spectra", len(spectra)),
    ]
    params_df = pd.DataFrame(params, columns=["参数", "值"])

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        raw_df.to_excel(xw, sheet_name="原始数据", index=False)
        sm_df.to_excel(xw, sheet_name="平滑数据", index=False)
        params_df.to_excel(xw, sheet_name="处理参数", index=False)


def _write_plots(cfg: ToolkitConfig, spectra: list[Spectrum], plot_dir: Path) -> None:
    plot_dir = Path(plot_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    plots = cfg.output.plots

    if plots.get("single_overlay") and spectra:
        s0 = spectra[0]
        plotting.plot_single_overlay(s0, s0.smoothed, cfg.plot, plot_dir / "single_overlay.png")

    if plots.get("multi_curves"):
        plotting.plot_multi_curves(spectra, cfg.plot, plot_dir / "multi_curves.png")

    groups = group_by_sample(spectra)

    if plots.get("sample_scans"):
        for sample_id, grp in groups.items():
            if len(grp) >= 2:
                plotting.plot_sample_scans(
                    sample_id, grp, cfg.plot, plot_dir / f"sample_{sample_id}_scans.png")

    if plots.get("sample_comparison") and len(groups) >= 2:
        plotting.plot_sample_comparison(groups, cfg.plot, plot_dir / "sample_comparison.png")

    if plots.get("before_after"):
        plotting.plot_before_after(spectra, cfg.plot, plot_dir / "before_after.png")

    if plots.get("mean_std") and spectra:
        plotting.plot_mean_std(spectra, cfg.plot, plot_dir / "mean_std.png")


def _save_record(cfg: ToolkitConfig, spectra: list[Spectrum],
                 summary: dict, run_dir: Path) -> Path:
    """保存本次处理记录（含输入文件、SG 参数、处理/绘图范围、重采样、运行时间）。"""
    files_info = []
    for s in spectra:
        st = s.wavelength_stats or {}
        info = s.smooth_info or {}
        files_info.append({
            "name": s.source_file.name,
            "sample_id": s.sample_id,
            "scan_id": s.scan_id,
            "wavelength_range": [float(s.wavelengths.min()), float(s.wavelengths.max())],
            "n_points": int(s.wavelengths.size),
            "interval_median": st.get("median_step"),
            "interval_uniform": st.get("uniform"),
            "resampled": info.get("resampled"),
        })

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_dir": str(cfg.input.data_dir),
        "input_files": files_info,
        "n_spectra": len(spectra),
        "sg_params": {
            "window_length": cfg.sg.window_length,
            "polyorder": cfg.sg.polyorder,
            "deriv": cfg.sg.deriv,
            "mode": cfg.sg.mode,
        },
        "processing_range": {
            "wavelength_min": cfg.processing.wavelength_min,
            "wavelength_max": cfg.processing.wavelength_max,
        },
        "resample": {
            "mode": cfg.processing.resample,
            "method": cfg.processing.resample_method,
            "step": cfg.processing.resample_step,
            "applied": any((s.smooth_info or {}).get("resampled") for s in spectra),
            "uniform_grid_step": next(
                (float((s.smooth_info or {}).get("resample_step"))
                 for s in spectra if (s.smooth_info or {}).get("resampled")), None),
        },
        "plot_range": {
            "x_min": cfg.plot.x_min,
            "x_max": cfg.plot.x_max,
            "y_min": cfg.plot.y_min,
            "y_max": cfg.plot.y_max,
            "figure_dpi": cfg.plot.figure_dpi,
            "title": cfg.plot.title,
            "xlabel": cfg.plot.xlabel,
            "ylabel": cfg.plot.ylabel,
        },
        "runtime_seconds": summary["runtime_seconds"],
        "outputs": {
            k: v for k, v in summary.items()
            if k not in ("runtime_seconds", "input_files", "n_spectra")
        },
    }
    record_path = run_dir / "processing_record.json"
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record_path