import pytest

from envex.lib.cache import DictStringCache


class TestDictStringCache:
    def test_get_existing_key_returns_value(self):
        cache = DictStringCache(3)
        cache.push("key1", "value1")
        cache.push("key2", "value2")
        cache.push("key3", "value3")

        result = cache.get("key2")

        assert result == "value2"

    def test_get_non_existing_key_with_default_returns_default(self):
        cache = DictStringCache(3)
        cache.push("key1", "value1")
        cache.push("key2", "value2")
        cache.push("key3", "value3")

        result = cache.get("key4", default="default_value")

        assert result == "default_value"

    def test_get_non_existing_key_without_default_returns_none(self):
        cache = DictStringCache(3)
        cache.push("key1", "value1")
        cache.push("key2", "value2")
        cache.push("key3", "value3")

        result = cache.get("key4")

        assert result is None

    def test_put_new_key_value_pair_returns_none(self):
        cache = DictStringCache(3)

        result = cache.put("key1", "value1")

        assert result is None

    def test_put_existing_key_value_pair_returns_old_value(self):
        # Create an instance of StringCacheType
        cache = DictStringCache(3)

        # Add a key-value pair to the cache
        cache.push("key1", "value1")

        # Put an existing key-value pair in the cache
        result = cache.put("key1", "new_value")

        # Assert that the returned value is the old value
        assert result == "value1"

    def test_put_key_value_pair_when_cache_is_full(self):
        # Create an instance of DictStringCache
        cache = DictStringCache(3)

        # Add key-value pairs to the cache
        cache.push("key1", "value1")
        cache.push("key2", "value2")
        cache.push("key3", "value3")

        # Put a new key-value pair in the cache when it is full
        result = cache.put("key4", "value4")

        # Assert that the returned value is None
        assert result is None

        # Assert that the least recently used key-value pair is removed
        assert "key1" not in cache._cache

    def test_clear_cache_with_one_item(self):
        cache = DictStringCache(10)
        cache.push("key", "value")
        cache.clear()
        assert cache.size == 0
        assert "key" not in cache._cache

    def test_clear_cache_with_multiple_items(self):
        cache = DictStringCache(10)
        cache.push("key1", "value1")
        cache.push("key2", "value2")
        cache.push("key3", "value3")
        cache.clear()
        assert cache.size == 0
        assert "key1" not in cache
        assert "key2" not in cache
        assert "key3" not in cache

    def test_clear_cache_with_nonexistent_key(self):
        cache = DictStringCache(10)
        cache.push("key", "value")
        cache.clear()
        assert cache.size == 0
        assert "key" not in cache

    def test_get_item(self):
        cache = DictStringCache(10)
        key = "key"
        value = "value"

        cache[key] = value
        assert cache[key] == value

        with pytest.raises(KeyError):
            _ = cache["nonexistent_key"]

        del cache[key]

        with pytest.raises(KeyError):
            _ = cache[key]
