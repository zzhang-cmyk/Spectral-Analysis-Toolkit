"""代表性光谱提取计算模块。

读取已完成 SG 平滑并剔除异常的光谱文件，按样本文件夹归类，
对同一样本的多条光谱逐波长计算算术平均值，生成代表性光谱。

核心能力：
- 遍历总输入文件夹下的一级子文件夹（每个子文件夹 = 一个样本）
- 读取样本子文件夹内的 TXT（Tab/逗号/空格/分号，多编码，自动识别波长列）
- 多数据列时优先选择标记为 Smoothed / SG_Smoothed 等平滑结果列
- 同一样本内波长坐标一致性检查
- 逐波长算术平均（各条光谱权重相同，不采用中位数/加权/插值）
- 不同样本代表性光谱波长一致性检查

本模块不进行 SG 平滑、SNV、MSC、导数等任何预处理，不计算标准差/CV 等统计量。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import RepresentativeInputConfig
from .data_io import (
    _match_column,
    _sniff_header,
    _split_line,
    _to_float,
    read_text,
    sniff_separator,
)

log = logging.getLogger("spectral_toolkit.representative")

_WAVELENGTH_KEYWORDS = ["wavelength", "wave", "波长", "波段", "lambda", "nm"]
# 平滑结果列标识：含这些关键词的列被优先视为已平滑反射率
_SMOOTH_KEYWORDS = ["smoothed", "smooth", "平滑"]


@dataclass
class RepSpectrum:
    """代表性光谱模块读取的单条光谱。"""
    wavelengths: np.ndarray
    reflectance: np.ndarray
    source_file: Path
    column_note: str = ""   # 选择的反射率列识别说明


def discover_samples(data_dir: Path, file_glob: str = "*.txt") -> dict[str, list[Path]]:
    """遍历总输入文件夹的一级子文件夹，识别样本及其 TXT 文件。

    只读取一级子文件夹内的 TXT，不递归更深层级；忽略非 TXT 与隐藏文件。

    Args:
        data_dir: 总输入文件夹
        file_glob: TXT 匹配规则

    Returns:
        {样本名称: [TXT 文件路径...]}，样本按名称排序

    Raises:
        FileNotFoundError: 输入目录不存在
        SystemExit: 未找到任何一级子文件夹
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"输入总文件夹不存在: {data_dir}")

    subdirs = sorted(
        p for p in data_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if not subdirs:
        raise SystemExit(f"在 {data_dir} 下未找到任何一级子文件夹（样本文件夹）")

    samples: dict[str, list[Path]] = {}
    for d in subdirs:
        files = sorted(
            p for p in d.glob(file_glob)
            if p.is_file() and not p.name.startswith(".") and not p.name.startswith("~$")
        )
        samples[d.name] = files
    return samples


def read_rep_spectrum(path: Path, cfg: RepresentativeInputConfig) -> tuple[RepSpectrum, list[str]]:
    """读取单个 TXT 光谱文件，自动识别波长列与反射率列。

    多数据列时的选择规则：
    - 仅一个数据列 -> 直接使用。
    - 多个数据列 -> 优先选择表头含 Smoothed/SG_Smoothed/平滑 等标识的列。
    - 多个数据列且无法明确判断 -> 抛错，提示用户检查，不擅自选择。

    Returns:
        (RepSpectrum, warnings)

    Raises:
        ValueError: 文件为空、列数异常、缺失值（按 on_missing）、列无法判断等
    """
    path = Path(path)
    text = read_text(path, cfg.encoding)
    sep = sniff_separator(text, cfg.separator)

    lines = text.splitlines()
    data_lines = [ln for ln in lines if ln.strip() != ""]
    if not data_lines:
        raise ValueError(f"文件为空: {path.name}")

    if cfg.header == "auto":
        has_header = _sniff_header(data_lines, sep)
    else:
        has_header = cfg.header == "true"

    header_names: list[str] | None = None
    start = 0
    if has_header:
        header_names = _split_line(data_lines[0], sep)
        start = 1
        if len(data_lines) == 1:
            raise ValueError(f"文件仅有表头、无数据行: {path.name}")

    first_row = _split_line(data_lines[start], sep)
    n_cols = len(header_names) if header_names is not None else len(first_row)
    if n_cols < 2:
        raise ValueError(f"列数异常: 至少需要 2 列（波长 + 反射率），实际 {n_cols} 列: {path.name}")

    warnings: list[str] = []

    # 1. 识别波长列
    if has_header and header_names:
        wl_idx = _match_column(header_names, _WAVELENGTH_KEYWORDS)
        wl_note = f"表头 {header_names[wl_idx]!r}（第{wl_idx}列）" if wl_idx is not None else "第0列（默认波长列）"
        if wl_idx is None:
            wl_idx = 0
    else:
        wl_idx = 0
        wl_note = "第0列（默认波长列）"

    # 2. 识别反射率数据列
    data_cols = [i for i in range(n_cols) if i != wl_idx]
    if not data_cols:
        raise ValueError(f"未找到反射率数据列: {path.name}")

    if len(data_cols) == 1:
        rf_idx = data_cols[0]
        rf_note = _col_note(header_names, rf_idx)
    else:
        # 多个数据列：优先平滑结果列
        smooth_cols = [
            i for i in data_cols
            if header_names is not None
            and any(kw in str(header_names[i]).strip().lower() for kw in _SMOOTH_KEYWORDS)
        ]
        if len(smooth_cols) == 1:
            rf_idx = smooth_cols[0]
            rf_note = _col_note(header_names, rf_idx) + "（识别为平滑结果列）"
        elif len(smooth_cols) > 1:
            names = ", ".join(str(header_names[i]) for i in smooth_cols)
            raise ValueError(
                f"{path.name}: 检测到多个平滑结果列 [{names}]，无法确定使用哪一列，请检查")
        else:
            names = ", ".join(str(header_names[i]) for i in data_cols)
            raise ValueError(
                f"{path.name}: 包含多个数据列 [{names}]，无法自动判断哪一列是平滑后的反射率，"
                f"请检查文件或确认列名（建议标记为 Smoothed/SG_Smoothed）")

    warnings.append(f"{path.name}: 波长列={wl_note}，反射率列={rf_note}")

    wls: list[float] = []
    rfs: list[float] = []
    for ln_no, line in enumerate(data_lines[start:], start=start + 1):
        tokens = _split_line(line, sep)
        if not tokens:
            continue
        if len(tokens) != n_cols:
            msg = f"{path.name}: 第{ln_no}行列数异常（期望 {n_cols} 列，实际 {len(tokens)} 列）"
            if cfg.on_column_error == "error":
                raise ValueError(msg)
            warnings.append(msg)
            continue
        w = _to_float(tokens[wl_idx])
        r = _to_float(tokens[rf_idx])
        if w is None or r is None:
            msg = f"{path.name}: 第{ln_no}行存在缺失值/非数值"
            if cfg.on_missing == "error":
                raise ValueError(msg)
            if cfg.on_missing == "warn":
                warnings.append(msg)
            continue
        wls.append(w)
        rfs.append(r)

    if not wls:
        raise ValueError(f"文件无有效数据行: {path.name}")

    wl_arr = np.asarray(wls, dtype=float)
    rf_arr = np.asarray(rfs, dtype=float)

    # 沿波长升序排列，保证平均计算时逐波长对齐
    order = np.argsort(wl_arr, kind="stable")
    if not np.array_equal(order, np.arange(order.size)):
        warnings.append(f"{path.name}: 波长未按升序排列，已自动排序")
    wl_arr = wl_arr[order]
    rf_arr = rf_arr[order]

    return RepSpectrum(
        wavelengths=wl_arr,
        reflectance=rf_arr,
        source_file=path,
        column_note=rf_note,
    ), warnings


def _col_note(header_names: list[str] | None, idx: int) -> str:
    if header_names is not None and idx < len(header_names):
        return f"表头 {header_names[idx]!r}（第{idx}列）"
    return f"第{idx}列"


def check_sample_wavelengths(spectra: list[RepSpectrum], tolerance: float) -> list[str]:
    """检查同一样本文件夹内多条光谱的波长坐标一致性。

    检查：波长数量、顺序、对应数值是否一致（按容差比较）。

    Returns:
        问题描述列表；为空表示一致，可计算平均。
    """
    if not spectra:
        return ["样本文件夹内没有有效光谱文件"]
    if len(spectra) == 1:
        return []

    ref = spectra[0].wavelengths
    ref_name = spectra[0].source_file.name
    msgs: list[str] = []
    for s in spectra[1:]:
        wl = s.wavelengths
        if wl.size != ref.size:
            msgs.append(
                f"{s.source_file.name}: 波长数量不一致（{wl.size} 个，参考 {ref_name} 为 {ref.size} 个）")
            continue
        if not (np.all(np.diff(wl) > 0) and np.all(np.diff(ref) > 0)):
            msgs.append(f"{s.source_file.name}: 波长顺序与参考 {ref_name} 不一致（存在重复或倒序）")
            continue
        diff = np.abs(wl - ref)
        if diff.size and float(diff.max()) > tolerance:
            idx = int(np.argmax(diff))
            msgs.append(
                f"{s.source_file.name}: 第{idx}个波长点数值不一致（{wl[idx]:.6f} vs 参考 {ref[idx]:.6f}，"
                f"差值 {diff.max():.6g}，容差 {tolerance:g}）")
    return msgs


def mean_spectrum(spectra: list[RepSpectrum]) -> tuple[np.ndarray, np.ndarray]:
    """对同一样本多条光谱逐波长计算算术平均值。

    各条光谱权重相同；要求波长坐标已经通过一致性检查。

    Returns:
        (wavelengths, mean_reflectance)
    """
    if not spectra:
        raise ValueError("无法计算平均：样本内没有有效光谱")
    wavelengths = spectra[0].wavelengths
    stack = np.vstack([s.reflectance for s in spectra])
    return wavelengths, stack.mean(axis=0)


def check_cross_sample_wavelengths(
    samples: dict[str, tuple[np.ndarray, np.ndarray]], tolerance: float,
) -> list[str]:
    """检查不同样本代表性光谱的波长坐标是否一致。

    Returns:
        问题描述列表；为空表示一致，可生成全部样本对比图。
    """
    names = list(samples.keys())
    if len(names) < 2:
        return []
    ref_name = names[0]
    ref = samples[ref_name][0]
    msgs: list[str] = []
    for name in names[1:]:
        wl = samples[name][0]
        if wl.size != ref.size:
            msgs.append(
                f"样本 {name!r} 波长数量与 {ref_name!r} 不一致（{wl.size} vs {ref.size}）")
            continue
        diff = np.abs(wl - ref)
        if diff.size and float(diff.max()) > tolerance:
            idx = int(np.argmax(diff))
            msgs.append(
                f"样本 {name!r} 与 {ref_name!r} 波长坐标不一致（第{idx}个点 "
                f"{wl[idx]:.6f} vs {ref[idx]:.6f}）")
    return msgs