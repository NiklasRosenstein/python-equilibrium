from equilibrium.rules.Rule import Rule, collect_rules, rule


def test__collect_rules__picks_up_rules_from_nonlocals() -> None:
    @rule
    def a() -> int:
        return 42

    def get_rules() -> list[Rule]:
        @rule
        def b() -> int:
            return 42

        return list(collect_rules())

    assert len(get_rules()) == 2
    assert {x.id.rpartition(".")[2] for x in get_rules()} == {"a", "b"}
