from typing import Hashable, Sequence

from equilibrium.types.HashableMapping import V_Hashable


class HashableSequence(Sequence[V_Hashable], Hashable):
    """
    A hashable sequence.
    """
