from __future__ import annotations

import inspect
import sys
from collections import ChainMap
from functools import wraps
from itertools import chain
from typing import Any, Callable, Mapping, ParamSpec, TypeVar, overload
from uuid import uuid4

from typeapi import get_annotations, type_repr

from equilibrium.rules.Params import Params
from equilibrium.rules.Signature import Signature

T = TypeVar("T")
P = ParamSpec("P")


class Rule:
    """
    A rule represents a single step in the rules engine. It is a single unit of work that can be executed. It
    always has one or more inputs and produces exactly one output.
    """

    def __init__(
        self,
        func: Callable[[Params], Any],
        input_types: set[type[Any]],
        output_type: type[Any],
        id: str | None = None,
    ) -> None:
        self.id = id or str(uuid4())
        self.func = func
        self.input_types = input_types
        self.output_type = output_type

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Rules can be called just like their underlying function. This is mostly for the @rule decorator."""
        return self.func(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<Rule {self.id!r} ({', '.join(map(type_repr, self.input_types))}) -> {type_repr(self.output_type)}>"

    @property
    def signature(self) -> Signature:
        return Signature(self.input_types, self.output_type)

    def execute(self, params: Params) -> Any:
        return self.func(params)


def rule(func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator for functions to be used as rules.
    """

    annotations = get_annotations(func)
    output_type = annotations.pop("return")
    input_types = {v: k for k, v in annotations.items()}
    if len(input_types) != len(annotations):
        raise RuntimeError("Rule function must not have overlapping type annotations")
    if output_type in input_types:
        raise RuntimeError("Rule function must not have overlapping type annotations")
    if len(input_types) != func.__code__.co_argcount:
        raise RuntimeError("Rule function must have type annotations for all parameters and return value")

    @wraps(func)
    def _wrapper(params: Params) -> Any:
        return func(**{k: params.get(v) for v, k in input_types.items()})

    return Rule(_wrapper, set(input_types), output_type, func.__module__ + "." + func.__qualname__)


@overload
def collect_rules(*, globals: Mapping[str, Any]) -> list[Rule]:
    ...


@overload
def collect_rules(*, module: str) -> list[Rule]:
    ...


@overload
def collect_rules(*, stackdepth: int = 0) -> list[Rule]:
    ...


def collect_rules(
    *,
    globals: Mapping[str, Any] | None = None,
    module: str | None = None,
    stackdepth: int = 0,
) -> list[Rule]:
    """
    Collect all rules from the specified globals and locals. If they are not specified, the globals and locals of the
    calling frame are used.
    """

    def get_scope(stack: list[inspect.FrameInfo]) -> Mapping[str, Any]:
        container = id(stack[0].frame.f_globals)
        locals = []
        for frame in stack:
            if id(frame.frame.f_globals) == container:
                locals.append(frame.frame.f_locals)
        return ChainMap(*locals, stack[0].frame.f_globals)

    try:
        if globals is None:
            if module is None:
                globals = get_scope(inspect.stack()[stackdepth + 1 :])
            else:
                globals = sys.modules[module].__dict__

        result = []
        for v in chain(globals.values()):
            if isinstance(v, Rule):
                result.append(v)
        return result
    finally:
        del globals
