import logging
from types import NoneType

__all__ = ("config", "log_set_level", "log_get_level")

from typing import NoReturn


def fatal(msg, *args, **kwargs) -> NoReturn:
    """
    Don't use this function, use critical() instead.
    """
    exitcode = kwargs.pop("exitcode", 1)
    logging.critical(msg, *args, **kwargs)
    exit(exitcode)


logging.fatal = fatal


def config(**kwargs):
    (kwargs.setdefault("level", logging.INFO),)
    (kwargs.setdefault("format", "%(asctime)s %(message)s (%(levelname)s)"),)
    logging.basicConfig(**kwargs)


__levelIndex = [
    logging.FATAL,
    logging.ERROR,
    logging.WARNING,
    logging.INFO,
    logging.DEBUG,
]


__default_level = logging.WARNING
__current_level = __default_level


def log_set_level(level: int | NoneType = None):
    """
    Set the log level for the application.

    :param level: The desired log level as an index.
                  If not specified, the level is reset to the default.
    :type level: int | NoneType
    :return: The loggging level that was set.
    :rtype: int
    """
    if level is None:
        level = __default_level
    else:
        if level < 0:
            level = 0
        elif level >= len(__levelIndex):
            level = len(__levelIndex) - 1
        level = __levelIndex[level]
    logging.getLogger().setLevel(level)
    return level


def log_get_level(level: int | NoneType = None):
    if level is None:
        level = __current_level
    return __levelIndex.index(level)
