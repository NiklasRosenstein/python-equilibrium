from __future__ import annotations

from typing import Any, Collection, KeysView, TypeVar, cast, overload

from equilibrium.rulesengine.Signature import Signature

T = TypeVar("T")
U = TypeVar("U")

_Sentinel = object()


class Params:
    """
    The Params class is a container for strongly typed parameters that can be passed to a rule. It serves as the
    container for the input parameters to a rule. It is a simple dictionary that maps a type to a value.
    """

    def __init__(self, *args: object):
        self._params = {type(arg): arg for arg in args}
        self._hash: int | None = None
        assert len(self._params) == len(args), "Duplicate types in Params"

    def __contains__(self, param_type: type[Any]) -> bool:
        return param_type in self._params

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(tuple(sorted(map(hash, self._params.values()))))
        return self._hash

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({', '.join(map(repr, self._params.values()))})"

    def __or__(self, params: Params) -> Params:
        """
        Merge two parameter sets, taking precedence of the parameters in the right hand side.
        """

        return Params(*{**self._params, **params._params}.values())

    @overload
    def get(self, param_type: type[T]) -> T:
        ...

    @overload
    def get(self, param_type: type[T], default: U) -> T | U:
        ...

    def get(self, param_type: type[T], default: U | object = _Sentinel) -> T | U:
        try:
            return cast(T, self._params[param_type])
        except KeyError:
            if default is _Sentinel:
                raise KeyError(f"Parameter of type {param_type} not found")
            return cast(U, default)

    def types(self) -> KeysView[type[Any]]:
        return self._params.keys()

    def filter(self, types: Collection[type[Any]], total: bool = False) -> Params:
        """
        Return a new Params instance containing only the parameters of the specified types.
        """

        if total:
            return Params(*[self.get(t) for t in types])
        else:
            return Params(*[self.get(t) for t in types if t in self])

    def signature(self, output_type: type[Any]) -> Signature:
        """
        Obtain a signature for this set of parameters, with the specified output type.
        """

        return Signature(set(self._params.keys()), output_type)
