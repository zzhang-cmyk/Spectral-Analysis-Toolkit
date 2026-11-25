"""PCA 主成分分析模块的完整处理流程。

流程：识别类别/样本文件夹 -> 读取全部有效单次扫描光谱 -> 波长一致性检查
      -> 波段范围切片 -> 构建数据矩阵 -> 均值中心化 -> PCA 计算
      -> 导出 Excel -> 绘制得分图/载荷图/方差贡献率图。

只输出两个结果文件夹：
- 01_PCA分析数据/
- 02_PCA结果图/

必要的运行信息与错误提示在控制台输出，不生成额外报告文件。
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import pca_plot
from .config import PcaConfig
from .pca import (
    PcaObservation,
    attach_metadata,
    build_matrix,
    check_global_wavelengths,
    compute_pca,
    discover_categories,
    legend_label_mapping,
    read_observations,
)

log = logging.getLogger("spectral_toolkit.pca_pipeline")


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


def _validate(cfg: PcaConfig) -> None:
    a = cfg.analysis
    if a.wavelength_min is not None and a.wavelength_max is not None and a.wavelength_min >= a.wavelength_max:
        raise ValueError(f"analysis.wavelength_min({a.wavelength_min}) 必须小于 wavelength_max({a.wavelength_max})")
    if a.centering != "mean":
        raise ValueError(f"第一版仅支持均值中心化（centering='mean'），实际 {a.centering!r}")
    p = cfg.plot
    if p.figure_dpi <= 0:
        raise ValueError(f"figure_dpi 必须为正整数，实际 {p.figure_dpi}")
    if p.scatter_size <= 0:
        raise ValueError(f"scatter_size 必须为正数，实际 {p.scatter_size}")
    if not (0 < p.scatter_alpha <= 1):
        raise ValueError(f"scatter_alpha 必须在 (0, 1] 区间，实际 {p.scatter_alpha}")
    if p.score_plot_mode not in ("sample", "species", "both"):
        raise ValueError(f"score_plot_mode 必须为 sample / species / both，实际 {p.score_plot_mode!r}")
    if cfg.input.wavelength_tolerance < 0:
        raise ValueError(f"wavelength_tolerance 必须为非负数，实际 {cfg.input.wavelength_tolerance}")


def _sample_counts(
    categories: dict[str, dict[str, list[Path]]], observations: list[PcaObservation],
) -> dict[str, tuple[int, int]]:
    """统计每个样本的原始 TXT 数量与有效观测数量。

    Returns:
        {"类别/样本": (原始TXT数量, 有效光谱数量)}
    """
    original: dict[str, int] = {}
    for cat, samples in categories.items():
        for sample, files in samples.items():
            original[f"{cat}/{sample}"] = len(files)
    effective: dict[str, int] = Counter(o.sample_key for o in observations)
    keys = sorted(set(original) | set(effective))
    return {k: (original.get(k, 0), effective.get(k, 0)) for k in keys}


def _write_excel(result, observations: list[PcaObservation],
                 counts: dict[str, tuple[int, int]], path: Path) -> None:
    """导出 PCA 分析结果 Excel（多工作表）。"""
    k_total = result.n_components_total
    pc_names = [f"PC{i + 1}" for i in range(k_total)]

    # Sheet1：PCA 得分数据（每条 TXT 一行，可追溯原始文件）
    score_dict: dict[str, list] = {
        "Category": result.categories,
        "Sample_ID": result.sample_ids,
        "File_Name": result.file_names,
    }
    for i in range(k_total):
        score_dict[pc_names[i]] = result.scores[:, i]
    score_df = pd.DataFrame(score_dict)

    # Sheet2：PCA 载荷数据（第一列 Wavelength，后续各主成分载荷系数）
    loading_dict: dict[str, list] = {"Wavelength": result.wavelengths}
    for i in range(k_total):
        loading_dict[pc_names[i]] = result.loadings[i]
    loading_df = pd.DataFrame(loading_dict)

    # Sheet3：方差贡献率
    variance_df = pd.DataFrame({
        "主成分名称": pc_names,
        "特征值": result.eigenvalues,
        "方差贡献率": result.explained_variance_ratio,
        "累计方差贡献率": result.cumulative_variance_ratio,
    })

    # Sheet4：样本扫描数量统计
    count_rows = []
    for key, (orig, eff) in counts.items():
        cat, sample = key.split("/", 1)
        count_rows.append({
            "Category": cat,
            "Sample_ID": sample,
            "原始TXT文件数量": orig,
            "实际参与PCA的有效光谱数量": eff,
        })
    count_df = pd.DataFrame(count_rows)

    # Sheet5：PCA 输入矩阵（完整输入数据与样本对应关系）
    input_dict: dict[str, list] = {
        "Category": result.categories,
        "Sample_ID": result.sample_ids,
        "File_Name": result.file_names,
    }
    for j, wl in enumerate(result.wavelengths):
        input_dict[f"{wl:.4f}"] = result.X[:, j]
    input_df = pd.DataFrame(input_dict)

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        score_df.to_excel(xw, sheet_name="PCA得分数据", index=False)
        loading_df.to_excel(xw, sheet_name="PCA载荷数据", index=False)
        variance_df.to_excel(xw, sheet_name="方差贡献率", index=False)
        count_df.to_excel(xw, sheet_name="样本扫描数量统计", index=False)
        input_df.to_excel(xw, sheet_name="PCA输入矩阵", index=False)


def run(cfg: PcaConfig) -> dict:
    """执行 PCA 主成分分析流程。

    Returns:
        处理摘要 dict
    """
    t0 = time.time()
    _validate(cfg)

    # 1. 识别类别与样本文件夹
    categories = discover_categories(cfg.input.data_dir, cfg.input.file_glob)
    n_categories = len(categories)
    n_samples = sum(len(s) for s in categories.values())
    log.info("输入总文件夹: %s", cfg.input.data_dir)
    log.info("识别到 %d 个类别文件夹、%d 个样本文件夹", n_categories, n_samples)
    for cat, samples in categories.items():
        if not samples:
            log.warning("类别 %s: 未找到任何二级样本文件夹", cat)
        for sample, files in samples.items():
            if not files:
                log.warning("样本 %s/%s: 文件夹内没有匹配 %s 的 TXT 文件",
                            cat, sample, cfg.input.file_glob)

    # 2. 读取全部有效单次扫描光谱（每条 TXT = 一条独立观测）
    observations, invalid = read_observations(categories, cfg.input)
    if not observations:
        raise SystemExit("没有读取到任何有效光谱文件，请检查输入数据")

    if invalid:
        log.warning("以下文件无效，已列入异常文件清单：")
        for f, reason in invalid.items():
            log.warning("  - %s: %s", f, reason)

    log.info("共读取 %d 条有效单次扫描光谱", len(observations))

    # 3. 全局波长一致性检查（不一致则暂停本次 PCA）
    wl_msgs = check_global_wavelengths(observations, cfg.input.wavelength_tolerance)
    if wl_msgs:
        log.error("波长坐标不一致，暂停本次 PCA 计算：")
        for m in wl_msgs:
            log.error("  - %s", m)
        raise SystemExit("波长坐标不一致，本次 PCA 计算已暂停，请检查输入数据")

    # 4. 构建 PCA 数据矩阵（波段范围切片）
    X, wavelengths = build_matrix(
        observations, cfg.analysis.wavelength_min, cfg.analysis.wavelength_max)
    log.info("分析波段 %s–%s nm，波长变量 %d 个",
             cfg.analysis.wavelength_min, cfg.analysis.wavelength_max, wavelengths.size)
    log.info("PCA 输入矩阵维度: %d 条光谱 × %d 个波长变量", X.shape[0], X.shape[1])

    # 5. PCA 计算（内部计算全部有效主成分）
    result = compute_pca(X, cfg.analysis.n_components)
    attach_metadata(result, observations, wavelengths)

    # 6. 样本扫描数量均衡性提示
    counts = _sample_counts(categories, observations)
    eff_counts = [v[1] for v in counts.values() if v[1] > 0]
    if eff_counts and max(eff_counts) >= 2 * min(eff_counts):
        log.warning("不同样本的有效扫描数量不均衡（%d–%d 条），"
                    "扫描次数较多的样本会对总体方差结构产生更大影响，解释结果时需注意",
                    min(eff_counts), max(eff_counts))

    # 7. 创建独立输出目录（不覆盖历史结果）
    run_dir = _run_dir(cfg.output.out_dir)
    data_dir = run_dir / "01_PCA分析数据"
    plot_dir = run_dir / "02_PCA结果图"
    data_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    log.info("输出目录: %s", run_dir)

    # 8. 导出 Excel
    excel_path = data_dir / "PCA分析结果.xlsx"
    _write_excel(result, observations, counts, excel_path)

    # 9. 绘制结果图
    legend_labels = legend_label_mapping(observations)
    mode = cfg.plot.score_plot_mode
    plot_files: list[str] = []
    for pair in cfg.plot.score_pairs:
        a, b = pair
        if a > result.n_components_total or b > result.n_components_total:
            log.warning("得分图组合 PC%d-PC%d 超出有效主成分数（%d），已跳过",
                        a, b, result.n_components_total)
            continue
        # 两种模式共用同一组 PCA 得分数据，仅改变颜色分组与点形状
        if mode in ("sample", "both"):
            fname = f"PCA得分图_样本级_PC{a}-PC{b}.png"
            pca_plot.plot_score_sample(
                result.scores, result.sample_keys, legend_labels,
                result.explained_variance_ratio, pair, cfg.plot, plot_dir / fname)
            plot_files.append(fname)
        if mode in ("species", "both"):
            fname = f"PCA得分图_树种级_PC{a}-PC{b}.png"
            pca_plot.plot_score_species(
                result.scores, result.sample_keys, result.categories, legend_labels,
                result.explained_variance_ratio, pair, cfg.plot, plot_dir / fname)
            plot_files.append(fname)

    pc_indices = [1, 2] + ([3] if result.n_components_keep >= 3 else [])
    pc_indices = [p for p in pc_indices if p <= result.n_components_total]
    loading_name = "PCA载荷图_PC" + "-PC".join(str(p) for p in pc_indices) + ".png"
    pca_plot.plot_loadings(
        result.wavelengths, result.loadings, pc_indices, cfg.plot, plot_dir / loading_name)
    plot_files.append(loading_name)

    pca_plot.plot_explained_variance(
        result.explained_variance_ratio, cfg.plot, plot_dir / "PCA方差贡献率.png")
    pca_plot.plot_cumulative_variance(
        result.cumulative_variance_ratio, cfg.plot, plot_dir / "PCA累计贡献率.png")
    plot_files.append("PCA方差贡献率.png")
    plot_files.append("PCA累计贡献率.png")

    # 10. 组装摘要
    pc1_plus_pc2 = float(result.cumulative_variance_ratio[1]) if result.n_components_total >= 2 else None
    summary = {
        "input_dir": str(cfg.input.data_dir),
        "n_categories": n_categories,
        "n_samples": n_samples,
        "n_spectra": len(observations),
        "n_wavelength_vars": int(wavelengths.size),
        "analysis_band": [cfg.analysis.wavelength_min, cfg.analysis.wavelength_max],
        "n_components_total": result.n_components_total,
        "n_components_keep": result.n_components_keep,
        "explained_variance_ratio": [float(x) for x in result.explained_variance_ratio],
        "pc1_plus_pc2_cumulative": pc1_plus_pc2,
        "n_files_per_sample": {k: v for k, v in counts.items()},
        "invalid_files": invalid,
        "excel": str(excel_path),
        "plots": plot_files,
        "run_dir": str(run_dir),
        "runtime_seconds": round(time.time() - t0, 3),
    }

    log.info("PCA 计算完成: %d 条光谱、%d 个波长变量、%d 个有效主成分，用时 %.2f s",
             len(observations), wavelengths.size, result.n_components_total, summary["runtime_seconds"])
    return summary