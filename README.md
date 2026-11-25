# Spectral_Analysis_Toolkit V1.0

可复用的光谱数据预处理工具箱，当前用于木材反射率光谱的 SG（Savitzky-Golay）平滑与可视化，后续可扩展至土壤、岩石、植被等光谱数据。

第一版能力：TXT 读取、波长间隔检查与非均匀重采样、SG 平滑、科研风格光谱绘图、结果导出。暂不包含 GUI、SNV、MSC、导数分析与机器学习。

另提供两个相互独立的扩展模块：

- 「代表性光谱提取模块」：读取已完成 SG 平滑并剔除异常的光谱文件，按样本文件夹归类，逐波长算术平均，输出每个样本的代表性光谱数据与曲线图，以及全部样本对比图（详见文末 [代表性光谱提取模块](#代表性光谱提取模块representative-spectrum-extraction)）。
- 「PCA 主成分分析模块」：直接读取经 SG 平滑和人工筛选后的全部有效单次扫描光谱进行主成分分析，绘制得分图、载荷图与方差贡献率图并导出 Excel（详见文末 [PCA 主成分分析模块](#pca-主成分分析模块principal-component-analysis)）。

## 数据格式

- 文件格式：TXT。
- 数据分隔符：Tab（也兼容空格、逗号、分号）。
- 第一行为表头：`Wavelength`、`Intensity`（也兼容 `wavelength`/`reflectance` 等常见写法）。
- 第一列为波长（单位 nm），第二列为光谱数据（Intensity 即白板校正后的反射率）。
- 原始数据完整保留，程序只读源文件，绝不覆盖、不修改源文件。

示例真实样本 `1-1.txt`：480 组数据，波长范围 190.34–1193.63 nm，波长采样间隔存在轻微不均匀。

## 项目结构

```
Spectral_Analysis_Toolkit/
├── run.py                         # SG 平滑启动入口（命令行参数可覆盖配置）
├── run_representative.py          # 代表性光谱提取模块启动入口
├── run_pca.py                     # PCA 主成分分析模块启动入口
├── requirements.txt               # 依赖
├── README.md
├── config/
│   ├── sg_config.yaml             # SG 平滑全部参数（输入/处理范围/分组/SG/绘图/输出）
│   ├── representative_config.yaml # 代表性光谱模块参数（输入/绘图/输出）
│   └── pca_config.yaml            # PCA 主成分分析模块参数（输入/分析/绘图/输出）
├── spectral_toolkit/
│   ├── __init__.py                # 包说明与版本
│   ├── config.py                  # 配置数据模型 + YAML 解析（含代表性/PCA 模块配置）
│   ├── data_io.py                 # TXT 读取（多分隔符/编码/表头/列识别）
│   ├── validation.py              # 参数校验、波长间隔检查
│   ├── grouping.py                # 样本/扫描编号识别与分组
│   ├── smoothing.py               # SG 平滑 + 非均匀重采样（Smoother 基类预留扩展）
│   ├── plotting.py                # SG 模块科研风格绘图
│   ├── pipeline.py                # SG 模块流程编排 + 导出 + 记录
│   ├── representative.py          # 代表性光谱计算 + 读取 + 波长一致性检查
│   ├── representative_plot.py     # 代表性光谱绘图（单样本图 + 对比图）
│   ├── representative_pipeline.py # 代表性光谱流程编排
│   ├── pca.py                     # PCA 核心计算（类别/样本识别、波长检查、均值中心化、PCA）
│   ├── pca_plot.py                # PCA 绘图（得分图、载荷图、方差贡献率图）
│   └── pca_pipeline.py            # PCA 流程编排 + Excel 导出
└── tests/
    ├── test_toolkit.py            # SG 模块真实格式（480 点）全流程测试
    └── test_representative.py     # 代表性光谱模块测试
```

## 安装

```bash
pip install -r requirements.txt
```

依赖：numpy、scipy、scikit-learn、pandas、matplotlib、pyyaml、openpyxl。

## 运行方式

```bash
# 使用默认配置 config/sg_config.yaml
python run.py

# 指定配置
python run.py --config config/sg_config.yaml

# 仅处理指定文件
python run.py --file_list 1-1.txt 1-2.txt

# 修改 SG 参数（窗口长度 / 阶数 / 导数 / 边界方式）
python run.py --window_length 11 --polyorder 3
python run.py --deriv 0 --mode interp

# 设置实际处理范围（控制参与 SG 平滑的波长；与绘图范围独立）
python run.py --wavelength_min 190 --wavelength_max 1194

# 设置绘图显示范围（仅影响横轴显示，不影响平滑结果）
python run.py --x_min 400 --x_max 1000

# 修改输入 / 输出目录
python run.py --data_dir ./data/raw --out_dir ./outputs
```

## 参数修改方法

所有参数集中在 [config/sg_config.yaml](config/sg_config.yaml)，也可在命令行覆盖（命令行优先级更高）。

### 数据输入（input）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| data_dir | ../data/raw | 输入 TXT 目录（相对路径以 config/ 目录为基准，../ 即项目根目录） |
| file_glob | *.txt | 文件匹配规则 |
| file_list | [] | 指定文件列表；非空时优先于整个文件夹 |
| separator | auto | auto / comma / tab / space / semicolon |
| header | auto | auto / true / false |
| encoding | auto | auto / utf-8 / gb18030 / gbk / latin-1 |
| wavelength_col / reflectance_col | auto | auto / 列序号（0 起）/ 表头名 |
| on_missing | warn | warn / error / drop（缺失值处理） |
| on_column_error | error | error / warn（列数异常处理） |

### SG 平滑参数（sg）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| window_length | 9 | 窗口长度，必须为奇数且大于 polyorder |
| polyorder | 2 | 多项式阶数 |
| deriv | 0 | 导数阶数，第一版默认 0 |
| mode | interp | 边界处理方式 interp / nearest / mirror / constant / wrap |

程序会自动校验：窗口长度为奇数、窗口长度大于多项式阶数，参数非法时直接报错。

### 实际处理范围与重采样（processing）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| wavelength_min / wavelength_max | null | 实际处理范围（参与 SG 平滑的波长），null = 完整光谱 |
| resample | auto | auto（非均匀时重采样）/ always / never |
| resample_method | linear | linear / nearest / cubic |
| resample_step | null | 均匀网格步长，null = 取原始间隔中位数 |

> 处理范围（processing）与绘图范围（plot）完全独立。默认建议对完整原始光谱平滑，再显示 400–1000 nm，避免绘图区间边界影响 SG 结果。

### 波长采样间隔处理

程序自动检查波长间隔。当间隔不均匀时：

1. 计算原始波长间隔及其中位数；
2. 在实际处理波段内建立均匀波长网格；
3. 线性插值将反射率转换到均匀网格；
4. 在均匀网格上执行 SG 平滑；
5. 将平滑结果插值回原始波长坐标；
6. 输出保留原始波长坐标。

若数据已均匀，则直接平滑，不做不必要重采样。重采样方法、步长与 SG 参数均写入处理记录。

### 绘图参数（plot）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| x_min / x_max | 400 / 1000 | 绘图横轴显示范围（仅影响显示，不改变平滑结果） |
| y_min / y_max | null | 纵轴范围（null = 自动适配） |
| figure_dpi | 300 | PNG 分辨率 |
| title | 木材反射率光谱 | 标题 |
| xlabel | Wavelength (nm) | 横轴名 |
| ylabel | Reflectance | 纵轴名 |
| line_width | 1.5 | 曲线线宽 |
| legend_loc | upper left | 图例位置（默认左上角） |
| grid | false | 网格线（默认关闭） |
| font_size | 11 | 字体大小 |
| legend_labels | {} | 自定义图例名，如 `{"1-1": "样本1-扫描1"}` |

绘图统一科研风格：白色背景、黑色坐标轴边框、多色连续曲线、无数据点标记、图例默认左上角、默认关闭网格。

支持的绘图模式：单条原始 + SG 平滑叠加、多条光谱叠加、同一样本多次扫描对比、不同样本对比、平滑前后对比、平均光谱 + 标准差阴影（预留）。

### 文件分组（grouping）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| enabled | true | 是否启用文件名规则识别 |
| pattern | `(?P<sample>\d+)-(?P<scan>\d+)` | 正则，需含命名分组 sample 与 scan |

`1-1.txt` ~ `1-10.txt` 归为样本 1（扫描 1~10），`2-1.txt` ~ `2-10.txt` 归为样本 2。规则可配置，不硬编码。

## 结果导出

每次运行自动在 `outputs/run_<时间戳>/` 下创建独立结果文件夹，绝不覆盖原始文件：

- `smoothed_txt/`：每条光谱对应的平滑 TXT（保留原始波长坐标）
- `summary.xlsx`：原始数据、平滑数据、处理参数三张表
- `plots/`：原始与平滑对比图、多条叠加图、样本扫描对比图等 PNG
- `processing_record.json`：本次处理记录

处理记录包含：原始文件名、原始波长范围、实际处理范围、绘图显示范围、SG 窗口长度、多项式阶数、重采样方法及步长、运行时间。

## 测试

```bash
python tests/test_toolkit.py
```

测试使用真实格式样本（480 组数据，波长 190.34–1193.63 nm，Tab 分隔，表头 Wavelength/Intensity，间隔轻微不均匀），覆盖：

1. 自动识别 Wavelength/Intensity 两列
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

## 扩展接口

`smoothing.Smoother` 为基类，定义 `smooth(wavelengths, values) -> values` 接口；`SavitzkyGolaySmoother` 为其中一个实现。后续新增 SNV、MSC、导数分析等预处理算法时，继承 `Smoother` 即可无缝接入现有管线，无需改动读取、绘图与导出模块。

## 代表性光谱提取模块（Representative Spectrum Extraction）

独立的代表性光谱提取模块，用于读取已完成 SG 平滑、并经人工剔除异常的光谱文件，按样本文件夹归类，对同一样本的多条光谱逐波长计算算术平均值，生成该样本的代表性光谱数据与曲线图。

模块与 SG 平滑模块相互独立，不进行 SG 平滑、SNV、MSC、导数等任何预处理，不计算标准差、CV、相关系数等统计量。

### 输入文件夹组织方式

采用「一个总文件夹 + 多个样本子文件夹」的方式。一级子文件夹名即样本名，子文件夹内所有 TXT 为同一样本的多次扫描。

```
Representative_Spectrum_Input/
├── 松木_1/
│   ├── 1-1.txt
│   ├── 1-2.txt
│   └── ...
├── 松木_2/
│   └── ...
├── 树种B/
│   └── ...
└── 树种C/
    └── ...
```

规则：

- 只读取一级子文件夹内的 TXT，不递归更深层级；
- 忽略非 TXT 与隐藏文件；
- 样本数量、每个样本的扫描次数、材料名称、波段范围均不固定；
- 样本子文件夹名直接作为样本名，用于输出文件命名与图例。

### 数据读取

支持 Tab、逗号、空格、分号分隔，自动识别常见编码，自动识别 Wavelength 列与 Intensity/Reflectance 等数值列。Intensity 按反射率（Reflectance）处理，绘图纵轴标记为 Reflectance，反射率保持原始 0–1 数值、不乘以 100。

若 TXT 含原始光谱与平滑光谱等多个数据列，优先选择表头标记为 `Smoothed` / `SG_Smoothed` / `平滑` 的平滑结果列；无法判断时提示用户检查，不擅自选择。

### 计算方法与波长一致性检查

对同一样本 N 条有效光谱，逐波长计算算术平均值：

```
R_mean(λ) = [R_1(λ) + R_2(λ) + ... + R_N(λ)] / N
```

各条光谱权重相同，不采用中位数 / 加权平均，不进行插值或重采样。计算前检查同一样本内各 TXT 的波长数量、顺序与数值（可配置容差 `wavelength_tolerance`）；不一致时给出具体文件名与差异说明，暂停该样本计算。同时检查不同样本代表性光谱波长坐标是否一致，不一致时不生成全部样本对比图。

### 运行方式

```bash
# 使用默认配置 config/representative_config.yaml
python run_representative.py

# 指定输入总文件夹 / 输出目录
python run_representative.py --data_dir "E:/data/.../样本文件夹" --out_dir ./outputs/representative

# 修改绘图横轴显示范围（不影响输出的完整光谱数据）
python run_representative.py --x_min 400 --x_max 1000

# 修改纵轴范围、分辨率、图片尺寸
python run_representative.py --y_min 0 --y_max 1 --dpi 300 --figsize 8,5
```

### 参数配置

所有参数集中在 [config/representative_config.yaml](config/representative_config.yaml)，也可在命令行覆盖（命令行优先级更高）。

| 分组 | 参数 | 默认 | 说明 |
| --- | --- | --- | --- |
| input | data_dir | 见配置 | 输入总文件夹（一级子文件夹即样本） |
| input | file_glob | *.txt | 样本子文件夹内 TXT 匹配规则 |
| input | separator / header / encoding | auto | 分隔符 / 表头 / 编码，均支持自动识别 |
| input | on_missing / on_column_error | warn / error | 缺失值与列数异常处理 |
| input | wavelength_tolerance | 1e-6 | 同一样本内波长坐标一致性容差（nm） |
| plot | x_min / x_max | 400 / 1000 | 绘图横轴显示范围（仅影响显示） |
| plot | y_min / y_max | null | 纵轴范围（null = 自动适配） |
| plot | figure_dpi | 300 | PNG 分辨率 |
| plot | figsize | [8, 5] | 图片尺寸（宽, 高，英寸） |
| plot | title | 全部样本代表性光谱对比 | 对比图标题 |
| plot | xlabel / ylabel | Wavelength (nm) / Reflectance | 坐标轴名称 |
| plot | line_width | 1.5 | 曲线线宽 |
| plot | legend_loc | best | 图例位置（best = 自动选不遮挡曲线的位置） |
| plot | grid | false | 网格线（默认关闭） |
| plot | font_size | 11 | 字体大小 |
| output | out_dir | ../outputs/representative | 输出根目录（自动创建时间戳子目录） |

### 结果输出

每次运行自动创建独立的 `run_<时间戳>/` 目录，绝不覆盖之前结果，且只生成两个结果文件夹：

```
outputs/representative/run_<时间戳>/
├── 01_代表性光谱数据/
│   ├── 松木_1_代表性光谱.txt
│   ├── 松木_2_代表性光谱.txt
│   └── ...
└── 02_光谱曲线图/
    ├── 松木_1_代表性光谱.png
    ├── 松木_2_代表性光谱.png
    ├── ...
    └── 全部样本代表性光谱对比.png
```

- 代表性光谱 TXT 两列：`Wavelength`、`Reflectance`，保留完整波长范围与原始坐标精度，不因绘图横轴范围而截断；
- 单样本图与对比图的图例直接采用样本子文件夹名称（完整保留中文、数字与下划线）；
- 绘图统一科研风格：白色背景、黑色边框、默认无网格、连续实线、无散点标记、不同样本使用不同颜色、图例默认自动选位。

### 测试

```bash
python tests/test_representative.py
```

覆盖：样本子文件夹识别、单列 / 多列读取、平滑列优先选择、多列无法判断时抛错、同一样本波长一致性检查、逐波长算术平均、跨样本波长一致性检查、空文件夹提示，以及完整流程仅生成 01 / 02 两个结果文件夹。

## PCA 主成分分析模块（Principal Component Analysis）

独立的 PCA 主成分分析模块，直接读取经 SG 平滑和人工筛选后的**全部有效单次扫描光谱**进行主成分分析，研究不同类别、不同样本之间的光谱差异，观察同一样本内部多次扫描的光谱分布，并分析不同波长变量对主成分的贡献。

模块与 SG 平滑模块、代表性光谱模块相互独立，不进行 SG 平滑、异常光谱识别、人工筛选和代表性光谱计算，也不进行 SNV、MSC、导数等额外预处理，**不先计算每个样本的平均光谱**——每个 TXT 文件直接作为一条独立观测参与 PCA。

### 输入文件夹组织方式

采用「总文件夹 → 类别文件夹 → 样本文件夹 → 平滑 TXT」三级结构：

```
PCA_Input/
├── 松木/
│   ├── 松树1/
│   │   ├── 1-1.txt
│   │   ├── 1-2.txt
│   │   └── ...
│   ├── 松树2/
│   │   └── ...
│   └── 松树6/
│       └── ...
├── 枫树/
│   └── 枫树1/
│       └── ...
└── 樟树/
    └── 樟树1/
        └── ...
```

规则：

- 一级文件夹名 = 类别名称，二级文件夹名 = 独立样本名称；
- 只读取样本文件夹内的 TXT，不递归更深层级；
- 类别数量、每个类别的样本数量、每个样本的扫描次数、名称与波段范围均不固定，不依赖 TXT 命名规则；
- 每个 TXT 文件代表一条独立光谱观测（同一样本文件夹内的全部有效 TXT 直接参与 PCA）；
- 空文件夹、没有有效 TXT 的文件夹会给出明确提示。

### 数据读取与波长一致性检查

复用代表性光谱模块的 TXT 读取逻辑：支持 Tab / 逗号 / 空格 / 分号分隔，自动识别常见编码与 Wavelength / Intensity / Reflectance 列；若 TXT 含原始与平滑等多个数据列，优先选择表头标记为 `Smoothed` / `SG_Smoothed` / `平滑` 的平滑结果列，无法判断时提示用户检查，不擅自选择；反射率保留原始 0–1 数值、不乘以 100。

PCA 计算前检查全部输入光谱的波长坐标一致性（数量、顺序、数值，可配置容差 `wavelength_tolerance`）。若不一致，显示具体文件名与差异说明，**暂停本次 PCA 计算**，不按行号匹配、不自动插值或重采样。无效文件列入异常文件清单并提示，不静默跳过。

### 数据矩阵与预处理

- 每条光谱一行（N = 有效 TXT 总数），每个波长一列（P = 波长变量数），即 `X = N × P`；
- 类别、样本、文件名作为元数据保存，不参与 PCA 数值计算；
- 默认分析波段 400–1000 nm，可配置 `wavelength_min` / `wavelength_max`（只影响本次 PCA 输入变量，不修改原始 TXT）；
- 均值中心化：按每个波长变量减去该波长在全部观测中的平均值（不是对每条光谱分别中心化）；
- 第一版不做 StandardScaler、SNV、MSC、导数等额外预处理，代码结构为后续扩展预留接口。

### 运行方式

```bash
# 使用默认配置 config/pca_config.yaml
python run_pca.py

# 指定配置 / 输入总文件夹 / 输出目录
python run_pca.py --config config/pca_config.yaml
python run_pca.py --data_dir "E:/data/.../PCA_Input" --out_dir ./outputs/pca

# 设置分析波段范围、主成分数量
python run_pca.py --wavelength_min 400 --wavelength_max 1000
python run_pca.py --n_components 3              # 2 / 3 / 4 / all

# 设置得分图主成分组合、输出模式、散点样式、分辨率
python run_pca.py --score_pairs 1,2 1,3 2,3
python run_pca.py --score_plot_mode both     # sample / species / both
python run_pca.py --scatter_size 30 --scatter_alpha 0.85 --dpi 300
```

### 参数配置

所有参数集中在 [config/pca_config.yaml](config/pca_config.yaml)，也可在命令行覆盖（命令行优先级更高）。

| 分组 | 参数 | 默认 | 说明 |
| --- | --- | --- | --- |
| input | data_dir | 见配置 | 总输入文件夹（类别 → 样本 → TXT） |
| input | file_glob | *.txt | 样本文件夹内 TXT 匹配规则 |
| input | separator / header / encoding | auto | 分隔符 / 表头 / 编码，均支持自动识别 |
| input | on_missing / on_column_error | warn / error | 缺失值与列数异常处理 |
| input | wavelength_tolerance | 1e-6 | 全部光谱波长坐标一致性容差（nm） |
| analysis | wavelength_min / wavelength_max | 400 / 1000 | 分析波段范围（null = 完整光谱） |
| analysis | n_components | 2 | 保留/展示的主成分数量（all = 全部有效主成分） |
| analysis | centering | mean | 中心化方式，第一版仅支持均值中心化 |
| plot | figure_dpi | 300 | PNG 分辨率 |
| plot | figsize | [8, 6] | 图片尺寸（宽, 高，英寸） |
| plot | font_size | 11 | 字体大小 |
| plot | grid | false | 网格线（默认关闭） |
| plot | scatter_size / scatter_alpha | 30 / 0.85 | 得分图散点大小 / 透明度 |
| plot | score_pairs | [[1,2]] | 得分图主成分组合，如 `[[1,2],[1,3],[2,3]]` |
| plot | score_plot_mode | sample | 得分图输出模式：sample（仅样本级）/ species（仅树种级）/ both（两者都生成） |
| plot | legend_loc / legend_max_ncol | best / 2 | 图例位置 / 最大列数（best = 自动选择不遮挡散点的位置，始终在图框内） |
| plot | loading_x_min / loading_x_max | 400 / 1000 | 载荷图横轴显示范围 |
| plot | max_variance_bars | 10 | 方差贡献率图最多显示的主成分数量 |
| output | out_dir | ../outputs/pca | 输出根目录（自动创建时间戳子目录） |

### 得分图颜色分组与图例

得分图通过 `score_plot_mode` 支持三种输出模式：

- **sample（样本级）**：严格按**第二级样本文件夹**进行颜色分组——同一样本的所有散点使用相同颜色，不同样本文件夹使用不同颜色；图例名称直接采用样本子文件夹名称（若不同类别中存在同名样本，自动使用「类别名称-样本名称」作为唯一图例名称）。
- **species（树种级）**：按**第一级类别文件夹**进行颜色分组——同一树种的所有散点使用相同颜色（不同树种使用高区分度、明显不同的饱和颜色），同一树种内不同独立样本使用不同散点形状；图例每个样本一个条目，同时携带其树种颜色与散点形状。
- **both**：同时生成上述两张得分图，两张图共用同一组 PCA 得分数据，坐标、散点位置、方差贡献率完全一致，仅颜色分组与点形状不同，不重复计算 PCA。

所有得分图图名统一为「PCA 得分图（PCx-PCy）」，不区分样本级/树种级。图例统一使用白底、100% 不透明、黑色实线直角矩形边框（0.8 pt）；图例自适应选择不遮挡散点的位置（优先放下方，覆盖到数据点时自动向上/向两侧移动）并始终保持在图框内，样本数量较多时按列排列。每个点代表一条单次扫描光谱，可通过 Excel 追溯其原始 TXT 文件。

### 结果输出

每次运行自动创建独立的 `run_<时间戳>/` 目录，绝不覆盖之前结果，且只生成两个结果文件夹：

```
outputs/pca/run_<时间戳>/
├── 01_PCA分析数据/
│   └── PCA分析结果.xlsx
└── 02_PCA结果图/
    ├── PCA得分图_样本级_PC1-PC2.png   # score_plot_mode = sample / both
    ├── PCA得分图_树种级_PC1-PC2.png   # score_plot_mode = species / both
    ├── PCA载荷图_PC1-PC2.png
    ├── PCA方差贡献率.png
    └── PCA累计贡献率.png
```

`PCA分析结果.xlsx` 包含五个工作表：

1. `PCA得分数据`：Category、Sample_ID、File_Name 与 PC1、PC2、PC3… 得分（每条 TXT 一行，可追溯原始文件）；
2. `PCA载荷数据`：Wavelength 与各主成分载荷系数；
3. `方差贡献率`：主成分名称、特征值、方差贡献率、累计方差贡献率；
4. `样本扫描数量统计`：每个样本的原始 TXT 数量与实际参与 PCA 的有效光谱数量；
5. `PCA输入矩阵`：Category、Sample_ID、File_Name 与各波长反射率（完整输入数据，便于复核）。

### 结果解释说明

程序会根据实际计算结果生成基础统计（参与光谱数量、类别/样本数量、各主成分方差贡献率、前两个主成分累计贡献率等），但**不能替代专业分析**，不会自动得出以下结论：仅凭得分图认定分类成功、将技术重复扫描视为独立样本、仅凭少量样本推断整类材料的普遍特征、仅凭载荷峰值认定某波段对应特定化学成分、仅凭二维得分图判断全部高维信息均已分离。

特别地，由于每条扫描光谱在 PCA 中权重相同，扫描次数较多的样本会对总体方差结构产生更大影响；当不同样本有效扫描数量明显不均衡时会给出提示，结果解释时需考虑这一点。