"""TXT 光谱数据读取模块。

支持：
- 批量 / 单文件读取
- 常见分隔符（逗号 / 制表 / 空格 / 分号）
- 有表头 / 无表头
- 常见编码（utf-8 / gb18030 / gbk / latin-1，含 BOM）
- 识别波长列与反射率列（显式配置优先，auto 模式透明记录识别依据）
- 对读取失败、缺失值、异常列数给出明确提示

本模块只读，绝不修改 / 覆盖原始文件。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .config import InputConfig

log = logging.getLogger("spectral_toolkit.data_io")

# 常见编码，按优先级依次尝试
_ENCODINGS = ["utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"]

_WAVELENGTH_KEYWORDS = ["wavelength", "wave", "波长", "波段", "lambda", "nm"]
_REFLECTANCE_KEYWORDS = [
    "intensity", "reflectance", "reflectivity", "reflect", "absorbance",
    "反射率", "强度", "值", "value",
]


@dataclass
class Spectrum:
    """单条光谱数据。"""
    wavelengths: np.ndarray
    reflectance: np.ndarray
    source_file: Path
    sample_id: str | None = None
    scan_id: str | None = None
    smoothed: np.ndarray | None = None
    smooth_info: dict | None = None       # 平滑/重采样过程信息
    wavelength_stats: dict | None = None  # 波长间隔统计

    @property
    def label(self) -> str:
        if self.sample_id is not None and self.scan_id is not None:
            return f"{self.sample_id}-{self.scan_id}"
        return self.source_file.stem


def list_txt_files(data_dir: Path, file_glob: str = "*.txt") -> list[Path]:
    """列出目录下所有匹配的 TXT 文件（按路径排序）。

    Raises:
        FileNotFoundError: 输入目录不存在
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"输入目录不存在: {data_dir}")
    return sorted(p for p in data_dir.glob(file_glob) if p.is_file())


def read_text(path: Path, encoding: str = "auto") -> str:
    """读取文本内容，支持自动尝试多种编码。"""
    path = Path(path)
    if encoding not in ("", "auto", None):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError) as e:
            raise ValueError(f"以指定编码 {encoding!r} 读取失败: {path.name}（{e}）") from e

    last: Exception | None = None
    for enc in _ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError) as e:
            last = e
            continue
    raise ValueError(f"无法识别文件编码: {path.name}（{last}）")


def sniff_separator(text: str, hint: str = "auto") -> str:
    """推断分隔符。hint 非 auto 时直接使用。"""
    if hint not in ("", "auto", None):
        return hint
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "\t" in line:
            return "tab"
        if "," in line:
            return "comma"
        if ";" in line:
            return "semicolon"
        return "space"
    return "space"


def _split_line(line: str, sep: str) -> list[str]:
    """按分隔符切分一行。"""
    line = line.strip()
    if not line:
        return []
    if sep == "space":
        return line.split()
    if sep == "tab":
        return [t.strip() for t in line.split("\t")]
    return [t.strip() for t in line.split(sep)]


def _to_float(s: str) -> float | None:
    s = s.strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _sniff_header(data_lines: list[str], sep: str) -> bool:
    """若首行任一单元无法解析为数值，视为表头。"""
    for line in data_lines:
        tokens = _split_line(line, sep)
        if not tokens:
            continue
        return not all(_to_float(t) is not None for t in tokens)
    return False


def _match_column(header_names: list[str], keywords: list[str], exclude: int | None = None) -> int | None:
    """在表头中按关键词匹配列。"""
    for i, name in enumerate(header_names):
        if exclude is not None and i == exclude:
            continue
        n = str(name).strip().lower()
        for kw in keywords:
            if kw in n:
                return i
    return None


def _resolve_column(cfg_col: Any, header_names: list[str] | None,
                    n_cols: int, has_header: bool, kind: str) -> tuple[int | None, str | None]:
    """解析列配置。返回 (列索引, 识别说明)；auto 返回 (None, None)。"""
    if isinstance(cfg_col, int) and not isinstance(cfg_col, bool):
        if cfg_col < 0 or cfg_col >= n_cols:
            raise ValueError(f"{kind}列索引 {cfg_col} 越界（共 {n_cols} 列）")
        return cfg_col, f"显式索引 {cfg_col}"
    if isinstance(cfg_col, str) and cfg_col != "auto":
        if not has_header or not header_names:
            raise ValueError(f"{kind}列指定了表头名 {cfg_col!r}，但文件无表头，无法按名称定位")
        for i, name in enumerate(header_names):
            if str(name).strip() == cfg_col:
                return i, f"表头名 {cfg_col!r}"
        raise ValueError(f"未找到 {kind}列表头 {cfg_col!r}（实际表头: {header_names}）")
    return None, None


