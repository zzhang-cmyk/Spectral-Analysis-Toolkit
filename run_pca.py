"""PCA 主成分分析模块启动入口。

用法示例：
    python run_pca.py
    python run_pca.py --config config/pca_config.yaml
    python run_pca.py --data_dir E:/data/.../PCA_Input --out_dir ./outputs/pca
    python run_pca.py --wavelength_min 400 --wavelength_max 1000   # 分析波段范围
    python run_pca.py --n_components 3                             # 主成分数量
    python run_pca.py --score_pairs 1,2 1,3                        # 得分图主成分组合
    python run_pca.py --scatter_size 30 --scatter_alpha 0.85 --dpi 300
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spectral_toolkit import pca_pipeline
from spectral_toolkit.config import load_pca_config


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PCA 主成分分析模块（单次扫描光谱 PCA）")
    p.add_argument("--config", default=None,
                   help="配置文件路径，默认 config/pca_config.yaml")
    p.add_argument("--data_dir", default=None, help="输入总文件夹（类别→样本→TXT）")
    p.add_argument("--out_dir", default=None, help="输出根目录（自动创建时间戳子目录）")
    p.add_argument("--tolerance", type=float, default=None,
                   help="全部光谱波长坐标一致性容差（nm）")
    # 分析参数
    p.add_argument("--wavelength_min", type=float, default=None, help="分析波段下限")
    p.add_argument("--wavelength_max", type=float, default=None, help="分析波段上限")
    p.add_argument("--n_components", default=None,
                   help="主成分数量（正整数，或 all 表示全部有效主成分）")
    # 绘图参数
    p.add_argument("--score_pairs", nargs="+", default=None,
                   help="得分图主成分组合，如 '1,2 1,3 2,3'")
    p.add_argument("--score_plot_mode", choices=["sample", "species", "both"],
                   default=None, help="得分图输出模式：sample / species / both")
    p.add_argument("--scatter_size", type=float, default=None, help="得分图散点大小")
    p.add_argument("--scatter_alpha", type=float, default=None, help="得分图散点透明度")
    p.add_argument("--dpi", type=int, default=None, dest="figure_dpi", help="图片分辨率")
    p.add_argument("--loading_x_min", type=float, default=None, help="载荷图横轴显示下限")
    p.add_argument("--loading_x_max", type=float, default=None, help="载荷图横轴显示上限")
    p.add_argument("--grid", action="store_true", default=None, help="显示网格线")
    return p.parse_args(argv)


def _apply_overrides(cfg, args: argparse.Namespace) -> None:
    if args.data_dir:
        cfg.input.data_dir = Path(args.data_dir)
    if args.out_dir:
        cfg.output.out_dir = Path(args.out_dir)
    if args.tolerance is not None:
        cfg.input.wavelength_tolerance = args.tolerance
    if args.wavelength_min is not None:
        cfg.analysis.wavelength_min = args.wavelength_min
    if args.wavelength_max is not None:
        cfg.analysis.wavelength_max = args.wavelength_max
    if args.n_components is not None:
        from spectral_toolkit.config import _opt_n_components
        cfg.analysis.n_components = _opt_n_components(args.n_components)
    if args.score_pairs is not None:
        from spectral_toolkit.config import _parse_score_pairs
        cfg.plot.score_pairs = _parse_score_pairs(args.score_pairs)
    if args.score_plot_mode is not None:
        cfg.plot.score_plot_mode = args.score_plot_mode
    for attr in ("scatter_size", "scatter_alpha", "figure_dpi",
                 "loading_x_min", "loading_x_max"):
        v = getattr(args, attr)
        if v is not None:
            setattr(cfg.plot, attr, v)
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
                   else Path(__file__).resolve().parent / "config" / "pca_config.yaml")
    cfg = load_pca_config(config_path)
    _apply_overrides(cfg, args)

    summary = pca_pipeline.run(cfg)

    print("\n=== PCA 主成分分析摘要 ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())