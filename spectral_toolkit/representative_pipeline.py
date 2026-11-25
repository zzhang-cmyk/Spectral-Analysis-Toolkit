"""代表性光谱提取模块的完整处理流程。

流程：识别样本子文件夹 -> 读取平滑光谱 -> 波长一致性检查 -> 逐波长算术平均
      -> 输出代表性光谱 TXT -> 绘制单样本图与全部样本对比图。

只输出两个结果文件夹：
- 01_代表性光谱数据/
- 02_光谱曲线图/

必要的运行信息与错误提示在控制台输出，不生成额外报告文件。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import representative_plot
from .config import RepresentativeConfig
from .representative import (
    check_cross_sample_wavelengths,
    check_sample_wavelengths,
    discover_samples,
    mean_spectrum,
    read_rep_spectrum,
)

log = logging.getLogger("spectral_toolkit.representative_pipeline")


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


def _validate(cfg: RepresentativeConfig) -> None:
    p = cfg.plot
    if p.x_min is not None and p.x_max is not None and p.x_min >= p.x_max:
        raise ValueError(f"plot.x_min({p.x_min}) 必须小于 x_max({p.x_max})")
    if p.y_min is not None and p.y_max is not None and p.y_min >= p.y_max:
        raise ValueError(f"plot.y_min({p.y_min}) 必须小于 y_max({p.y_max})")
    if p.figure_dpi <= 0:
        raise ValueError(f"figure_dpi 必须为正整数，实际 {p.figure_dpi}")
    if p.line_width <= 0:
        raise ValueError(f"line_width 必须为正数，实际 {p.line_width}")
    if cfg.input.wavelength_tolerance < 0:
        raise ValueError(
            f"wavelength_tolerance 必须为非负数，实际 {cfg.input.wavelength_tolerance}")


def _write_txt(path: Path, wavelengths: np.ndarray, reflectance: np.ndarray) -> None:
    """输出代表性光谱 TXT，保留完整波长范围与原始坐标精度。"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("Wavelength\tReflectance\n")
        for w, r in zip(wavelengths, reflectance):
            f.write(f"{w:.6f}\t{r:.8f}\n")


def run(cfg: RepresentativeConfig) -> dict:
    """执行代表性光谱提取流程。

    Returns:
        处理摘要 dict
    """
    t0 = time.time()
    _validate(cfg)

    # 1. 识别样本子文件夹
    samples = discover_samples(cfg.input.data_dir, cfg.input.file_glob)
    log.info("输入总文件夹: %s", cfg.input.data_dir)
    log.info("识别到 %d 个样本子文件夹: %s", len(samples), "、".join(samples.keys()) or "（无）")

    # 2. 逐样本读取 + 一致性检查 + 算术平均
    results: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    file_counts: dict[str, int] = {}
    skipped: dict[str, str] = {}
    for name, files in samples.items():
        if not files:
            skipped[name] = "文件夹内没有匹配的 TXT 文件"
            log.warning("样本 %s: 文件夹内没有匹配 %s 的 TXT 文件", name, cfg.input.file_glob)
            continue

        spectra = []
        for f in files:
            try:
                spec, warns = read_rep_spectrum(f, cfg.input)
            except ValueError as e:
                log.error("跳过文件 %s: %s", f.name, e)
                continue
            for w in warns:
                log.info("%s", w)
            spectra.append(spec)

        if not spectra:
            skipped[name] = "没有可读取的有效光谱文件"
            log.warning("样本 %s: 没有可读取的有效光谱文件", name)
            continue

        msgs = check_sample_wavelengths(spectra, cfg.input.wavelength_tolerance)
        if msgs:
            skipped[name] = "波长坐标不一致，暂停平均计算"
            log.warning("样本 %s 波长坐标不一致，暂停平均计算：", name)
            for m in msgs:
                log.warning("  - %s", m)
            continue

        wl, mean = mean_spectrum(spectra)
        results[name] = (wl, mean)
        file_counts[name] = len(spectra)
        log.info("样本 %s: 读取 %d 条光谱，波长 %d 点（%.2f–%.2f nm），完成算术平均",
                 name, len(spectra), wl.size, float(wl.min()), float(wl.max()))

    if not results:
        raise SystemExit("没有成功计算任何样本的代表性光谱，请检查输入数据")

    # 3. 跨样本波长一致性检查
    cross_msgs = check_cross_sample_wavelengths(results, cfg.input.wavelength_tolerance)

    # 4. 创建独立输出目录（不覆盖历史结果）
    run_dir = _run_dir(cfg.output.out_dir)
    data_dir = run_dir / "01_代表性光谱数据"
    plot_dir = run_dir / "02_光谱曲线图"
    data_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    log.info("输出目录: %s", run_dir)

    # 5. 输出代表性光谱 TXT + 单样本图
    for name, (wl, mean) in results.items():
        _write_txt(data_dir / f"{name}_代表性光谱.txt", wl, mean)
        representative_plot.plot_single(
            name, wl, mean, cfg.plot, plot_dir / f"{name}_代表性光谱.png")

    # 6. 全部样本对比图（仅当跨样本波长一致时生成）
    if cross_msgs:
        log.warning("不同样本代表性光谱波长坐标不一致，不生成全部样本对比图：")
        for m in cross_msgs:
            log.warning("  - %s", m)
    else:
        representative_plot.plot_all(results, cfg.plot, plot_dir / "全部样本代表性光谱对比.png")

    summary = {
        "input_dir": str(cfg.input.data_dir),
        "n_samples_total": len(samples),
        "n_samples_computed": len(results),
        "samples": list(results.keys()),
        "n_files_per_sample": file_counts,
        "skipped": skipped,
        "cross_sample_wavelength_consistent": not bool(cross_msgs),
        "data_dir": str(data_dir),
        "plot_dir": str(plot_dir),
        "runtime_seconds": round(time.time() - t0, 3),
    }

    log.info("处理完成: 成功 %d/%d 个样本，用时 %.2f s",
             len(results), len(samples), summary["runtime_seconds"])
    return summary