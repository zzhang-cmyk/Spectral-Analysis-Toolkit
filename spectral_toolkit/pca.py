"""PCA 主成分分析核心计算模块。

读取已完成 SG 平滑并人工筛选后的全部有效单次扫描光谱，按
「总文件夹 → 类别文件夹 → 样本文件夹 → 平滑 TXT」组织，把每一条 TXT
作为一条独立观测，构建 N×P 数据矩阵，做均值中心化后用 Scikit-learn PCA
计算主成分、得分、载荷与方差贡献率。

核心能力：
- 识别一级类别文件夹与二级样本文件夹（层级可配置，不递归更深层）
- 复用代表性光谱模块的 TXT 读取逻辑（平滑结果列优先、波长升序）
- 全部光谱波长坐标一致性检查（数量 / 顺序 / 数值容差）
- 按用户选择的波段范围切片（不影响原始文件）
- 均值中心化（按波长变量，非按光谱）
- PCA 计算（内部计算全部有效主成分，保留完整方差贡献率数据）

本模块不进行 SG 平滑、异常光谱识别、人工筛选和代表性光谱计算，
也不进行 SNV / MSC / 导数等额外预处理。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA

from .config import PcaInputConfig
from .representative import read_rep_spectrum

log = logging.getLogger("spectral_toolkit.pca")


@dataclass
class PcaObservation:
    """PCA 模块读取的单条光谱观测（一条 TXT = 一行观测）。"""
    wavelengths: np.ndarray
    reflectance: np.ndarray
    category: str          # 一级类别文件夹名称
    sample_id: str         # 二级样本文件夹名称
    file_name: str         # 原始 TXT 文件名
    source_file: Path      # 原始文件绝对路径

    @property
    def sample_key(self) -> str:
        """唯一样本标识，避免不同类别存在同名样本时混淆。"""
        return f"{self.category}/{self.sample_id}"


@dataclass
class PcaResult:
    """PCA 计算结果。"""
    wavelengths: np.ndarray                # 分析波段内的波长坐标（P 个）
    X: np.ndarray                          # N×P 原始输入矩阵（分析波段）
    X_mean: np.ndarray                     # 各波长变量均值（P 个）
    X_centered: np.ndarray                 # N×P 均值中心化矩阵
    scores: np.ndarray                     # N×K 得分矩阵
    loadings: np.ndarray                   # K×P 载荷矩阵（components_ 特征向量系数）
    eigenvalues: np.ndarray                # K 个特征值
    explained_variance_ratio: np.ndarray   # K 个方差贡献率
    cumulative_variance_ratio: np.ndarray  # K 个累计方差贡献率
    n_components_total: int                # 实际计算的全部有效主成分数
    n_components_keep: int                 # 用户选择保留/展示的主成分数
    categories: list[str]                  # 每条观测所属类别
    sample_ids: list[str]                  # 每条观测所属样本
    file_names: list[str]                  # 每条观测原始文件名
    sample_keys: list[str]                 # 每条观测唯一样本标识 "类别/样本"


def discover_categories(
    data_dir: Path, file_glob: str = "*.txt",
) -> dict[str, dict[str, list[Path]]]:
    """遍历总输入文件夹，识别类别文件夹与样本文件夹。

    只读取两级：一级文件夹名 = 类别，二级文件夹名 = 样本；
    只读取样本文件夹内的 TXT，不递归更深层级，忽略隐藏文件与临时文件。

    Returns:
        {类别名称: {样本名称: [TXT 文件路径...]}}

    Raises:
        FileNotFoundError: 输入目录不存在
        SystemExit: 未找到任何一级类别文件夹
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"输入总文件夹不存在: {data_dir}")

    cat_dirs = sorted(
        p for p in data_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if not cat_dirs:
        raise SystemExit(f"在 {data_dir} 下未找到任何一级子文件夹（类别文件夹）")

    categories: dict[str, dict[str, list[Path]]] = {}
    for cat_dir in cat_dirs:
        sample_dirs = sorted(
            p for p in cat_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
        samples: dict[str, list[Path]] = {}
        for sd in sample_dirs:
            files = sorted(
                p for p in sd.glob(file_glob)
                if p.is_file() and not p.name.startswith(".") and not p.name.startswith("~$")
            )
            samples[sd.name] = files
        categories[cat_dir.name] = samples
    return categories


def read_observations(
    categories: dict[str, dict[str, list[Path]]], cfg: PcaInputConfig,
) -> tuple[list[PcaObservation], dict[str, str]]:
    """读取全部类别的全部有效 TXT，返回观测列表与无效文件清单。

    Args:
        categories: discover_categories 的返回值
        cfg: PCA 输入配置

    Returns:
        (观测列表, {文件路径: 错误原因})；无效文件不静默跳过，统一记录。
    """
    observations: list[PcaObservation] = []
    invalid: dict[str, str] = {}
    for cat, samples in categories.items():
        for sample, files in samples.items():
            for f in files:
                try:
                    # 复用代表性光谱模块的读取逻辑（平滑列优先、波长升序）
                    spec, warns = read_rep_spectrum(f, cfg)  # type: ignore[arg-type]
                except ValueError as e:
                    invalid[str(f)] = str(e)
                    continue
                for w in warns:
                    log.info("%s", w)
                observations.append(PcaObservation(
                    wavelengths=spec.wavelengths,
                    reflectance=spec.reflectance,
                    category=cat,
                    sample_id=sample,
                    file_name=f.name,
                    source_file=f,
                ))
    return observations, invalid


def check_global_wavelengths(
    observations: list[PcaObservation], tolerance: float,
) -> list[str]:
    """检查全部输入光谱的波长坐标一致性。

    检查：波长数量、顺序、对应数值是否一致（按容差比较）。
    任何一条不一致都返回问题描述，PCA 计算前必须全部一致。

    Returns:
        问题描述列表；为空表示全部一致。
    """
    if not observations:
        return ["没有任何有效光谱文件"]
    if len(observations) == 1:
        return []

    ref = observations[0]
    ref_name = f"{ref.category}/{ref.sample_id}/{ref.file_name}"
    msgs: list[str] = []
    for obs in observations[1:]:
        wl = obs.wavelengths
        name = f"{obs.category}/{obs.sample_id}/{obs.file_name}"
        if wl.size != ref.wavelengths.size:
            msgs.append(
                f"{name}: 波长数量不一致（{wl.size} 个，参考 {ref_name} 为 {ref.wavelengths.size} 个）")
            continue
        if not np.all(np.diff(wl) > 0) or not np.all(np.diff(ref.wavelengths) > 0):
            msgs.append(f"{name}: 波长顺序与参考 {ref_name} 不一致（存在重复或倒序）")
            continue
        diff = np.abs(wl - ref.wavelengths)
        if diff.size and float(diff.max()) > tolerance:
            idx = int(np.argmax(diff))
            msgs.append(
                f"{name}: 第{idx}个波长点数值不一致（{wl[idx]:.6f} vs 参考 {ref.wavelengths[idx]:.6f}，"
                f"差值 {diff.max():.6g}，容差 {tolerance:g}）")
    return msgs


def _band_mask(wavelengths: np.ndarray, wl_min: float | None, wl_max: float | None) -> np.ndarray:
    """根据分析波段范围生成布尔掩码（仅影响本次 PCA 输入，不修改原始数据）。"""
    mask = np.ones(wavelengths.size, dtype=bool)
    if wl_min is not None:
        mask &= wavelengths >= wl_min
    if wl_max is not None:
        mask &= wavelengths <= wl_max
    return mask


def build_matrix(
    observations: list[PcaObservation], wl_min: float | None, wl_max: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    """构建 PCA 数据矩阵 X（N×P）。

    每条光谱一行，每个波长一列。波长坐标取参考（第一条观测）坐标，
    按用户选择的波段范围切片。要求已通过全局波长一致性检查。

    Returns:
        (X, wavelengths)

    Raises:
        ValueError: 波段范围内没有波长点
    """
    ref_wl = observations[0].wavelengths
    mask = _band_mask(ref_wl, wl_min, wl_max)
    wavelengths = ref_wl[mask]
    if wavelengths.size == 0:
        raise ValueError(
            f"所选波段范围 {wl_min}–{wl_max} nm 内没有波长点，"
            f"数据实际范围 {ref_wl.min():.2f}–{ref_wl.max():.2f} nm")
    X = np.vstack([obs.reflectance[mask] for obs in observations])
    return X, wavelengths


def mean_center(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """均值中心化：按每个波长变量减去该波长在全部观测中的平均值。"""
    X_mean = X.mean(axis=0)
    return X - X_mean, X_mean


def compute_pca(X: np.ndarray, n_components_keep: int) -> PcaResult:
    """对数据矩阵执行 PCA 计算（内部计算全部有效主成分）。

    Args:
        X: N×P 原始输入矩阵
        n_components_keep: 用户选择保留/展示的主成分数量；<=0 表示全部有效主成分

    Returns:
        PcaResult（其中 scores/loadings 等为全部有效主成分，展示数量单独记录）

    Raises:
        ValueError: 观测数量不足或数据矩阵非法
    """
    N, P = X.shape
    max_comp = min(N - 1, P)
    if max_comp < 1:
        raise ValueError(
            f"有效主成分数量不足：观测数 {N}、波长变量数 {P}，至少需要 N≥2 且 P≥1")

    if n_components_keep <= 0 or n_components_keep > max_comp:
        keep = max_comp
    else:
        keep = n_components_keep

    X_centered, X_mean = mean_center(X)

    pca = PCA(n_components=max_comp)
    scores = pca.fit_transform(X_centered)
    loadings = pca.components_
    eigenvalues = pca.explained_variance_
    evr = pca.explained_variance_ratio_
    cumulative = np.cumsum(evr)

    return PcaResult(
        wavelengths=np.array([]),   # 由 pipeline 填充
        X=X,
        X_mean=X_mean,
        X_centered=X_centered,
        scores=scores,
        loadings=loadings,
        eigenvalues=eigenvalues,
        explained_variance_ratio=evr,
        cumulative_variance_ratio=cumulative,
        n_components_total=max_comp,
        n_components_keep=keep,
        categories=[],
        sample_ids=[],
        file_names=[],
        sample_keys=[],
    )


def attach_metadata(
    result: PcaResult, observations: list[PcaObservation], wavelengths: np.ndarray,
) -> None:
    """把观测元数据（类别/样本/文件名）与波长坐标附加到结果对象。

    这些信息只作为元数据保存，不参与 PCA 数值计算。
    """
    result.wavelengths = wavelengths
    result.categories = [o.category for o in observations]
    result.sample_ids = [o.sample_id for o in observations]
    result.file_names = [o.file_name for o in observations]
    result.sample_keys = [o.sample_key for o in observations]


def legend_label_mapping(
    observations: list[PcaObservation],
) -> dict[str, str]:
    """生成「唯一样本标识 -> 图例名称」映射。

    样本名称全局唯一时直接用样本名；不同类别存在同名样本时，
    使用「类别名称-样本名称」组合避免混淆。
    """
    from collections import defaultdict
    sample_categories: dict[str, set[str]] = defaultdict(set)
    for o in observations:
        sample_categories[o.sample_id].add(o.category)

    mapping: dict[str, str] = {}
    for o in observations:
        key = o.sample_key
        if len(sample_categories[o.sample_id]) > 1:
            mapping[key] = f"{o.category}-{o.sample_id}"
        else:
            mapping[key] = o.sample_id
    return mapping