from pytest import raises

from equilibrium.rules.errors import MultipleMatchingRulesError, NoMatchingRulesError
from equilibrium.rules.Rule import Rule
from equilibrium.rules.RulesGraph import RulesGraph
from equilibrium.rules.Signature import Signature


def test__RulesGraph__rules_for() -> None:
    """
    Creates a rules graph like this:

        str -> int
        bool -> int
        int -> float

    And tests the output of `rules_for` for each type.
    """

    graph = RulesGraph(
        [
            Rule(
                func=lambda p: int(p.get(str)),
                input_types={str},
                output_type=int,
                id="r1",
            ),
            Rule(
                func=lambda p: int(p.get(bool)),
                input_types={bool},
                output_type=int,
                id="r2",
            ),
            Rule(
                func=lambda p: float(p.get(int)),
                input_types={int},
                output_type=float,
                id="r3",
            ),
        ]
    )

    assert {r.id for r in graph.rules_for(int)} == {"r1", "r2"}
    assert {r.id for r in graph.rules_for(float)} == {"r3"}


def test__RulesGraph__cannot_resolve_diamond_dependency() -> None:
    """
    Builds a rules graph like this:

        str -> int
        str -> bool -> int

    When the requested signature is `(str) -> int`, the engine should raise an exception as it cannot decide
    whether to use the short or the long path.
    """

    graph = RulesGraph(
        rules=[
            Rule(
                func=lambda p: int(p.get(str)),
                input_types={str},
                output_type=int,
                id="r1",
            ),
            Rule(
                func=lambda p: int(p.get(bool)),
                input_types={bool},
                output_type=int,
                id="r2",
            ),
            Rule(
                func=lambda p: bool(p.get(str)),
                input_types={str},
                output_type=bool,
                id="r3",
            ),
        ]
    )

    # There's a path for (bool) -> int.
    assert graph.find_path(Signature({bool}, int)) == [graph["r2"]]

    # There's no singular path for (str) -> int as it cannot decide to go ((str) -> bool) -> int or (str) -> int.
    with raises(MultipleMatchingRulesError) as excinfo1:
        graph.find_path(Signature({str}, int))
    assert sorted(excinfo1.value.paths, key=len) == [[graph["r1"]], [graph["r3"], graph["r2"]]]

    # There's no path for (float) -> bool.
    with raises(NoMatchingRulesError):
        graph.find_path(Signature({float}, bool))
