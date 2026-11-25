"""代表性光谱绘图模块。

统一科研绘图风格：白色背景、黑色边框、默认无网格、无数据点标记、
连续实线、图例默认自动选位（best）。中文图例正常显示。

支持：
1. 单样本代表性光谱图（图例 = 样本子文件夹名称）
2. 全部样本代表性光谱对比图（图例 = 各样本子文件夹名称）

绘图横轴/纵轴范围仅控制显示，不影响已计算的完整代表性光谱数据。
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无 GUI 环境安全后端

import matplotlib.font_manager as _fm
import matplotlib.pyplot as plt
import numpy as np

from .config import RepresentativePlotConfig

# 优先使用支持中文的字体，避免图例出现乱码或方块
_available = {f.name for f in _fm.fontManager.ttflist}
for _name in ("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"):
    if _name in _available:
        plt.rcParams["font.sans-serif"] = [_name, "DejaVu Sans"]
        break
plt.rcParams["axes.unicode_minus"] = False


def _slice(wl: np.ndarray, val: np.ndarray, cfg: RepresentativePlotConfig):
    """按绘图横轴显示范围切片（仅影响显示）。"""
    mask = np.ones(len(wl), dtype=bool)
    if cfg.x_min is not None:
        mask &= wl >= cfg.x_min
    if cfg.x_max is not None:
        mask &= wl <= cfg.x_max
    return wl[mask], val[mask]


def _new_axes(cfg: RepresentativePlotConfig, title: str):
    """创建统一风格坐标轴：白底、黑边框、默认无网格。"""
    fig, ax = plt.subplots(figsize=cfg.figsize)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(1.0)
    ax.set_title(title, fontsize=cfg.font_size + 2)
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


def _legend(ax, cfg: RepresentativePlotConfig) -> None:
    handles, labels = ax.get_legend_handles_labels()
    if not labels:
        return
    loc = cfg.legend_loc if cfg.legend_loc else "best"
    ncol = 2 if len(labels) >= 6 else 1
    ax.legend(loc=loc, fontsize=cfg.font_size - 1, ncol=ncol)


def _save(fig, path: Path, dpi: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _color(i: int):
    """返回区分度较高的曲线颜色。"""
    cmap = plt.get_cmap("tab20") if i >= 10 else plt.get_cmap("tab10")
    return cmap(i % (20 if i >= 10 else 10))


def plot_single(sample_name: str, wavelengths: np.ndarray, reflectance: np.ndarray,
                cfg: RepresentativePlotConfig, out_path: Path) -> None:
    """绘制单样本代表性光谱曲线，图例使用样本子文件夹名称。"""
    wl, refl = _slice(wavelengths, reflectance, cfg)
    fig, ax = _new_axes(cfg, f"{sample_name} 代表性光谱")
    ax.plot(wl, refl, label=sample_name, color=_color(0), lw=cfg.line_width)
    _legend(ax, cfg)
    _save(fig, out_path, cfg.figure_dpi)


def plot_all(samples: dict[str, tuple[np.ndarray, np.ndarray]],
             cfg: RepresentativePlotConfig, out_path: Path) -> None:
    """绘制全部样本代表性光谱对比图，图例直接采用样本子文件夹名称。"""
    fig, ax = _new_axes(cfg, cfg.title)
    for i, (name, (wl, refl)) in enumerate(samples.items()):
        wl_s, refl_s = _slice(wl, refl, cfg)
        ax.plot(wl_s, refl_s, label=name, color=_color(i), lw=cfg.line_width)
    _legend(ax, cfg)
    _save(fig, out_path, cfg.figure_dpi)