from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from equilibrium.rules.Params import Params
    from equilibrium.rules.Rule import Rule


class Cache(ABC):
    """
    Base class for all cache implementations.
    """

    @abstractmethod
    def has(self, rule: Rule, params: Params) -> bool:
        """
        Return True if the specified rule and params have been evaluated.
        """

    @abstractmethod
    def get(self, rule: Rule, params: Params) -> Any:
        """
        Return the result of evaluating the specified rule and params.

        Raise a #KeyError if the specified rule and params have not been evaluated.
        """

    @abstractmethod
    def set(self, rule: Rule, params: Params, value: Any) -> None:
        """
        Set the result of evaluating the specified rule and params.
        """

    @staticmethod
    def none() -> "Cache":
        """
        Return a new cache that does not cache anything.
        """

        return NoneCache()

    @staticmethod
    def memory() -> "Cache":
        """
        Return a new memory cache.
        """

        return MemoryCache()


class NoneCache(Cache):
    """
    Cache implementation that does not cache anything.
    """

    def has(self, rule: Rule, params: Params) -> bool:
        return False

    def get(self, rule: Rule, params: Params) -> Any:
        raise KeyError()

    def set(self, rule: Rule, params: Params, value: Any) -> None:
        pass


class MemoryCache(Cache):
    """
    In-memory cache implementation.
    """

    def __init__(self) -> None:
        self._cache: dict[int, Any] = {}

    def has(self, rule: Rule, params: Params) -> bool:
        return hash((rule.id, params)) in self._cache

    def get(self, rule: Rule, params: Params) -> Any:
        return self._cache[hash((rule.id, params))]

    def set(self, rule: Rule, params: Params, value: Any) -> None:
        self._cache[hash((rule.id, params))] = value
