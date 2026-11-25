"""光谱数据预处理工具箱 Spectral_Analysis_Toolkit。

第一版能力：
- TXT 批量读取（多分隔符 / 有无表头 / 多编码 / 列识别）
- Savitzky-Golay 平滑（scipy.signal.savgol_filter）
- 光谱曲线绘制
- 结果导出（平滑 TXT / 汇总 Excel / PNG / 处理记录）

可复用、可扩展：Smoother 基类预留未来其他预处理算法接入点。
"""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]