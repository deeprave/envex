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

    def test_match_no_keys_match_pattern(self, mocker):
        cache = DictStringCache(10)
        mocker.patch.object(cache, "get", return_value=None)
        result = list(cache.match("abc*"))
        assert len(result) == 0

    def test_match_one_key_matches_pattern(self, mocker):
        cache = DictStringCache(10)
        cache.push("abc", "123")
        result = list(cache.match("abc"))
        assert len(result) == 1
        assert result[0] == "abc"

        result = list(cache.match("abc*"))
        assert len(result) == 1
        assert result[0] == "abc"

    def test_match_multiple_keys_match_pattern_and_order_added(self, mocker):
        cache = DictStringCache(10)

        cache.push("abc", "123")
        cache.push("abcd", "456")
        cache.push("abcde", "789")

        result = list(cache.match("abc*"))

        assert len(result) == 3
        assert result[0] == "abc"
        assert result[1] == "abcd"
        assert result[2] == "abcde"

    def test_match_order_of_most_recently_accessed_keys(self, mocker):
        cache = DictStringCache(10)

        cache.push("abc", "123")
        cache.push("abcd", "456")
        cache.push("abcde", "789")

        _ = cache.get("abcd")
        _ = cache.get("abc")
        _ = cache.get("abcde")

        result = list(cache.match("abc*"))

        # Assert that the result contains the values of
        # all matching keys in the order of most to least recently accessed
        assert len(result) == 3
        assert result[0] == "abcd"
        assert result[1] == "abc"
        assert result[2] == "abcde"

    def test_match_order_of_most_recently_accessed_keys_with_evictions(self, mocker):
        cache = DictStringCache(3)

        cache.push("abc", "123")
        cache.push("abcd", "456")
        cache.push("abcde", "789")

        _ = cache.get("abcd")
        _ = cache.get("abc")
        _ = cache.get("abcde")

        cache.push("abcdef", "000")

        result = list(cache.match("abc*"))

        # Assert that the result contains the values of all matching keys in the order of
        # most recently accessed to least recently accessed
        assert len(result) == 3
        assert result[0] == "abc"
        assert result[1] == "abcde"
        assert result[2] == "abcdef"

    def test_match_with_path_pattern(self, mocker):
        cache = DictStringCache(10)

        cache.push("test/abc", "123")
        cache.push("test/abcd", "456")
        cache.push("test2/abcde", "789")

        result = list(cache.match("test/abc*"))
        assert len(result) == 2
        assert result[0] == "test/abc"
        assert result[1] == "test/abcd"

        result = list(cache.match("test/*"))
        assert len(result) == 2
        assert result[0] == "test/abc"
        assert result[1] == "test/abcd"

        result = list(cache.match("test*"))
        assert len(result) == 3
        assert result[0] == "test/abc"
        assert result[1] == "test/abcd"
        assert result[2] == "test2/abcde"
