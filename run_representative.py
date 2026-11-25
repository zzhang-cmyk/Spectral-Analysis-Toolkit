"""代表性光谱提取模块启动入口。

用法示例：
    python run_representative.py
    python run_representative.py --config config/representative_config.yaml
    python run_representative.py --data_dir E:/data/.../样本文件夹 --out_dir ./outputs/representative
    python run_representative.py --x_min 400 --x_max 1000        # 绘图横轴显示范围
    python run_representative.py --y_min 0 --y_max 1             # 绘图纵轴范围
    python run_representative.py --dpi 300 --figsize 8,5
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spectral_toolkit import representative_pipeline
from spectral_toolkit.config import load_representative_config


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="代表性光谱提取模块（逐波长算术平均）")
    p.add_argument("--config", default=None,
                   help="配置文件路径，默认 config/representative_config.yaml")
    p.add_argument("--data_dir", default=None, help="输入总文件夹（一级子文件夹即样本）")
    p.add_argument("--out_dir", default=None, help="输出根目录（自动创建带时间戳子目录）")
    p.add_argument("--tolerance", type=float, default=None,
                   help="同一样本内波长坐标一致性容差（nm）")
    # 绘图参数
    p.add_argument("--x_min", type=float, default=None, help="绘图横轴下限（不影响输出数据）")
    p.add_argument("--x_max", type=float, default=None, help="绘图横轴上限")
    p.add_argument("--y_min", type=float, default=None, help="绘图纵轴下限")
    p.add_argument("--y_max", type=float, default=None, help="绘图纵轴上限")
    p.add_argument("--dpi", type=int, default=None, dest="figure_dpi", help="图片分辨率")
    p.add_argument("--figsize", default=None, help="图片尺寸（宽,高），如 8,5")
    p.add_argument("--title", default=None, help="全部样本对比图标题")
    p.add_argument("--xlabel", default=None, help="横轴名称")
    p.add_argument("--ylabel", default=None, help="纵轴名称")
    p.add_argument("--line_width", type=float, default=None, help="曲线线宽")
    p.add_argument("--legend_loc", default=None, help="图例位置，如 best / upper left")
    p.add_argument("--grid", action="store_true", default=None, help="显示网格线")
    return p.parse_args(argv)


def _apply_overrides(cfg, args: argparse.Namespace) -> None:
    if args.data_dir:
        cfg.input.data_dir = Path(args.data_dir)
    if args.out_dir:
        cfg.output.out_dir = Path(args.out_dir)
    if args.tolerance is not None:
        cfg.input.wavelength_tolerance = args.tolerance
    for attr in ("x_min", "x_max", "y_min", "y_max", "figure_dpi",
                 "title", "xlabel", "ylabel", "line_width", "legend_loc"):
        v = getattr(args, attr)
        if v is not None:
            setattr(cfg.plot, attr, v)
    if args.figsize is not None:
        from spectral_toolkit.config import _parse_figsize
        cfg.plot.figsize = _parse_figsize(args.figsize)
    if args.grid is not None:
        cfg.plot.grid = args.grid


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = _parse_args(argv)
    config_path = (Path(args.config) if args.config
                   else Path(__file__).resolve().parent / "config" / "representative_config.yaml")
    cfg = load_representative_config(config_path)
    _apply_overrides(cfg, args)

    summary = representative_pipeline.run(cfg)

    print("\n=== 代表性光谱提取摘要 ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())