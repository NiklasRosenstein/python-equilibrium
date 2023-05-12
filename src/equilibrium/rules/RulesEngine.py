from __future__ import annotations

from contextlib import contextmanager
from typing import Any, ClassVar, Iterable, Iterator, TypeVar

from equilibrium.rules.Cache import Cache
from equilibrium.rules.Executor import Executor
from equilibrium.rules.HashSupport import HashSupport
from equilibrium.rules.Params import Params
from equilibrium.rules.Rule import Rule
from equilibrium.rules.RulesGraph import RulesGraph
from equilibrium.rules.Signature import Signature

T = TypeVar("T")


class RulesEngine:
    """
    A simple rules engine.
    """

    def __init__(
        self,
        rules: Iterable[Rule] | RulesGraph,
        subjects: Params.InitType | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.graph = RulesGraph(rules)
        self.hashsupport = HashSupport()
        self.subjects = Params(subjects or (), self.hashsupport)
        self.executor = executor or Executor.simple(Cache.memory())

    _current_engine_stack: ClassVar[list[RulesEngine]] = []

    @contextmanager
    def as_current(self) -> Iterator[None]:
        """
        Set the engine as the current engine for the duration of the context. Calls to #current() will return it
        as long as the context manager is active.
        """

        try:
            RulesEngine._current_engine_stack.append(self)
            yield
        finally:
            assert RulesEngine._current_engine_stack.pop() is self

    @staticmethod
    def current() -> "RulesEngine":
        if RulesEngine._current_engine_stack:
            return RulesEngine._current_engine_stack[-1]
        raise RuntimeError("No current RulesEngine")

    def get(self, output_type: type[T], params: Params) -> T:
        """
        Evaluate the rules to derive the specified *output_type* from the given parameters.
        """

        if not params and output_type in self.subjects:
            return self.subjects.get(output_type)

        sig = Signature(set(params.types()) | set(self.subjects.types()), output_type)
        rules = self.graph.find_path(sig)
        assert len(rules) > 0, "Empty path?"

        output: Any = None
        for rule in rules:
            inputs = self.subjects.filter(rule.input_types) | params.filter(rule.input_types)
            output = self.executor.execute(rule, inputs, self)
            params = params | Params({rule.output_type: output}, self.hashsupport)

        assert isinstance(output, output_type), f"Expected {output_type}, got {type(output)}"
        return output


def get(output_type: type[T], *inputs: object) -> T:
    """
    Delegate to the engine to retrieve the specified output type given the input parameters. If the first argument
    is a dictionary, it will be used as the input parameters and no arguments can follow.
    """

    engine = RulesEngine.current()

    if inputs and isinstance(inputs[0], dict):
        assert len(inputs) == 1, "No arguments allowed after dictionary"
        params = Params(inputs[0], engine.hashsupport)
    else:
        params = Params(inputs, engine.hashsupport)

    return engine.get(output_type, params)
