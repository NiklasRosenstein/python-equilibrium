from typing import Iterable

from equilibrium.types.HashableMapping import V_Hashable
from equilibrium.types.HashableSequence import HashableSequence


class FrozenList(HashableSequence[V_Hashable], tuple[V_Hashable]):  # type: ignore[misc]
    def __new__(cls, sequence: Iterable[V_Hashable]) -> "FrozenList[V_Hashable]":
        return tuple.__new__(FrozenList, tuple(sequence))
