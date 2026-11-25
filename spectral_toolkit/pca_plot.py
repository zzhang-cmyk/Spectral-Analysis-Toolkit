"""PCA 主成分分析绘图模块。

统一科研绘图风格：白色背景、黑色坐标轴、默认无网格、连续实线、
中文样本名称正常显示、图例与数据点不遮挡。

支持：
1. 得分图（Score Plot）：按第二级样本文件夹颜色分组，可切换主成分组合
2. 载荷图（Loading Plot）：PC1/PC2/PC3 载荷曲线（横轴 Wavelength）
3. 方差贡献率柱状图
4. 累计方差贡献率折线图
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无 GUI 环境安全后端

import matplotlib.font_manager as _fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from .config import PcaPlotConfig

# 优先使用支持中文的字体，避免图例出现乱码或方块
_available = {f.name for f in _fm.fontManager.ttflist}
for _name in ("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"):
    if _name in _available:
        plt.rcParams["font.sans-serif"] = [_name, "DejaVu Sans"]
        break
plt.rcParams["axes.unicode_minus"] = False


def _distinct_colors(n: int) -> list:
    """返回 n 个区分度较高的颜色（最多支持 60 个）。"""
    palettes = ["tab20", "tab20b", "tab20c"]
    colors: list = []
    p = 0
    while len(colors) < n:
        cmap = plt.get_cmap(palettes[p % len(palettes)])
        for j in range(20):
            colors.append(cmap(j))
            if len(colors) >= n:
                break
        p += 1
    return colors[:n]


# 树种级得分图使用的高区分度、饱和颜色（不同树种明显不同）
_SPECIES_COLORS = [
    "#e6194B", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
    "#f032e6", "#bfef45", "#fabed4", "#469990", "#9A6324", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#dcbeff", "#a9a9a9",
]


def _species_colors(n: int) -> list:
    """返回 n 个高区分度、饱和的颜色；超过内置数量时续接 tab20。"""
    colors = list(_SPECIES_COLORS)
    if n > len(colors):
        colors += _distinct_colors(n - len(colors))
    return colors[:n]


# 树种级得分图中，同一树种内不同样本使用不同散点形状（循环复用）
_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*", "p", "h", "<", ">", "d", "H", "8"]


def _unique_in_order(seq: list) -> list:
    """保留首次出现顺序的去重列表。"""
    seen: list = []
    for x in seq:
        if x not in seen:
            seen.append(x)
    return seen


def _legend_frame_kwargs() -> dict:
    """得分图图例统一边框样式：白底、100% 不透明、黑色实线、直角矩形。"""
    return dict(
        fancybox=False,      # 取消圆角，直角矩形
        framealpha=1.0,      # 背景 100% 不透明
        edgecolor="black",   # 黑色实线边框
        facecolor="white",   # 白色背景
    )


def _style_legend_frame(leg) -> None:
    """设置图例边框宽度（0.8 pt）。"""
    leg.set_frame_on(True)
    leg.get_frame().set_linewidth(0.8)


def _new_axes(cfg: PcaPlotConfig, title: str):
    """创建统一风格坐标轴：白底、黑边框、默认无网格。"""
    fig, ax = plt.subplots(figsize=cfg.figsize)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(1.0)
    ax.set_title(title, fontsize=cfg.font_size + 2)
    ax.grid(cfg.grid)
    ax.tick_params(labelsize=cfg.font_size - 1)
    return fig, ax


def _save(fig, path: Path, dpi: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def plot_score_sample(
    scores: np.ndarray,
    sample_keys: list[str],
    legend_labels: dict[str, str],
    explained_variance_ratio: np.ndarray,
    pair: tuple[int, int],
    cfg: PcaPlotConfig,
    out_path: Path,
) -> None:
    """绘制样本级 PCA 得分图（按第二级样本文件夹颜色分组）。

    同一样本的全部散点使用相同颜色，不同样本使用不同颜色；
    图例采用样本子文件夹名称。
    """
    a, b = pair
    x = scores[:, a - 1]
    y = scores[:, b - 1]

    unique_keys = _unique_in_order(sample_keys)
    colors = _distinct_colors(len(unique_keys))
    key_color = {k: colors[i] for i, k in enumerate(unique_keys)}

    fig, ax = _new_axes(cfg, f"PCA 得分图（PC{a}-PC{b}）")
    for k in unique_keys:
        mask = np.array([s == k for s in sample_keys])
        ax.scatter(
            x[mask], y[mask],
            s=cfg.scatter_size, alpha=cfg.scatter_alpha, color=key_color[k],
            marker="o", label=legend_labels.get(k, k), edgecolors="none",
        )

    ax.set_xlabel(f"PC{a}（{_pct(explained_variance_ratio[a - 1])}）", fontsize=cfg.font_size)
    ax.set_ylabel(f"PC{b}（{_pct(explained_variance_ratio[b - 1])}）", fontsize=cfg.font_size)

    _score_legend(ax, cfg, len(unique_keys))
    _save(fig, out_path, cfg.figure_dpi)


def plot_score_species(
    scores: np.ndarray,
    sample_keys: list[str],
    categories: list[str],
    legend_labels: dict[str, str],
    explained_variance_ratio: np.ndarray,
    pair: tuple[int, int],
    cfg: PcaPlotConfig,
    out_path: Path,
) -> None:
    """绘制树种级 PCA 得分图（按第一级类别文件夹颜色分组）。

    同一树种的散点使用相同颜色；同一树种内不同独立样本使用不同散点形状。
    图例每个样本一个条目，同时携带其树种颜色与散点形状。
    与样本级得分图共用同一组 PCA 得分，坐标、散点位置、方差贡献率完全一致。
    """
    a, b = pair
    x = scores[:, a - 1]
    y = scores[:, b - 1]

    unique_keys = _unique_in_order(sample_keys)
    unique_species = _unique_in_order(categories)
    species_color = dict(zip(unique_species, _species_colors(len(unique_species))))
    sample_marker = {k: _MARKERS[i % len(_MARKERS)] for i, k in enumerate(unique_keys)}
    key_species: dict[str, str] = {}
    for k, c in zip(sample_keys, categories):
        key_species.setdefault(k, c)

    fig, ax = _new_axes(cfg, f"PCA 得分图（PC{a}-PC{b}）")
    for k in unique_keys:
        mask = np.array([s == k for s in sample_keys])
        ax.scatter(
            x[mask], y[mask],
            s=cfg.scatter_size, alpha=cfg.scatter_alpha,
            color=species_color[key_species[k]], marker=sample_marker[k],
            edgecolors="none",
        )

    ax.set_xlabel(f"PC{a}（{_pct(explained_variance_ratio[a - 1])}）", fontsize=cfg.font_size)
    ax.set_ylabel(f"PC{b}（{_pct(explained_variance_ratio[b - 1])}）", fontsize=cfg.font_size)

    # 图例：每个样本一个条目，同时携带其树种颜色与散点形状
    handles = [Line2D([], [], marker=sample_marker[k],
                      color=species_color[key_species[k]],
                      linestyle="None", markersize=8) for k in unique_keys]
    labels = [legend_labels.get(k, k) for k in unique_keys]
    _score_legend(ax, cfg, len(unique_keys), handles=handles, labels=labels)
    _save(fig, out_path, cfg.figure_dpi)


def _axes_data_points(ax):
    """收集坐标轴内所有数据点（散点 + 折线），用于判断图例是否遮挡。"""
    pts = []
    for coll in ax.collections:
        offs = np.asarray(coll.get_offsets(), dtype=float)
        if len(offs):
            pts.append(offs)
    for line in ax.lines:
        data = np.asarray(line.get_xydata(), dtype=float)
        if len(data):
            pts.append(data)
    if not pts:
        return None
    return np.vstack(pts)


def _legend_overlap_count(ax, leg, points):
    """统计落在图例框内的数据点数量（越少表示遮挡越轻）。"""
    if points is None or len(points) == 0:
        return 0
    try:
        ax.figure.canvas.draw()
        bbox = leg.get_window_extent()
        inv = ax.transData.inverted()
        (x0, y0) = inv.transform([[bbox.x0, bbox.y0]])[0]
        (x1, y1) = inv.transform([[bbox.x1, bbox.y1]])[0]
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        inside = (points[:, 0] >= x0) & (points[:, 0] <= x1) & \
                 (points[:, 1] >= y0) & (points[:, 1] <= y1)
        return int(inside.sum())
    except Exception:
        return 0


def _score_legend(ax, cfg: PcaPlotConfig, n_labels: int,
                  handles=None, labels=None) -> None:
    """得分图图例：白底不透明、黑色实线直角边框；自适应选择不遮挡散点的位置（始终在图框内）。"""
    if handles is None:
        handles, labels = ax.get_legend_handles_labels()
    if not labels:
        return
    ncol = min(cfg.legend_max_ncol, max(1, n_labels))
    fontsize = cfg.font_size - 1
    kw = _legend_frame_kwargs()
    loc = cfg.legend_loc if cfg.legend_loc else "best"

    if loc != "best":
        leg = ax.legend(handles, labels, loc=loc, borderaxespad=0.8,
                        fontsize=fontsize, ncol=ncol, **kw)
        _style_legend_frame(leg)
        return

    # 自适应：优先放下方，覆盖到数据点时向上/向两侧移动，始终在图框内
    points = _axes_data_points(ax)
    candidates = ["lower right", "lower left",
                  "upper right", "upper left",
                  "center right", "center left",
                  "upper center", "lower center", "center"]
    best_loc = candidates[0]
    best_overlap = float("inf")
    for loc_c in candidates:
        leg = ax.legend(handles, labels, loc=loc_c, borderaxespad=0.8,
                        fontsize=fontsize, ncol=ncol, **kw)
        ov = _legend_overlap_count(ax, leg, points)
        if ov < best_overlap:
            best_overlap = ov
            best_loc = loc_c
        if ov == 0:
            break
    leg = ax.legend(handles, labels, loc=best_loc, borderaxespad=0.8,
                    fontsize=fontsize, ncol=ncol, **kw)
    _style_legend_frame(leg)


def plot_loadings(
    wavelengths: np.ndarray,
    loadings: np.ndarray,
    pc_indices: list[int],
    cfg: PcaPlotConfig,
    out_path: Path,
) -> None:
    """绘制主成分载荷图（PC1/PC2 及可选的 PC3）。

    Args:
        wavelengths: 波长坐标（P 个）
        loadings: K×P 载荷矩阵（components_）
        pc_indices: 需要绘制的主成分编号列表（从 1 开始）
        cfg: 绘图配置
        out_path: 输出 PNG 路径
    """
    mask = np.ones(wavelengths.size, dtype=bool)
    if cfg.loading_x_min is not None:
        mask &= wavelengths >= cfg.loading_x_min
    if cfg.loading_x_max is not None:
        mask &= wavelengths <= cfg.loading_x_max

    title = "主成分载荷图"
    fig, ax = _new_axes(cfg, title)
    for i, pc in enumerate(pc_indices):
        color = _distinct_colors(3)[i % 3]
        ax.plot(wavelengths[mask], loadings[pc - 1][mask],
                color=color, lw=1.5, label=f"PC{pc}")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("Wavelength (nm)", fontsize=cfg.font_size)
    ax.set_ylabel("Loading", fontsize=cfg.font_size)
    if cfg.loading_x_min is not None:
        ax.set_xlim(left=cfg.loading_x_min)
    if cfg.loading_x_max is not None:
        ax.set_xlim(right=cfg.loading_x_max)
    ax.legend(loc="best", fontsize=cfg.font_size - 1, frameon=False)
    _save(fig, out_path, cfg.figure_dpi)


def plot_explained_variance(
    explained_variance_ratio: np.ndarray,
    cfg: PcaPlotConfig,
    out_path: Path,
) -> None:
    """绘制主成分方差贡献率柱状图。"""
    n = min(len(explained_variance_ratio), cfg.max_variance_bars)
    evr = explained_variance_ratio[:n] * 100
    labels = [f"PC{i + 1}" for i in range(n)]

    fig, ax = _new_axes(cfg, "主成分方差贡献率")
    bars = ax.bar(labels, evr, color="#4C72B0", width=0.6)
    ax.set_xlabel("Principal Components", fontsize=cfg.font_size)
    ax.set_ylabel("Explained Variance Ratio (%)", fontsize=cfg.font_size)
    for bar, v in zip(bars, evr):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.2f}%", ha="center", va="bottom", fontsize=cfg.font_size - 2)
    _save(fig, out_path, cfg.figure_dpi)


def plot_cumulative_variance(
    cumulative_variance_ratio: np.ndarray,
    cfg: PcaPlotConfig,
    out_path: Path,
) -> None:
    """绘制累计方差贡献率折线图。"""
    n = min(len(cumulative_variance_ratio), cfg.max_variance_bars)
    cum = cumulative_variance_ratio[:n] * 100
    xs = np.arange(1, n + 1)
    labels = [f"PC{i}" for i in xs]

    fig, ax = _new_axes(cfg, "累计方差贡献率")
    ax.plot(xs, cum, color="#C44E52", marker="o", lw=1.5)
    ax.set_xlabel("Principal Components", fontsize=cfg.font_size)
    ax.set_ylabel("Cumulative Explained Variance Ratio (%)", fontsize=cfg.font_size)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    for x, v in zip(xs, cum):
        ax.text(x, v, f"{v:.2f}%", ha="center", va="bottom", fontsize=cfg.font_size - 2)
    _save(fig, out_path, cfg.figure_dpi)