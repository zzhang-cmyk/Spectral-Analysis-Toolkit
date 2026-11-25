"""配置数据模型与 YAML 读取。

将 config/sg_config.yaml 解析为强类型 dataclass，供各模块使用。
所有参数集中于此，避免硬编码；运行 run.py 时可通过命令行参数覆盖。

关键设计：
- processing（实际处理范围）与 plot（绘图显示范围）完全分离。
- 调整绘图横轴范围不会改变 SG 处理的数据范围。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class InputConfig:
    """数据输入配置。"""
    data_dir: Path = Path("./data/raw")
    file_glob: str = "*.txt"
    file_list: list[str] = field(default_factory=list)  # 指定文件列表，空 = 处理整个文件夹
    separator: str = "auto"          # auto / comma / tab / space / semicolon
    header: str = "auto"             # auto / true / false
    encoding: str = "auto"           # auto / utf-8 / gb18030 / gbk / latin-1 ...
    wavelength_col: Any = "auto"     # auto / 0 起始列序号 / 表头名
    reflectance_col: Any = "auto"
    on_missing: str = "warn"         # warn(丢行并提示) / error / drop
    on_column_error: str = "error"   # error / warn(跳过异常行)


@dataclass
class ProcessingConfig:
    """实际处理范围与波长重采样配置。

    wavelength_min / wavelength_max 控制哪些波长参与 SG 平滑；
    None 表示处理完整光谱。与绘图显示范围相互独立。
    """
    wavelength_min: float | None = None   # 处理范围下限，None = 完整光谱
    wavelength_max: float | None = None   # 处理范围上限
    resample: str = "auto"                # auto(不均匀时重采样) / always / never
    resample_method: str = "linear"       # linear / nearest / cubic
    resample_step: float | None = None    # 均匀网格步长，None = 取原始间隔中位数


@dataclass
class SGParams:
    """Savitzky-Golay 平滑参数。"""
    window_length: int = 9
    polyorder: int = 2
    deriv: int = 0
    mode: str = "interp"


@dataclass
class GroupingConfig:
    """样本 / 扫描编号识别配置。"""
    enabled: bool = True
    # 必须包含命名分组 sample 与 scan（或 sample_id / scan_id）
    pattern: str = r"(?P<sample>\d+)-(?P<scan>\d+)"


@dataclass
class PlotConfig:
    """绘图配置。x_min/x_max 仅控制显示范围，不影响 SG 处理范围。

    默认绘图范围 400–1000 nm（木材案例）。
    """
    x_min: float | None = 400.0
    x_max: float | None = 1000.0
    y_min: float | None = None
    y_max: float | None = None
    figure_dpi: int = 300
    title: str = "木材反射率光谱"
    xlabel: str = "Wavelength (nm)"
    ylabel: str = "Reflectance"
    line_width: float = 1.5
    legend_loc: str = "upper left"
    grid: bool = False
    font_size: int = 11
    legend_labels: dict = field(default_factory=dict)  # {文件名主名: 自定义图例名称}


@dataclass
class OutputConfig:
    """输出配置。自动创建独立输出目录，绝不覆盖原始文件。"""
    out_dir: Path = Path("./outputs")
    export_smoothed_txt: bool = True
    export_excel: bool = True
    export_png: bool = True
    export_record: bool = True
    plots: dict = field(default_factory=lambda: {
        "single_overlay": True,
        "multi_curves": True,
        "sample_scans": True,
        "sample_comparison": True,
        "before_after": True,
        "mean_std": False,
    })


@dataclass
class ToolkitConfig:
    """工具箱总配置。"""
    input: InputConfig
    processing: ProcessingConfig
    sg: SGParams
    grouping: GroupingConfig
    plot: PlotConfig
    output: OutputConfig
    config_path: Path = field(default_factory=Path)


@dataclass
class RepresentativeInputConfig:
    """代表性光谱提取模块的输入配置。

    数据组织：一个总文件夹 + 多个样本子文件夹；
    一级子文件夹名即样本名，子文件夹内所有 TXT 为同一样本的多次扫描。
    """
    data_dir: Path = Path("./data")
    file_glob: str = "*.txt"
    separator: str = "auto"          # auto / comma / tab / space / semicolon
    header: str = "auto"             # auto / true / false
    encoding: str = "auto"           # auto / utf-8 / gb18030 / gbk / latin-1 ...
    on_missing: str = "warn"         # warn / error / drop
    on_column_error: str = "error"   # error / warn
    wavelength_tolerance: float = 1e-6  # 波长坐标一致性比较容差（nm）


@dataclass
class RepresentativePlotConfig:
    """代表性光谱绘图配置。x_min/x_max 仅控制显示范围，不影响输出的完整光谱数据。"""
    x_min: float | None = 400.0
    x_max: float | None = 1000.0
    y_min: float | None = None
    y_max: float | None = None
    figure_dpi: int = 300
    figsize: tuple[float, float] = (8.0, 5.0)
    title: str = "全部样本代表性光谱对比"
    xlabel: str = "Wavelength (nm)"
    ylabel: str = "Reflectance"
    line_width: float = 1.5
    legend_loc: str = "best"
    grid: bool = False
    font_size: int = 11


@dataclass
class RepresentativeOutputConfig:
    """代表性光谱输出配置。自动创建独立时间戳目录，绝不覆盖之前结果。"""
    out_dir: Path = Path("./outputs/representative")


@dataclass
class RepresentativeConfig:
    """代表性光谱提取模块总配置。"""
    input: RepresentativeInputConfig
    plot: RepresentativePlotConfig
    output: RepresentativeOutputConfig
    config_path: Path = field(default_factory=Path)


def _resolve(base_dir: Path, p: Any) -> Path:
    """相对路径以配置文件所在目录为基准解析。"""
    p = Path(p).expanduser()
    return p if p.is_absolute() else (base_dir / p).resolve()


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _opt_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _opt_n_components(v: Any) -> int:
    """解析主成分数量配置：正整数 = 保留数量；"all" / 非正数 = 全部有效主成分（用 -1 表示）。"""
    if isinstance(v, str) and v.strip().lower() in ("all", "max", "全部"):
        return -1
    n = _opt_int(v, 2)
    if n <= 0:
        return -1
    return n


def load_config(path: str | Path) -> ToolkitConfig:
    """读取并解析 sg_config.yaml。

    Args:
        path: 配置文件路径

    Returns:
        ToolkitConfig

    Raises:
        FileNotFoundError: 配置文件不存在
    """
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    base_dir = path.parent

    inp = raw.get("input") or {}
    file_list = [str(x) for x in (inp.get("file_list") or [])]
    input_cfg = InputConfig(
        data_dir=_resolve(base_dir, inp.get("data_dir", "./data/raw")),
        file_glob=inp.get("file_glob", "*.txt"),
        file_list=file_list,
        separator=str(inp.get("separator", "auto")).lower(),
        header=str(inp.get("header", "auto")).lower(),
        encoding=inp.get("encoding", "auto"),
        wavelength_col=inp.get("wavelength_col", "auto"),
        reflectance_col=inp.get("reflectance_col", "auto"),
        on_missing=str(inp.get("on_missing", "warn")).lower(),
        on_column_error=str(inp.get("on_column_error", "error")).lower(),
    )

    proc = raw.get("processing") or {}
    processing = ProcessingConfig(
        wavelength_min=_opt_float(proc.get("wavelength_min")),
        wavelength_max=_opt_float(proc.get("wavelength_max")),
        resample=str(proc.get("resample", "auto")).lower(),
        resample_method=str(proc.get("resample_method", "linear")).lower(),
        resample_step=_opt_float(proc.get("resample_step")),
    )

    sg_raw = raw.get("sg") or {}
    sg = SGParams(
        window_length=int(sg_raw.get("window_length", 9)),
        polyorder=int(sg_raw.get("polyorder", 2)),
        deriv=int(sg_raw.get("deriv", 0)),
        mode=str(sg_raw.get("mode", "interp")),
    )

    grp = raw.get("grouping") or {}
    grouping = GroupingConfig(
        enabled=bool(grp.get("enabled", True)),
        pattern=grp.get("pattern") or r"(?P<sample>\d+)-(?P<scan>\d+)",
    )

    plt = raw.get("plot") or {}
    legend_labels = plt.get("legend_labels") or {}
    plot = PlotConfig(
        x_min=_opt_float(plt.get("x_min", 400.0)),
        x_max=_opt_float(plt.get("x_max", 1000.0)),
        y_min=_opt_float(plt.get("y_min")),
        y_max=_opt_float(plt.get("y_max")),
        figure_dpi=_opt_int(plt.get("figure_dpi"), 300),
        title=plt.get("title", "木材反射率光谱"),
        xlabel=plt.get("xlabel", "Wavelength (nm)"),
        ylabel=plt.get("ylabel", "Reflectance"),
        line_width=float(plt.get("line_width", 1.5)),
        legend_loc=str(plt.get("legend_loc", "upper left")),
        grid=bool(plt.get("grid", False)),
        font_size=_opt_int(plt.get("font_size"), 11),
        legend_labels={str(k): str(v) for k, v in legend_labels.items()},
    )

    out = raw.get("output") or {}
    default_plots = {
        "single_overlay": True,
        "multi_curves": True,
        "sample_scans": True,
        "sample_comparison": True,
        "before_after": True,
        "mean_std": False,
    }
    plots_raw = out.get("plots") or {}
    plots = {k: bool(plots_raw.get(k, v)) for k, v in default_plots.items()}
    output = OutputConfig(
        out_dir=_resolve(base_dir, out.get("out_dir", "./outputs")),
        export_smoothed_txt=bool(out.get("export_smoothed_txt", True)),
        export_excel=bool(out.get("export_excel", True)),
        export_png=bool(out.get("export_png", True)),
        export_record=bool(out.get("export_record", True)),
        plots=plots,
    )

    return ToolkitConfig(
        input=input_cfg,
        processing=processing,
        sg=sg,
        grouping=grouping,
        plot=plot,
        output=output,
        config_path=path,
    )


def _parse_figsize(v: Any) -> tuple[float, float]:
    """解析图片尺寸，支持 [8, 5] / (8, 5) / "8,5" 等形式。"""
    if v is None:
        return (8.0, 5.0)
    if isinstance(v, (list, tuple)):
        vals = [float(x) for x in v]
    elif isinstance(v, str):
        vals = [float(x) for x in v.replace(",", " ").split()]
    else:
        raise ValueError(f"figsize 配置非法: {v!r}")
    if len(vals) != 2:
        raise ValueError(f"figsize 必须包含两个数值（宽, 高），实际 {v!r}")
    if vals[0] <= 0 or vals[1] <= 0:
        raise ValueError(f"figsize 宽高必须为正数，实际 {v!r}")
    return (vals[0], vals[1])


def _load_representative_input(inp: dict, base_dir: Path) -> RepresentativeInputConfig:
    """解析代表性光谱 / PCA 模块共用的输入读取配置。"""
    return RepresentativeInputConfig(
        data_dir=_resolve(base_dir, inp.get("data_dir", "./data")),
        file_glob=str(inp.get("file_glob", "*.txt")),
        separator=str(inp.get("separator", "auto")).lower(),
        header=str(inp.get("header", "auto")).lower(),
        encoding=inp.get("encoding", "auto"),
        on_missing=str(inp.get("on_missing", "warn")).lower(),
        on_column_error=str(inp.get("on_column_error", "error")).lower(),
        wavelength_tolerance=float(inp.get("wavelength_tolerance", 1e-6)),
    )


def load_representative_config(path: str | Path) -> RepresentativeConfig:
    """读取并解析代表性光谱提取模块的配置文件。

    Args:
        path: 配置文件路径

    Returns:
        RepresentativeConfig
    """
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    base_dir = path.parent

    input_cfg = _load_representative_input(raw.get("input") or {}, base_dir)

    plt = raw.get("plot") or {}
    plot = RepresentativePlotConfig(
        x_min=_opt_float(plt.get("x_min", 400.0)),
        x_max=_opt_float(plt.get("x_max", 1000.0)),
        y_min=_opt_float(plt.get("y_min")),
        y_max=_opt_float(plt.get("y_max")),
        figure_dpi=_opt_int(plt.get("figure_dpi"), 300),
        figsize=_parse_figsize(plt.get("figsize", [8, 5])),
        title=str(plt.get("title", "全部样本代表性光谱对比")),
        xlabel=str(plt.get("xlabel", "Wavelength (nm)")),
        ylabel=str(plt.get("ylabel", "Reflectance")),
        line_width=float(plt.get("line_width", 1.5)),
        legend_loc=str(plt.get("legend_loc", "best")),
        grid=bool(plt.get("grid", False)),
        font_size=_opt_int(plt.get("font_size"), 11),
    )

    out = raw.get("output") or {}
    output = RepresentativeOutputConfig(
        out_dir=_resolve(base_dir, out.get("out_dir", "./outputs/representative")),
    )

    return RepresentativeConfig(
        input=input_cfg,
        plot=plot,
        output=output,
        config_path=path,
    )


@dataclass
class PcaInputConfig:
    """PCA 模块输入配置。

    数据组织：总文件夹 → 类别文件夹 → 样本文件夹 → 平滑 TXT。
    一级文件夹名即类别，二级文件夹名即样本，二级文件夹内所有 TXT
    为该样本经 SG 平滑和人工筛选后的单次扫描光谱。
    """
    data_dir: Path = Path("./data/PCA_Input")
    file_glob: str = "*.txt"
    separator: str = "auto"          # auto / comma / tab / space / semicolon
    header: str = "auto"             # auto / true / false
    encoding: str = "auto"           # auto / utf-8 / gb18030 / gbk / latin-1 ...
    on_missing: str = "warn"         # warn / error / drop
    on_column_error: str = "error"   # error / warn
    wavelength_tolerance: float = 1e-6  # 波长坐标一致性比较容差（nm）


@dataclass
class PcaAnalysisConfig:
    """PCA 分析配置。"""
    wavelength_min: float | None = 400.0   # 分析波段下限，None = 完整光谱
    wavelength_max: float | None = 1000.0  # 分析波段上限
    n_components: int = 2                  # 用户选择保留/展示的主成分数量
    centering: str = "mean"                # 中心化方式，第一版仅支持 mean


@dataclass
class PcaPlotConfig:
    """PCA 绘图配置。"""
    figure_dpi: int = 300
    figsize: tuple[float, float] = (8.0, 6.0)
    font_size: int = 11
    grid: bool = False
    scatter_size: float = 30.0            # 得分图散点大小（面积）
    scatter_alpha: float = 0.85           # 得分图散点透明度
    score_pairs: list[tuple[int, int]] = field(default_factory=lambda: [(1, 2)])
    score_plot_mode: str = "sample"       # 得分图输出模式：sample / species / both
    legend_loc: str = "best"              # 得分图图例位置；样本多时自动放右侧
    legend_max_ncol: int = 2              # 图例列数上限
    loading_x_min: float | None = 400.0   # 载荷图横轴显示下限
    loading_x_max: float | None = 1000.0  # 载荷图横轴显示上限
    max_variance_bars: int = 10           # 方差贡献率柱状图最多显示的主成分数量


@dataclass
class PcaOutputConfig:
    """PCA 输出配置。自动创建独立时间戳目录，绝不覆盖之前结果。"""
    out_dir: Path = Path("./outputs/pca")


@dataclass
class PcaConfig:
    """PCA 主成分分析模块总配置。"""
    input: PcaInputConfig
    analysis: PcaAnalysisConfig
    plot: PcaPlotConfig
    output: PcaOutputConfig
    config_path: Path = field(default_factory=Path)


def _parse_score_pairs(v: Any) -> list[tuple[int, int]]:
    """解析得分图主成分组合，支持 [[1,2],[1,3]] / ["1,2","1,3"] 等形式。"""
    if v is None:
        return [(1, 2)]
    if not isinstance(v, (list, tuple)):
        raise ValueError(f"score_pairs 配置非法: {v!r}")
    pairs: list[tuple[int, int]] = []
    for item in v:
        if isinstance(item, (list, tuple)):
            vals = [int(x) for x in item]
        elif isinstance(item, str):
            vals = [int(x) for x in item.replace(",", " ").split()]
        else:
            raise ValueError(f"score_pairs 元素非法: {item!r}")
        if len(vals) != 2:
            raise ValueError(f"score_pairs 每项必须包含两个主成分编号，实际 {item!r}")
        if vals[0] <= 0 or vals[1] <= 0 or vals[0] == vals[1]:
            raise ValueError(f"score_pairs 主成分编号必须为正且互不相同，实际 {item!r}")
        pairs.append((vals[0], vals[1]))
    if not pairs:
        raise ValueError("score_pairs 不能为空")
    return pairs


def load_pca_config(path: str | Path) -> PcaConfig:
    """读取并解析 PCA 主成分分析模块的配置文件。

    Args:
        path: 配置文件路径

    Returns:
        PcaConfig
    """
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    base_dir = path.parent

    inp = raw.get("input") or {}
    input_cfg = PcaInputConfig(
        data_dir=_resolve(base_dir, inp.get("data_dir", "./data/PCA_Input")),
        file_glob=str(inp.get("file_glob", "*.txt")),
        separator=str(inp.get("separator", "auto")).lower(),
        header=str(inp.get("header", "auto")).lower(),
        encoding=inp.get("encoding", "auto"),
        on_missing=str(inp.get("on_missing", "warn")).lower(),
        on_column_error=str(inp.get("on_column_error", "error")).lower(),
        wavelength_tolerance=float(inp.get("wavelength_tolerance", 1e-6)),
    )

    ana = raw.get("analysis") or {}
    analysis = PcaAnalysisConfig(
        wavelength_min=_opt_float(ana.get("wavelength_min", 400.0)),
        wavelength_max=_opt_float(ana.get("wavelength_max", 1000.0)),
        n_components=_opt_n_components(ana.get("n_components")),
        centering=str(ana.get("centering", "mean")).lower(),
    )

    plt = raw.get("plot") or {}
    plot = PcaPlotConfig(
        figure_dpi=_opt_int(plt.get("figure_dpi"), 300),
        figsize=_parse_figsize(plt.get("figsize", [8, 6])),
        font_size=_opt_int(plt.get("font_size"), 11),
        grid=bool(plt.get("grid", False)),
        scatter_size=float(plt.get("scatter_size", 30.0)),
        scatter_alpha=float(plt.get("scatter_alpha", 0.85)),
        score_pairs=_parse_score_pairs(plt.get("score_pairs", [[1, 2]])),
        score_plot_mode=str(plt.get("score_plot_mode", "sample")).lower(),
        legend_loc=str(plt.get("legend_loc", "best")),
        legend_max_ncol=_opt_int(plt.get("legend_max_ncol"), 2),
        loading_x_min=_opt_float(plt.get("loading_x_min", 400.0)),
        loading_x_max=_opt_float(plt.get("loading_x_max", 1000.0)),
        max_variance_bars=_opt_int(plt.get("max_variance_bars"), 10),
    )

    out = raw.get("output") or {}
    output = PcaOutputConfig(
        out_dir=_resolve(base_dir, out.get("out_dir", "./outputs/pca")),
    )

    return PcaConfig(
        input=input_cfg,
        analysis=analysis,
        plot=plot,
        output=output,
        config_path=path,
    )