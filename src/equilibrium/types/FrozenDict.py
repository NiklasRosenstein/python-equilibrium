from frozendict import frozendict

from equilibrium.types.HashableMapping import HashableMapping, K_Hashable, V_Hashable

__all__ = ["FrozenDict"]


class FrozenDict(frozendict[K_Hashable, V_Hashable], HashableMapping[K_Hashable, V_Hashable]):
    """
    A concrete implementation of a hashable mapping.
    """