def _auto_wavelength(header_names: list[str] | None, n_cols: int, has_header: bool) -> tuple[int, str]:
    if has_header and header_names:
        i = _match_column(header_names, _WAVELENGTH_KEYWORDS)
        if i is not None:
            return i, f"表头 {header_names[i]!r}（第{i}列）"
    return 0, "第0列（默认波长列）"


def _auto_reflectance(header_names: list[str] | None, n_cols: int,
                      has_header: bool, wl_idx: int) -> tuple[int, str]:
    if has_header and header_names:
        i = _match_column(header_names, _REFLECTANCE_KEYWORDS, exclude=wl_idx)
        if i is not None:
            return i, f"表头 {header_names[i]!r}（第{i}列）"
    for i in range(n_cols):
        if i != wl_idx:
            return i, f"第{i}列（默认反射率列）"
    return (1 if 1 != wl_idx else 0), "第1列"


def read_spectrum_txt(path: Path, input_cfg: InputConfig) -> tuple[Spectrum, list[str]]:
    """读取单个 TXT 光谱文件。

    Returns:
        (Spectrum, warnings) —— warnings 为可读的提示信息列表

    Raises:
        ValueError / FileNotFoundError: 读取失败、列数异常、缺失值（按 on_missing 配置）
    """
    path = Path(path)
    text = read_text(path, input_cfg.encoding)
    sep = sniff_separator(text, input_cfg.separator)

    lines = text.splitlines()
    data_lines = [ln for ln in lines if ln.strip() != ""]
    if not data_lines:
        raise ValueError(f"文件为空: {path.name}")

    if input_cfg.header == "auto":
        has_header = _sniff_header(data_lines, sep)
    else:
        has_header = input_cfg.header == "true"

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

    wl_idx, wl_note = _resolve_column(input_cfg.wavelength_col, header_names, n_cols, has_header, "波长")
    rf_idx, rf_note = _resolve_column(input_cfg.reflectance_col, header_names, n_cols, has_header, "反射率")

    if wl_idx is None:
        wl_idx, wl_note = _auto_wavelength(header_names, n_cols, has_header)
    if rf_idx is None:
        rf_idx, rf_note = _auto_reflectance(header_names, n_cols, has_header, wl_idx)

    warnings: list[str] = []
    if (input_cfg.wavelength_col == "auto" or input_cfg.reflectance_col == "auto") and (wl_note or rf_note):
        warnings.append(f"{path.name}: 自动识别列 -> 波长列={wl_note}，反射率列={rf_note}")

    wls: list[float] = []
    rfs: list[float] = []
    for ln_no, line in enumerate(data_lines[start:], start=start + 1):
        tokens = _split_line(line, sep)
        if not tokens:
            continue
        if len(tokens) != n_cols:
            msg = f"{path.name}: 第{ln_no}行列数异常（期望 {n_cols} 列，实际 {len(tokens)} 列）"
            if input_cfg.on_column_error == "error":
                raise ValueError(msg)
            warnings.append(msg)
            continue
        w = _to_float(tokens[wl_idx])
        r = _to_float(tokens[rf_idx])
        if w is None or r is None:
            msg = f"{path.name}: 第{ln_no}行存在缺失值/非数值"
            if input_cfg.on_missing == "error":
                raise ValueError(msg)
            if input_cfg.on_missing == "warn":
                warnings.append(msg)
            continue
        wls.append(w)
        rfs.append(r)

    if not wls:
        raise ValueError(f"文件无有效数据行: {path.name}")

    wl_arr = np.asarray(wls, dtype=float)
    rf_arr = np.asarray(rfs, dtype=float)

    # 按波长升序排列，保证绘图与平滑沿波长维度有序
    order = np.argsort(wl_arr, kind="stable")
    if not np.array_equal(order, np.arange(order.size)):
        warnings.append(f"{path.name}: 波长未按升序排列，已自动排序")
    wl_arr = wl_arr[order]
    rf_arr = rf_arr[order]

    return Spectrum(wavelengths=wl_arr, reflectance=rf_arr, source_file=path), warnings