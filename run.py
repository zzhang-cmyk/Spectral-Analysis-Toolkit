"""Spectral_Analysis_Toolkit 启动入口。

用法示例：
    python run.py
    python run.py --config config/sg_config.yaml
    python run.py --window_length 11 --polyorder 3
    python run.py --wavelength_min 400 --wavelength_max 1000   # 实际处理范围
    python run.py --x_min 400 --x_max 1000                     # 绘图显示范围
    python run.py --data_dir ./data/raw --out_dir ./outputs
    python run.py --file_list 1-1.txt 1-2.txt                  # 仅处理指定文件
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spectral_toolkit import pipeline
from spectral_toolkit.config import load_config


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="光谱数据 SG 平滑预处理工具箱")
    p.add_argument("--config", default=None, help="配置文件路径，默认 config/sg_config.yaml")
    p.add_argument("--data_dir", default=None, help="输入 TXT 目录")
    p.add_argument("--file_list", nargs="+", default=None, help="仅处理指定文件（可多个）")
    # SG 参数
    p.add_argument("--window_length", type=int, default=None, help="SG 窗口长度（奇数）")
    p.add_argument("--polyorder", type=int, default=None, help="多项式阶数")
    p.add_argument("--deriv", type=int, default=None, help="导数阶数")
    p.add_argument("--mode", default=None, help="边界处理方式 interp/nearest/mirror/constant/wrap")
    # 实际处理范围（独立于绘图范围）
    p.add_argument("--wavelength_min", type=float, default=None, help="处理范围起始波长（null=完整光谱）")
    p.add_argument("--wavelength_max", type=float, default=None, help="处理范围结束波长")
    p.add_argument("--resample", default=None, help="重采样 auto/always/never")
    # 绘图参数
    p.add_argument("--x_min", type=float, default=None, help="绘图横轴下限（不影响平滑）")
    p.add_argument("--x_max", type=float, default=None, help="绘图横轴上限（不影响平滑）")
    p.add_argument("--y_min", type=float, default=None, help="绘图纵轴下限")
    p.add_argument("--y_max", type=float, default=None, help="绘图纵轴上限")
    p.add_argument("--dpi", type=int, default=None, dest="figure_dpi", help="图片分辨率")
    p.add_argument("--title", default=None, help="图表标题")
    p.add_argument("--xlabel", default=None, help="横轴名称")
    p.add_argument("--ylabel", default=None, help="纵轴名称")
    p.add_argument("--line_width", type=float, default=None, help="曲线线宽")
    p.add_argument("--legend_loc", default=None, help="图例位置，如 upper left")
    p.add_argument("--grid", action="store_true", default=None, help="显示网格线")
    p.add_argument("--out_dir", default=None, help="输出根目录")
    return p.parse_args(argv)


def _apply_overrides(cfg, args: argparse.Namespace) -> None:
    if args.data_dir:
        cfg.input.data_dir = Path(args.data_dir)
    if args.file_list:
        cfg.input.file_list = list(args.file_list)
    for attr in ("window_length", "polyorder", "deriv", "mode"):
        v = getattr(args, attr)
        if v is not None:
            setattr(cfg.sg, attr, v)
    for attr in ("wavelength_min", "wavelength_max", "resample"):
        v = getattr(args, attr)
        if v is not None:
            setattr(cfg.processing, attr, v)
    for attr in ("x_min", "x_max", "y_min", "y_max", "figure_dpi",
                 "title", "xlabel", "ylabel", "line_width", "legend_loc"):
        v = getattr(args, attr)
        if v is not None:
            setattr(cfg.plot, attr, v)
    if args.grid is not None:
        cfg.plot.grid = args.grid
    if args.out_dir:
        cfg.output.out_dir = Path(args.out_dir)


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = _parse_args(argv)
    config_path = (Path(args.config) if args.config
                   else Path(__file__).resolve().parent / "config" / "sg_config.yaml")
    cfg = load_config(config_path)
    _apply_overrides(cfg, args)

    summary = pipeline.run(cfg)

    print("\n=== 处理摘要 ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())