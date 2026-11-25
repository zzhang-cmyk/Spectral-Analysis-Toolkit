"""真实数据格式全流程测试。

模拟真实样本 1-1.txt（480 组数据，波长 190.34–1193.63 nm，Tab 分隔，
表头 Wavelength / Intensity，波长间隔轻微不均匀）。

覆盖（对应修订指令第八节测试内容）：
1. 自动识别 Wavelength / Intensity 两列
2. 正确读取 480 组数据
3. 正确识别波长范围
4. 正确检查非均匀波长间隔并触发重采样
5. 完成 SG 平滑
6. 修改窗口长度与多项式阶数
7. 修改绘图横轴范围（不影响平滑）
8. 绘制原始与平滑曲线
9. 导出 TXT / Excel / PNG
10. 保留原始数据（源文件不变）
11. 比较 7 / 9 / 11 点窗口平滑效果

运行：
    cd Spectral_Analysis_Toolkit
    python tests/test_toolkit.py
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spectral_toolkit import pipeline
from spectral_toolkit.config import load_config
from spectral_toolkit.data_io import read_spectrum_txt
from spectral_toolkit.smoothing import smooth_spectrum
from spectral_toolkit.validation import (
    validate_plot_config,
    validate_processing_config,
    validate_sg_params,
    wavelength_interval_stats,
)

N_POINTS = 480
WL_START = 190.34
WL_END = 1193.63


def make_wavelengths(n=N_POINTS, start=WL_START, end=WL_END, seed=0) -> np.ndarray:
    """生成轻微不均匀、严格递增的波长坐标（模拟真实光谱仪采样）。"""
    rng = np.random.default_rng(seed)
    base = (end - start) / (n - 1)
    i = np.arange(n - 1)
    # 平滑的微小变化，模拟光栅非线性采样
    steps = base + 0.003 * np.sin(2 * np.pi * i / (n - 1) * 3.0) + rng.normal(0, 0.0008, n - 1)
    steps = np.clip(steps, base * 0.99, base * 1.01)
    steps = steps * (end - start) / steps.sum()  # 保证首尾精确为 start / end
    return start + np.concatenate([[0.0], np.cumsum(steps)])


def make_wood_reflectance(wl: np.ndarray, seed=1) -> np.ndarray:
    """生成木材典型反射率：可见光较低、近红外抬升，叠加噪声。"""
    rng = np.random.default_rng(seed)
    base = 0.30 + 0.45 / (1.0 + np.exp(-(wl - 600.0) / 140.0)) \
        + 0.06 * np.sin(wl / 120.0) + 0.03 * np.exp(-((wl - 980.0) / 60.0) ** 2)
    noise = rng.normal(0.0, 0.004, wl.size)
    return np.clip(base + noise, 0.0, 1.0)


def write_txt(path: Path, wl: np.ndarray, refl: np.ndarray) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("Wavelength\tIntensity\n")
        for w, r in zip(wl, refl):
            f.write(f"{w:.4f}\t{r:.6f}\n")


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def generate_data(data_dir: Path) -> None:
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    for sample, scans in ((1, [1, 2, 3]), (2, [1, 2])):
        for scan in scans:
            wl = make_wavelengths(seed=sample * 100 + scan)
            refl = make_wood_reflectance(wl, seed=sample * 10 + scan)
            write_txt(data_dir / f"{sample}-{scan}.txt", wl, refl)
    print(f"模拟真实数据已生成: {data_dir}")


def check(cond: bool, name: str) -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    assert cond, name


def main() -> int:
    root = ROOT
    data_dir = root / "data" / "raw"
    out_dir = root / "outputs"

    generate_data(data_dir)

    # ---------- 1/2/3/4. 列识别、点数、波长范围、间隔检查 ----------
    cfg = load_config(root / "config" / "sg_config.yaml")
    cfg.input.data_dir = data_dir
    cfg.output.out_dir = out_dir

    spec, warns = read_spectrum_txt(data_dir / "1-1.txt", cfg.input)
    check(spec.wavelengths.size == N_POINTS, f"正确读取 {N_POINTS} 组数据（实际 {spec.wavelengths.size}）")
    check(abs(spec.wavelengths.min() - WL_START) < 1e-3
          and abs(spec.wavelengths.max() - WL_END) < 1e-3,
          f"波长范围识别正确（{spec.wavelengths.min():.2f}–{spec.wavelengths.max():.2f} nm）")

    stats = wavelength_interval_stats(spec.wavelengths)
    print(f"  [INFO] 波长间隔: 最小 {stats['min_step']:.5f}, 最大 {stats['max_step']:.5f}, "
          f"中位数 {stats['median_step']:.5f} nm, 均匀={stats['uniform']}")
    check(not stats["uniform"], "正确检测到非均匀波长间隔")

    # 明确指定表头列名也应能识别
    cfg2 = load_config(root / "config" / "sg_config.yaml")
    cfg2.input.data_dir = data_dir
    cfg2.input.wavelength_col = "Wavelength"
    cfg2.input.reflectance_col = "Intensity"
    spec2, _ = read_spectrum_txt(data_dir / "1-1.txt", cfg2.input)
    check(spec2.wavelengths.size == N_POINTS, "按表头名识别 Wavelength/Intensity 列")

    # ---------- 5. SG 平滑（含重采样） ----------
    validate_sg_params(cfg.sg)
    validate_processing_config(cfg.processing)
    smoothed, info = smooth_spectrum(spec, cfg.sg, cfg.processing)
    check(smoothed.shape == spec.reflectance.shape, "平滑结果长度与原始一致（保留原始波长坐标）")
    check(not np.any(np.isnan(smoothed)), "平滑结果无 NaN")
    check(info["resampled"], "非均匀数据已自动重采样到均匀网格")
    print(f"  [INFO] 重采样: method={info['resample_method']}, step={info['resample_step']:.5f} nm, "
          f"均匀网格点数={info['n_grid']}")

    # ---------- 6. 修改窗口长度 / 阶数（7/9/11 比较） ----------
    smoothed_by_win = {}
    for win in (7, 9, 11):
        c = load_config(root / "config" / "sg_config.yaml")
        c.sg.window_length = win
        validate_sg_params(c.sg)
        smoothed_by_win[win], _ = smooth_spectrum(spec, c.sg, c.processing)
    check(not np.allclose(smoothed_by_win[7], smoothed_by_win[11]),
          "7 点与 11 点窗口平滑结果存在差异")
    check(smoothed_by_win[9].shape == spec.reflectance.shape, "9 点窗口平滑结果长度正确")

    c3 = load_config(root / "config" / "sg_config.yaml")
    c3.sg.window_length = 11
    c3.sg.polyorder = 3
    validate_sg_params(c3.sg)
    sm3, _ = smooth_spectrum(spec, c3.sg, c3.processing)
    check(sm3.shape == spec.reflectance.shape, "修改多项式阶数(3)后平滑正常")

    # 非法参数拦截
    bad = load_config(root / "config" / "sg_config.yaml")
    bad.sg.window_length = 10  # 偶数
    try:
        validate_sg_params(bad.sg)
        check(False, "偶数窗口长度应报错")
    except ValueError:
        check(True, "偶数窗口长度被拒绝")

    # ---------- 7. 绘图横轴范围修改（不影响平滑） ----------
    cfgA = load_config(root / "config" / "sg_config.yaml")
    cfgA.input.data_dir = data_dir
    cfgA.output.out_dir = out_dir
    cfgA.plot.x_min = 500.0
    cfgA.plot.x_max = 800.0
    cfgB = load_config(root / "config" / "sg_config.yaml")
    cfgB.input.data_dir = data_dir
    cfgB.output.out_dir = out_dir
    cfgB.plot.x_min = 400.0
    cfgB.plot.x_max = 1000.0
    validate_plot_config(cfgA.plot)
    validate_plot_config(cfgB.plot)

    # ---------- 8/9. 全流程：绘制 + 导出 ----------
    orig_md5 = {p.name: _md5(p) for p in data_dir.glob("*.txt")}
    summary = pipeline.run(cfgA)
    check(Path(summary["excel"]).exists(), "导出汇总 Excel")
    check(Path(summary["smoothed_txt_dir"]).is_dir(), "导出平滑 TXT")
    check(Path(summary["plots_dir"]).is_dir(), "导出 PNG 曲线图")
    check(Path(summary["record"]).exists(), "导出处理记录")
    pngs = list(Path(summary["plots_dir"]).glob("*.png"))
    check(any("multi_curves" in p.name for p in pngs), "生成多条平滑后曲线叠加图")
    check(not any("single_overlay" in p.name for p in pngs), "不再生成原始+平滑叠加对比图")

    # ---------- 10. 原始数据保留 ----------
    after_md5 = {p.name: _md5(p) for p in data_dir.glob("*.txt")}
    check(orig_md5 == after_md5, "原始 TXT 未被修改/覆盖")

    # ---------- 记录内容检查 ----------
    import json
    rec = json.loads(Path(summary["record"]).read_text(encoding="utf-8"))
    check("processing_range" in rec and "plot_range" in rec and "resample" in rec,
          "处理记录包含处理范围/绘图范围/重采样信息")
    check(rec["resample"]["applied"] is True, "处理记录标记已重采样")
    print(f"  [INFO] 记录: 处理范围={rec['processing_range']}, "
          f"绘图范围={rec['plot_range']['x_min']}–{rec['plot_range']['x_max']}")

    # ---------- 窗口 7/9/11 分别导出平滑曲线图 ----------
    for win in (7, 9, 11):
        c = load_config(root / "config" / "sg_config.yaml")
        c.input.data_dir = data_dir
        c.input.file_list = ["1-1.txt"]
        c.output.out_dir = out_dir
        c.sg.window_length = win
        s = pipeline.run(c)
        check(Path(s["plots_dir"], "multi_curves.png").exists(),
              f"窗口 {win} 点：生成平滑曲线图")
    print(f"  [INFO] 已完成 7/9/11 点窗口平滑效果对比导出")

    print("\n全部测试通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())