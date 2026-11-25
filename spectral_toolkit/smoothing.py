"""Savitzky-Golay 平滑模块。

基于 scipy.signal.savgol_filter；每条光谱独立沿波长维度处理，绝不跨样本平滑。

波长采样间隔处理：
1. 计算原始波长间隔及中位数。
2. 在实际处理波段内建立均匀波长网格。
3. 线性插值将原始反射率转换到均匀网格。
4. 在均匀网格上执行 SG 平滑。
5. 将平滑结果插值回原始波长坐标。
6. 输出时保留原始波长坐标。

若原始数据已满足均匀采样要求（且未强制重采样），则直接进行 SG 平滑。

Smoother 基类为未来扩展其他预处理算法（如 SNV、导数等）预留接口。
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import interp1d
from scipy.signal import savgol_filter

from .config import SGParams, ProcessingConfig
from .data_io import Spectrum
from .validation import wavelength_interval_stats


class Smoother:
    """平滑器基类：所有预处理算法实现 smooth(wavelengths, values) -> values。"""

    def smooth(self, wavelengths: np.ndarray, values: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class SavitzkyGolaySmoother(Smoother):
    """Savitzky-Golay 平滑器。"""

    def __init__(self, sg: SGParams):
        self.sg = sg

    def smooth(self, wavelengths: np.ndarray, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=float)
        # savgol_filter 沿索引维度平滑；对单条光谱整条处理
        return savgol_filter(
            values,
            window_length=self.sg.window_length,
            polyorder=self.sg.polyorder,
            deriv=self.sg.deriv,
            mode=self.sg.mode,
        )


def _interp_values(x_new: np.ndarray, x_old: np.ndarray, y_old: np.ndarray,
                   method: str = "linear") -> np.ndarray:
    """将 y 从 x_old 插值到 x_new。"""
    if x_new.size == 0:
        return np.array([], dtype=float)
    if x_old.size < 2:
        return np.full(x_new.size, float(y_old[0]) if y_old.size else np.nan)
    kind = method if method in ("linear", "nearest", "cubic") else "linear"
    f = interp1d(x_old, y_old, kind=kind, bounds_error=False,
                 fill_value=(y_old[0], y_old[-1]))
    return np.asarray(f(x_new), dtype=float)


def smooth_spectrum(spectrum: Spectrum, sg: SGParams,
                    proc: ProcessingConfig) -> tuple[np.ndarray, dict]:
    """对单条光谱执行处理范围选择 + 可选重采样 + SG 平滑。

    Args:
        spectrum: 单条光谱
        sg: SG 参数
        proc: 处理范围与重采样配置

    Returns:
        (smoothed, info)
        smoothed 与原始波长坐标一一对应（长度相同）；处理范围外保持原始值。
        info 记录重采样方法、均匀网格步长、SG 参数等。
    """
    wl = np.asarray(spectrum.wavelengths, dtype=float)
    rf = np.asarray(spectrum.reflectance, dtype=float)

    # 1. 实际处理范围
    proc_min = proc.wavelength_min
    proc_max = proc.wavelength_max
    mask = np.ones(wl.size, dtype=bool)
    if proc_min is not None:
        mask &= wl >= proc_min
    if proc_max is not None:
        mask &= wl <= proc_max

    sub_wl = wl[mask]
    sub_rf = rf[mask]

    # 2. 波长间隔检查（在处理范围内）
    stats = wavelength_interval_stats(sub_wl)
    uniform = bool(stats["uniform"])
    median_step = stats["median_step"]

    need_resample = (
        proc.resample == "always"
        or (proc.resample == "auto" and not uniform)
    )

    resampled = False
    resample_method = None
    resample_step = None
    n_grid = None

    if need_resample:
        step = proc.resample_step if proc.resample_step is not None else median_step
        if step is None or step <= 0:
            step = 1.0
        # 3. 在处理波段内建立均匀波长网格
        grid = np.arange(sub_wl[0], sub_wl[-1] + step * 0.5, step)
        grid = grid[grid <= sub_wl[-1] + 1e-9]
        # 4. 线性插值到均匀网格 -> SG 平滑
        rf_grid = _interp_values(grid, sub_wl, sub_rf, proc.resample_method)
        smoothed_grid = SavitzkyGolaySmoother(sg).smooth(grid, rf_grid)
        # 5. 平滑结果插值回原始波长坐标
        smoothed_sub = _interp_values(sub_wl, grid, smoothed_grid, proc.resample_method)
        resampled = True
        resample_method = proc.resample_method
        resample_step = float(step)
        n_grid = int(grid.size)
    else:
        # 数据均匀或禁用重采样：直接 SG 平滑
        smoothed_sub = SavitzkyGolaySmoother(sg).smooth(sub_wl, sub_rf)

    # 6. 组装：处理范围外保持原始值，范围内为平滑结果
    smoothed = rf.copy()
    smoothed[mask] = smoothed_sub

    info = {
        "uniform": uniform,
        "median_step": median_step,
        "resampled": resampled,
        "resample_method": resample_method,
        "resample_step": resample_step,
        "n_grid": n_grid,
        "processing_min": proc_min,
        "processing_max": proc_max,
        "sg_window_length": sg.window_length,
        "sg_polyorder": sg.polyorder,
        "sg_deriv": sg.deriv,
        "sg_mode": sg.mode,
    }
    return smoothed, info