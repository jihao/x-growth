"""市场级数据与状态：指数日线、市场广度缓存、市场环境（regime）判定。

子模块按需导入（避免 python -m quant.market.xxx 触发 RuntimeWarning）。
"""
__all__ = ["build_breadth", "index_update", "regime"]


def __getattr__(name):
    if name in __all__:
        import importlib
        return importlib.import_module(f"quant.market.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
