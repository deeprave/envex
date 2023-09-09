# -*- coding: utf-8 -*-
import fnmatch
from typing import Iterator

__all__ = (
    "StringCacheType",
    "DictStringCache",
    "new_string_cache",
)


class StringCacheType:
    def __init__(self, capacity: int):
        self.capacity = capacity

    def pop(self, key: str | None, default: str = None) -> str | None:
        raise NotImplementedError("_pop must be implemented")

    def push(self, key: str, value: str) -> None:
        raise NotImplementedError("_push must be implemented")

    @property
    def size(self) -> int:
        raise NotImplementedError("size must be implemented")

    def clear(self):
        raise NotImplementedError("clear must be implemented")

    def get(self, key: str, default: str | None = None, error: bool = False) -> str | None:
        value = self.pop(key, default)
        if value is not None:
            self.push(key, value)
        elif error:
            raise KeyError(key)
        return value

    def put(self, key: str, value: str) -> str | None:
        if key not in self and self.size == self.capacity:  # Cache is at its capacity,
            self.pop(None)  # remove the first key (least recently used)
        old_value = self.pop(key)
        self.push(key, value)  # Add new or update existing key
        return old_value

    def match(self, pattern: str) -> Iterator[str]:
        keys = []
        for key in self._cache:
            if fnmatch.fnmatch(key, pattern):
                keys.append(key)
        for key in keys:
            yield key

    def __contains__(self, key: str):
        return self.get(key) is not None

    def __getitem__(self, key: str) -> str | None:
        return self.get(key, error=True)

    def __setitem__(self, key: str, value: str):
        self.put(key, value)

    def __delitem__(self, key: str):
        if self.pop(key, default=None) is None:
            raise KeyError(key)


class DictStringCache(StringCacheType):
    def __init__(self, capacity: int):
        super().__init__(capacity)
        self._cache = {}

    def pop(self, key: str | None, default: str = None) -> str | None:
        if self.capacity == 0 or len(self._cache) == 0:
            return default
        if key is None:
            first = next(iter(self._cache))
            return self._cache.pop(first)
        return self._cache.pop(key, default)

    def push(self, key: str, value: str) -> None:
        if self.capacity > 0:
            if (
                key not in self and self.size == self.capacity
            ):  # Cache is at its capacity,remove the first key (least recently used)
                self.pop(None)
            self._cache[key] = value

    @property
    def size(self) -> int:
        return len(self._cache)

    def clear(self):
        self._cache.clear()


def new_string_cache(capacity: int) -> StringCacheType:
    return DictStringCache(capacity)
