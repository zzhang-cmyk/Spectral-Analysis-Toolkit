"""绘图模块。

统一科研绘图风格：白色背景、黑色边框、默认无网格、无数据点标记、
图例默认左上角、可配置线宽 / 标题 / 字体 / 图例位置。

支持模式：
1. 单条光谱原始 + SG 平滑叠加
2. 多条光谱曲线叠加
3. 同一样本多次扫描对比
4. 不同样本之间的光谱曲线对比
5. 平滑前后多条光谱对比
6. 平均光谱 + 标准差阴影（预留）

所有绘图仅通过 plot.x_min/x_max 控制显示范围，不影响 SG 处理范围。
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无 GUI 环境安全后端

import matplotlib.font_manager as _fm
import matplotlib.pyplot as plt
import numpy as np

from .config import PlotConfig
from .data_io import Spectrum

# 优先使用支持中文的字体，避免标题/轴名出现乱码或方块
_available = {f.name for f in _fm.fontManager.ttflist}
for _name in ("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"):
    if _name in _available:
        plt.rcParams["font.sans-serif"] = [_name, "DejaVu Sans"]
        break
plt.rcParams["axes.unicode_minus"] = False


def _label(s: Spectrum, cfg: PlotConfig) -> str:
    """图例名称：默认采用文件名主名，支持自定义覆盖。"""
    return cfg.legend_labels.get(s.source_file.stem, s.source_file.stem)


def _slice(wl: np.ndarray, val: np.ndarray, cfg: PlotConfig):
    """按绘图显示范围切片（仅影响显示）。"""
    mask = np.ones(len(wl), dtype=bool)
    if cfg.x_min is not None:
        mask &= wl >= cfg.x_min
    if cfg.x_max is not None:
        mask &= wl <= cfg.x_max
    return wl[mask], val[mask]


def _new_axes(cfg: PlotConfig):
    """创建统一风格坐标轴：白底、黑边框、默认无网格。"""
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(1.0)
    ax.set_title(cfg.title, fontsize=cfg.font_size + 2)
    ax.set_xlabel(cfg.xlabel, fontsize=cfg.font_size)
    ax.set_ylabel(cfg.ylabel, fontsize=cfg.font_size)
    if cfg.x_min is not None:
        ax.set_xlim(left=cfg.x_min)
    if cfg.x_max is not None:
        ax.set_xlim(right=cfg.x_max)
    if cfg.y_min is not None:
        ax.set_ylim(bottom=cfg.y_min)
    if cfg.y_max is not None:
        ax.set_ylim(top=cfg.y_max)
    ax.grid(cfg.grid)
    ax.tick_params(labelsize=cfg.font_size - 1)
    return fig, ax


def _legend(ax, cfg: PlotConfig) -> None:
    handles, labels = ax.get_legend_handles_labels()
    if not labels:
        return
    # 图例保持在图框内，用 best 自动选择不遮挡光谱曲线的位置
    loc = cfg.legend_loc if cfg.legend_loc else "best"
    ncol = 2 if len(labels) >= 6 else 1
    ax.legend(loc=loc, fontsize=cfg.font_size - 1, ncol=ncol)


def _save(fig, path: Path, dpi: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_single_overlay(spectrum: Spectrum, smoothed: np.ndarray,
                        cfg: PlotConfig, out_path: Path) -> None:
    """单条光谱原始与平滑曲线叠加对比。"""
    wl, raw = _slice(spectrum.wavelengths, spectrum.reflectance, cfg)
    _, sm = _slice(spectrum.wavelengths, smoothed, cfg)
    fig, ax = _new_axes(cfg)
    ax.plot(wl, raw, label="原始", color="#1f77b4", lw=cfg.line_width)
    ax.plot(wl, sm, label="SG平滑", color="#d62728", lw=cfg.line_width)
    _legend(ax, cfg)
    _save(fig, out_path, cfg.figure_dpi)


def plot_multi_curves(spectra: list[Spectrum], cfg: PlotConfig, out_path: Path) -> None:
    """多条平滑后光谱曲线叠加。"""
    fig, ax = _new_axes(cfg)
    cmap = plt.get_cmap("tab10")
    for i, s in enumerate(spectra):
        values = s.smoothed if s.smoothed is not None else s.reflectance
        wl, v = _slice(s.wavelengths, values, cfg)
        ax.plot(wl, v, label=_label(s, cfg), color=cmap(i % 10), lw=cfg.line_width)
    _legend(ax, cfg)
    _save(fig, out_path, cfg.figure_dpi)


def plot_sample_scans(sample_id: str, spectra: list[Spectrum],
                      cfg: PlotConfig, out_path: Path) -> None:
    """同一样本不同扫描次数的平滑后光谱曲线对比。"""
    fig, ax = _new_axes(cfg)
    cmap = plt.get_cmap("tab10")
    for i, s in enumerate(spectra):
        values = s.smoothed if s.smoothed is not None else s.reflectance
        wl, v = _slice(s.wavelengths, values, cfg)
        ax.plot(wl, v, label=_label(s, cfg), color=cmap(i % 10), lw=cfg.line_width)
    ax.set_title(f"{cfg.title} - 样本 {sample_id}")
    _legend(ax, cfg)
    _save(fig, out_path, cfg.figure_dpi)


def _mean_of_sample(spectra: list[Spectrum], use_smoothed: bool) -> tuple[np.ndarray, np.ndarray]:
    """对同一样本的多次扫描在参考波长网格上取平均。"""
    ref_wl = spectra[0].wavelengths
    src = [s.smoothed if (use_smoothed and s.smoothed is not None) else s.reflectance
           for s in spectra]
    all_vals = np.vstack([np.interp(ref_wl, s.wavelengths, v) for s, v in zip(spectra, src)])
    return ref_wl, all_vals.mean(axis=0)


def plot_sample_comparison(groups: dict[str, list[Spectrum]], cfg: PlotConfig,
                           out_path: Path, use_smoothed: bool = True) -> None:
    """不同样本之间的光谱曲线对比（每个样本取多次扫描平均）。"""
    fig, ax = _new_axes(cfg)
    cmap = plt.get_cmap("tab10")
    for i, (sample_id, spectra) in enumerate(groups.items()):
        wl, mean = _mean_of_sample(spectra, use_smoothed)
        wl_s, mean_s = _slice(wl, mean, cfg)
        ax.plot(wl_s, mean_s, label=f"样本 {sample_id}", color=cmap(i % 10), lw=cfg.line_width)
    _legend(ax, cfg)
    _save(fig, out_path, cfg.figure_dpi)


def plot_before_after(spectra: list[Spectrum], cfg: PlotConfig, out_path: Path) -> None:
    """平滑前后多条光谱对比：浅灰为原始，彩色为平滑后。"""
    fig, ax = _new_axes(cfg)
    cmap = plt.get_cmap("tab10")
    for i, s in enumerate(spectra):
        wl, raw = _slice(s.wavelengths, s.reflectance, cfg)
        _, sm = _slice(s.wavelengths, s.smoothed, cfg)
        ax.plot(wl, raw, color="0.80", lw=0.8, alpha=0.7)
        ax.plot(wl, sm, label=_label(s, cfg), color=cmap(i % 10), lw=cfg.line_width)
    _legend(ax, cfg)
    _save(fig, out_path, cfg.figure_dpi)


def plot_mean_std(spectra: list[Spectrum], cfg: PlotConfig, out_path: Path) -> None:
    """平均光谱 + 标准差阴影（预留功能）。"""
    ref = spectra[0]
    wl = ref.wavelengths
    # 不同光谱波长网格可能略有差异，统一插值到参考网格后再统计
    all_vals = np.vstack([np.interp(wl, s.wavelengths, s.reflectance) for s in spectra])
    mean = all_vals.mean(axis=0)
    std = all_vals.std(axis=0)

    wl_s, mean_s = _slice(wl, mean, cfg)
    _, std_s = _slice(wl, std, cfg)

    fig, ax = _new_axes(cfg)
    ax.plot(wl_s, mean_s, color="#1f77b4", lw=cfg.line_width, label="平均光谱")
    ax.fill_between(wl_s, mean_s - std_s, mean_s + std_s,
                    color="#1f77b4", alpha=0.25, label="±1 标准差")
    _legend(ax, cfg)
    _save(fig, out_path, cfg.figure_dpi)