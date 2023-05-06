from pytest import fixture

from equilibrium.rulesengine.Rule import Rule
from equilibrium.rulesengine.RulesGraph import RulesGraph


@fixture
def sut() -> RulesGraph:
    r"""
    Creates a rule graph of three rules:

                     str
        (decimal) __/  \__ (hex)
                    \  /
                     int
                      |
                    float
    """

    r1 = Rule(
        func=lambda p, e: int(p.get(str)),
        input_types={str},
        output_type=int,
        id="r1",
    )
    r2 = Rule(
        func=lambda p, e: int(p.get(str), base=16),
        input_types={str},
        output_type=int,
        id="r2",
    )
    r3 = Rule(
        func=lambda p, e: float(p.get(int)),
        input_types={int},
        output_type=float,
        id="r3",
    )
    g = RulesGraph([r1, r2, r3])
    return g


def test__RulesGraph__rules_for(sut: RulesGraph) -> None:
    assert {r.id for r in sut.rules(int)} == {"r1", "r2"}
    assert {r.id for r in sut.rules(float)} == {"r3"}


def test__RulesGraph__reduce(sut: RulesGraph) -> None:
    assert set(sut.reduce({int}, float)._graph.nodes) == {int, float}
    assert set(sut.reduce({str}, int)._graph.nodes) == {str, int}
    assert set(sut.reduce({str}, float)._graph.nodes) == {str, int, float}
    assert sut.reduce({str}, float)._graph.nodes == sut._graph.nodes
    assert sut.reduce({str}, float)._graph.edges == sut._graph.edges
