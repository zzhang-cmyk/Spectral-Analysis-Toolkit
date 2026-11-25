"""样本 / 扫描编号识别与分组模块。

通过可配置正则从文件名提取 sample 与 scan 编号。
例如：1-1.txt ~ 1-10.txt 归为样本 1（扫描 1~10）。
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import GroupingConfig
from .data_io import Spectrum


def parse_filename(path: Path, cfg: GroupingConfig) -> tuple[str, str]:
    """从文件名解析 (样本编号, 扫描编号)。

    未启用或未匹配时，回退为：样本编号 = 文件主名，扫描编号 = "1"。
    """
    name = Path(path).stem
    if cfg.enabled and cfg.pattern:
        m = re.search(cfg.pattern, name)
        if m:
            gd = m.groupdict()
            sample = gd.get("sample") or gd.get("sample_id")
            scan = gd.get("scan") or gd.get("scan_id")
            if sample is not None and scan is not None:
                return str(sample), str(scan)
    return name, "1"


def group_by_sample(spectra: list[Spectrum]) -> dict[str, list[Spectrum]]:
    """按样本编号分组。

    Returns:
        {sample_id: [Spectrum, ...]}
    """
    groups: dict[str, list[Spectrum]] = {}
    for s in spectra:
        key = s.sample_id if s.sample_id is not None else s.source_file.stem
        groups.setdefault(key, []).append(s)
    return groups