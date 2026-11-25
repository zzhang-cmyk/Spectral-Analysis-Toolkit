"""代表性光谱提取模块测试。

覆盖：
1. 识别一级子文件夹（忽略隐藏/非 TXT）
2. 读取单列光谱（Wavelength / Intensity）
3. 多数据列时优先选择 Smoothed 平滑结果列
4. 多数据列且无法判断时抛错（不擅自选择）
5. 同一样本内波长一致性检查（一致 / 数量不一致 / 数值不一致）
6. 逐波长算术平均
7. 跨样本波长一致性检查
8. 完整流程：输出仅含 01_代表性光谱数据、02_光谱曲线图 两个文件夹

运行：
    cd Spectral_Analysis_Toolkit
    python tests/test_representative.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spectral_toolkit.config import RepresentativeInputConfig, load_representative_config
from spectral_toolkit.representative import (
    check_cross_sample_wavelengths,
    check_sample_wavelengths,
    discover_samples,
    mean_spectrum,
    read_rep_spectrum,
)
from spectral_toolkit import representative_pipeline

WL = [400.0, 401.0, 402.0, 403.0, 404.0]


def check(cond: bool, name: str) -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    assert cond, name


def write_txt(path: Path, header: str, rows: list[tuple[float, float]]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n")
        for w, r in rows:
            f.write(f"{w}\t{r}\n")


def _cfg(data_dir: Path) -> RepresentativeInputConfig:
    return RepresentativeInputConfig(data_dir=data_dir, wavelength_tolerance=1e-6)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="rep_test_"))
    try:
        # ---------- 样本文件夹识别 ----------
        (tmp / "样本A").mkdir()
        (tmp / "样本B").mkdir()
        (tmp / ".hidden").mkdir()          # 隐藏文件夹应被忽略
        (tmp / "样本A" / "a-1.txt").write_text("Wavelength\tIntensity\n400\t0.1\n", encoding="utf-8")
        (tmp / "样本A" / "a-2.txt").write_text("Wavelength\tIntensity\n400\t0.3\n", encoding="utf-8")
        (tmp / "样本A" / "说明.md").write_text("not a txt", encoding="utf-8")  # 非 TXT 应被忽略
        (tmp / "样本B").mkdir(exist_ok=True)  # 空文件夹
        samples = discover_samples(tmp, "*.txt")
        check(set(samples.keys()) == {"样本A", "样本B"}, "正确识别一级子文件夹并忽略隐藏文件夹")
        check(len(samples["样本A"]) == 2, "忽略非 TXT 文件")

        # ---------- 单列读取 ----------
        spec, warns = read_rep_spectrum(tmp / "样本A" / "a-1.txt", _cfg(tmp))
        check(spec.wavelengths.tolist() == [400.0], "单列：读取波长列")
        check(spec.reflectance.tolist() == [0.1], "单列：读取反射率列")

        # ---------- 多列优先选择平滑列 ----------
        multi = tmp / "multi.txt"
        multi.write_text(
            "Wavelength\tIntensity\tIntensity_smoothed\n"
            "400\t0.10\t0.50\n401\t0.20\t0.60\n", encoding="utf-8")
        spec, _ = read_rep_spectrum(multi, _cfg(tmp))
        check(np.allclose(spec.reflectance, [0.50, 0.60]), "多列：优先选择 Smoothed 平滑结果列")

        # ---------- 多列无法判断 -> 抛错 ----------
        ambiguous = tmp / "ambiguous.txt"
        ambiguous.write_text(
            "Wavelength\tIntensity\tReflectance\n400\t0.10\t0.50\n", encoding="utf-8")
        try:
            read_rep_spectrum(ambiguous, _cfg(tmp))
            check(False, "多列无法判断时应抛错")
        except ValueError:
            check(True, "多列无法判断时抛错提示（不擅自选择）")

        # ---------- 同一样本波长一致性 ----------
        rows = [(w, float(i) / 100) for i, w in enumerate(WL)]
        (tmp / "cons").mkdir()
        write_txt(tmp / "cons" / "1.txt", "Wavelength\tIntensity", rows)
        write_txt(tmp / "cons" / "2.txt", "Wavelength\tIntensity", rows)
        specs = [read_rep_spectrum(tmp / "cons" / "1.txt", _cfg(tmp))[0],
                 read_rep_spectrum(tmp / "cons" / "2.txt", _cfg(tmp))[0]]
        check(check_sample_wavelengths(specs, 1e-6) == [], "同一样本波长一致 -> 无错误")

        # 数值不一致（第 3 个波长点偏移）
        bad_rows = list(rows)
        bad_rows[2] = (402.5, bad_rows[2][1])
        write_txt(tmp / "cons" / "3.txt", "Wavelength\tIntensity", bad_rows)
        specs_bad = specs + [read_rep_spectrum(tmp / "cons" / "3.txt", _cfg(tmp))[0]]
        msgs = check_sample_wavelengths(specs_bad, 1e-6)
        check(len(msgs) == 1 and "3.txt" in msgs[0], "同一样本波长数值不一致 -> 提示具体文件与差异")

        # 数量不一致
        write_txt(tmp / "cons" / "4.txt", "Wavelength\tIntensity", rows[:-1])
        specs_short = specs + [read_rep_spectrum(tmp / "cons" / "4.txt", _cfg(tmp))[0]]
        msgs = check_sample_wavelengths(specs_short, 1e-6)
        check(any("数量不一致" in m for m in msgs), "同一样本波长数量不一致 -> 提示")

        # ---------- 逐波长算术平均 ----------
        wl, mean = mean_spectrum(specs)
        check(wl.tolist() == WL, "平均：保留原始波长坐标")
        check(np.allclose(mean, specs[0].reflectance), "平均：两条相同光谱均值为原值")

        # ---------- 跨样本波长一致性 ----------
        good = {"A": (np.array(WL), np.array(WL)), "B": (np.array(WL), np.array(WL))}
        check(check_cross_sample_wavelengths(good, 1e-6) == [], "跨样本波长一致 -> 无错误")
        bad = {"A": (np.array(WL), np.array(WL)), "B": (np.array([400.0, 401.0, 402.0, 403.0, 405.0]), np.array(WL))}
        check(len(check_cross_sample_wavelengths(bad, 1e-6)) == 1, "跨样本波长不一致 -> 提示")

        # ---------- 完整流程（输出仅两个结果文件夹） ----------
        pipe_data = tmp / "pipe_in"
        (pipe_data / "煤矸石").mkdir(parents=True)
        (pipe_data / "磷矿").mkdir(parents=True)
        for i in range(3):
            write_txt(pipe_data / "煤矸石" / f"{i}.txt", "Wavelength\tIntensity",
                      [(w, 0.1 + 0.01 * i) for w in WL])
            write_txt(pipe_data / "磷矿" / f"{i}.txt", "Wavelength\tIntensity",
                      [(w, 0.5 + 0.01 * i) for w in WL])
        (pipe_data / "空样本").mkdir()  # 空文件夹应被跳过
        cfg = load_representative_config(ROOT / "config" / "representative_config.yaml")
        cfg.input.data_dir = pipe_data
        cfg.output.out_dir = tmp / "pipe_out"
        summary = representative_pipeline.run(cfg)
        check(summary["n_samples_computed"] == 2, "流程：成功计算 2 个样本")
        check("空样本" in summary["skipped"], "流程：空文件夹给出提示并跳过")
        data_dir = Path(summary["data_dir"])
        plot_dir = Path(summary["plot_dir"])
        check((data_dir / "煤矸石_代表性光谱.txt").exists()
              and (data_dir / "磷矿_代表性光谱.txt").exists(), "流程：输出每个样本代表性光谱 TXT")
        check((plot_dir / "煤矸石_代表性光谱.png").exists()
              and (plot_dir / "磷矿_代表性光谱.png").exists()
              and (plot_dir / "全部样本代表性光谱对比.png").exists(), "流程：输出单样本图与对比图")
        top_level = {p.name for p in data_dir.parent.iterdir()}
        check(top_level == {"01_代表性光谱数据", "02_光谱曲线图"}, "流程：仅生成 01 和 02 两个结果文件夹")

        print("\n所有代表性光谱模块测试通过。")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())