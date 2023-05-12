from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from equilibrium.rules.Cache import Cache
    from equilibrium.rules.Params import Params
    from equilibrium.rules.Rule import Rule
    from equilibrium.rules.RulesEngine import RulesEngine


class Executor(ABC):
    """
    Executor for rules.
    """

    @abstractmethod
    def execute(self, rule: Rule, params: Params, engine: RulesEngine) -> Any:
        """
        Execute the specified rule with the specified params.
        """
        ...

    @staticmethod
    def simple(cache: Cache) -> "Executor":
        """
        Return a simple executor.
        """

        return SimpleExecutor(cache)

    @staticmethod
    def threaded(cache: Cache) -> "Executor":
        """
        Return a threaded executor.
        """

        return ThreadedExecutor(cache)


class SimpleExecutor(Executor):
    """
    A simple executor that executes rules in the current thread.
    """

    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    def execute(self, rule: Rule, params: Params, engine: RulesEngine) -> Any:
        try:
            return self._cache.get(rule, params)
        except KeyError:
            with engine.as_current():
                result = rule.execute(params)
            assert isinstance(
                result, rule.output_type
            ), "Rule output (type: %r) does not match Rule output type: %r" % (
                type(result),
                rule.output_type,
            )
            self._cache.set(rule, params, result)
            return result


class ThreadedExecutor(Executor):
    """
    A threaded executor that executes rules in a separate thread.
    """

    def __init__(self, cache: Cache) -> None:
        self._cache = cache
        self._lock = Lock()
        self._pending: dict[int, Future[Any]] = {}
        self._executor = ThreadPoolExecutor()

    def _on_result(self, rule: Rule, params: Params, key: int) -> None:
        with self._lock:
            future = self._pending.pop(key)
            assert future.done(), "Future is not done"
            result = future.result()
            assert isinstance(
                result, rule.output_type
            ), "Rule output (type: %r) does not match Rule output type: %r" % (
                type(result),
                rule.output_type,
            )
            self._cache.set(rule, params, result)

    def execute(self, rule: Rule, params: Params, engine: RulesEngine) -> Any:
        try:
            return self._cache.get(rule, params)
        except KeyError:
            key = hash((rule.id, params))
            with self._lock:
                try:
                    future = self._pending[key]
                except KeyError:
                    future = self._executor.submit(rule.execute, params)
                    self._pending[key] = future
                    future.add_done_callback(lambda _: self._on_result(rule, params, key))
            return future.result()
