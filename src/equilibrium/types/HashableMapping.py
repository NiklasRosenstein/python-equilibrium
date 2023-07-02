from typing import Hashable, Mapping, TypeVar

__all__ = ["HashableMapping"]

K_Hashable = TypeVar("K_Hashable", bound=Hashable)
V_Hashable = TypeVar("V_Hashable", bound=Hashable)


class HashableMapping(Mapping[K_Hashable, V_Hashable], Hashable):
    """
    A hashable mapping.
    """
