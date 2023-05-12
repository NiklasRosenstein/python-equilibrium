from dataclasses import dataclass
from typing import Any


@dataclass
class Signature:
    """
    A signature represents the inputs and output of a rule.
    """

    inputs: set[type[Any]]
    output_type: type[Any]

    def __str__(self) -> str:
        sig = "(" + ", ".join(x.__name__ for x in self.inputs) + ")"
        if self.output_type:
            sig += " -> " + self.output_type.__name__
        return sig
