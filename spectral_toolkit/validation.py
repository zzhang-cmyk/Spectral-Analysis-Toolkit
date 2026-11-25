"""参数与数据合法性校验模块。"""
from __future__ import annotations

import logging

import numpy as np

from .config import SGParams, PlotConfig, ProcessingConfig

log = logging.getLogger("spectral_toolkit.validation")

_VALID_MODES = ("interp", "nearest", "mirror", "constant", "wrap")
_VALID_RESAMPLE = ("auto", "always", "never")
_VALID_RESAMPLE_METHOD = ("linear", "nearest", "cubic")


def validate_sg_params(sg: SGParams) -> None:
    """校验 SG 平滑参数。

    - window_length 必须为正整数且为奇数
    - window_length 必须大于 polyorder
    - polyorder / deriv 必须为非负整数
    - mode 必须在允许集合内

    Raises:
        ValueError: 参数非法
    """
    wl = sg.window_length
    po = sg.polyorder
    d = sg.deriv

    if not isinstance(wl, int) or isinstance(wl, bool) or wl <= 0:
        raise ValueError(f"window_length 必须为正整数，实际 {wl!r}")
    if wl % 2 == 0:
        raise ValueError(f"window_length 必须为奇数，实际 {wl}")

    if not isinstance(po, int) or isinstance(po, bool) or po < 0:
        raise ValueError(f"polyorder 必须为非负整数，实际 {po!r}")
    if po >= wl:
        raise ValueError(f"window_length({wl}) 必须大于 polyorder({po})")

    if not isinstance(d, int) or isinstance(d, bool) or d < 0:
        raise ValueError(f"deriv 必须为非负整数，实际 {d!r}")
    if d > po:
        log.warning("deriv(%d) 大于 polyorder(%d)，结果将趋于平坦，请确认", d, po)

    if sg.mode not in _VALID_MODES:
        raise ValueError(f"mode 非法: {sg.mode!r}，允许 {_VALID_MODES}")


def validate_processing_config(proc: ProcessingConfig) -> None:
    """校验实际处理范围与重采样配置。"""
    if proc.wavelength_min is not None and proc.wavelength_max is not None \
            and proc.wavelength_min >= proc.wavelength_max:
        raise ValueError(
            f"processing.wavelength_min({proc.wavelength_min}) 必须小于 wavelength_max({proc.wavelength_max})")
    if proc.resample not in _VALID_RESAMPLE:
        raise ValueError(f"resample 非法: {proc.resample!r}，允许 {_VALID_RESAMPLE}")
    if proc.resample_method not in _VALID_RESAMPLE_METHOD:
        raise ValueError(
            f"resample_method 非法: {proc.resample_method!r}，允许 {_VALID_RESAMPLE_METHOD}")
    if proc.resample_step is not None and proc.resample_step <= 0:
        raise ValueError(f"resample_step 必须为正数，实际 {proc.resample_step}")


def wavelength_interval_stats(wavelengths: np.ndarray, rtol: float = 1e-5) -> dict:
    """统计波长间隔。

    Returns:
        dict: n_points / uniform / median_step / min_step / max_step / msg
    """
    wl = np.asarray(wavelengths, dtype=float)
    info: dict = {
        "n_points": int(wl.size),
        "uniform": True,
        "median_step": None,
        "min_step": None,
        "max_step": None,
        "msg": "波长间隔均匀",
    }
    if wl.size < 2:
        info["msg"] = "波长点数过少，无法判断间隔"
        return info

    d = np.diff(wl)
    info["median_step"] = float(np.median(d))
    info["min_step"] = float(d.min())
    info["max_step"] = float(d.max())

    if np.any(d <= 0):
        info["uniform"] = False
        info["msg"] = "波长未严格递增（存在重复或倒序）"
        return info

    spread = float(d.max() - d.min())
    if spread > rtol * float(np.median(d)):
        info["uniform"] = False
        info["msg"] = (f"波长间隔不均匀（最大 {d.max():.6g}，最小 {d.min():.6g}，"
                       f"中位数 {np.median(d):.6g}）")
    return info


def check_uniform_wavelength(wavelengths: np.ndarray, rtol: float = 1e-5) -> tuple[bool, str, float | None]:
    """检查波长间隔是否均匀。

    Returns:
        (是否均匀, 说明信息, 间隔中位数)
    """
    info = wavelength_interval_stats(wavelengths, rtol)
    return info["uniform"], info["msg"], info["median_step"]


def validate_plot_config(plot: PlotConfig) -> None:
    """校验绘图配置。

    Raises:
        ValueError: 范围 / dpi / 线宽非法
    """
    if plot.x_min is not None and plot.x_max is not None and plot.x_min >= plot.x_max:
        raise ValueError(f"plot.x_min({plot.x_min}) 必须小于 x_max({plot.x_max})")
    if plot.y_min is not None and plot.y_max is not None and plot.y_min >= plot.y_max:
        raise ValueError(f"plot.y_min({plot.y_min}) 必须小于 y_max({plot.y_max})")
    if plot.figure_dpi <= 0:
        raise ValueError(f"figure_dpi 必须为正整数，实际 {plot.figure_dpi}")
    if plot.line_width <= 0:
        raise ValueError(f"line_width 必须为正数，实际 {plot.line_width}")