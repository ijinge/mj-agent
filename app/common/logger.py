"""统一日志配置。

- 控制台 + 可选文件输出
- 结构化字段：task_id、event_id、connection_id
- 单例 logger，按需重置
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

_LOGGERS: dict[str, logging.Logger] = {}
_DEFAULT_FMT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"


def configure_root(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """配置根 logger，确保只执行一次。"""
    root = logging.getLogger()
    if getattr(root, "_mj_configured", False):
        return
    root.setLevel(level.upper())
    fmt = logging.Formatter(_DEFAULT_FMT)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        rfh = RotatingFileHandler(log_file, maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8")
        rfh.setFormatter(fmt)
        root.addHandler(rfh)

    root._mj_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    """获取一个命名 logger，自动初始化根 logger。"""
    if name in _LOGGERS:
        return _LOGGERS[name]
    level = os.getenv("MJ_LOG_LEVEL", "INFO")
    log_file = os.getenv("MJ_LOG_FILE")
    configure_root(level=level, log_file=log_file)
    logger = logging.getLogger(name)
    _LOGGERS[name] = logger
    return logger
