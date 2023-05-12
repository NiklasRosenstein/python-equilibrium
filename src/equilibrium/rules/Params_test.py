from dataclasses import dataclass
from typing import Generic, TypeVar

from pytest import raises

from equilibrium.rules import Params

T = TypeVar("T")


@dataclass(frozen=True)
class MyGeneric(Generic[T]):
    value: T


def test__Params__cannot_delinate_between_instances_of_different_generic_types() -> None:
    with raises(AssertionError) as excinfo:
        Params([MyGeneric[int](1), MyGeneric[str]("a")])
    assert str(excinfo.value) == "Duplicate types in Params"


def test__Params__can_delinate_between_instances_of_different_generic_types_when_explicitly_specified() -> None:
    params = Params(
        {
            MyGeneric[int]: MyGeneric(1),
            MyGeneric[str]: MyGeneric("a"),
        }
    )
    assert params.get(MyGeneric[int]) == MyGeneric(1)
    assert params.get(MyGeneric[str]) == MyGeneric("a")

    with raises(KeyError):
        assert params.get(MyGeneric)
