from copy import deepcopy
from decimal import Decimal
import pytest
from container_planner.solver import LIMITS, decorate, solve, totals, validate
from conftest import make_atom


@pytest.mark.parametrize("q,cbm,weight,typ", [(280,"0.1","10","20GP"),(580,"0.1","10","40GP"),(680,"0.1","10","40HQ"),(100,"0.1","228","20GP")])
def test_exact_boundaries(q,cbm,weight,typ):
    atoms=[make_atom(q=q,cbm=cbm,weight=weight)]
    result=solve({"atoms":atoms},seconds=2)
    assert len(result["containers"])==1
    assert result["containers"][0]["type"]==typ
    assert not validate(result["containers"],atoms)


def test_two_dimensions_and_precision():
    atoms=[make_atom(q=500,cbm="0.091008",weight="44.2"),make_atom("b","b",q=400,cbm="0.17072001",weight="31.8")]
    result=solve({"atoms":atoms},seconds=2)
    assert not validate(result["containers"],atoms)
    index={a["id"]:a for a in atoms}
    for c in result["containers"]:
        v,w=totals(c,index)
        assert v<=Decimal(LIMITS[c["type"]]["cbm"])
        assert w<=22800


def test_factory_warehouse_batch_are_hard_boundaries():
    atoms=[make_atom(),make_atom("b","b",factory="续泰"),make_atom("c","c",warehouse="DCVIC"),make_atom("d","d",day="2027-01-11")]
    result=solve({"atoms":atoms},seconds=1)
    assert len(result["containers"])==4
    assert result["optimal"]
    assert not validate(result["containers"],atoms)
    mixed=deepcopy(result["containers"])
    mixed[1]["allocations"].append(mixed[0]["allocations"].pop())
    assert any("混有" in e for e in validate(mixed,atoms))


def test_split_and_lock_preserved():
    atoms=[make_atom(q=1000)]
    result=solve({"atoms":atoms},seconds=1)
    assert len(result["containers"])==2
    locked=deepcopy(result["containers"][:1])
    locked[0]["locked"]=True
    next_result=solve({"atoms":atoms},locked,seconds=1)
    assert next_result["containers"][0]["allocations"]==locked[0]["allocations"]
    assert not next_result["optimal"]
    assert not validate(next_result["containers"],atoms)


def test_split_count_before_small_container_size():
    # Each product can fit in one container; combining them would cause unnecessary splits.
    atoms=[make_atom(q=400),make_atom("b","b",q=400)]
    result=solve({"atoms":atoms},seconds=3)
    assert len(result["containers"])==2
    uses={a["id"]:sum(any(r["atom_id"]==a["id"] for r in c["allocations"]) for c in result["containers"]) for a in atoms}
    assert uses=={"a":1,"b":1}


def test_timeout_returns_valid_solution():
    atoms=[make_atom(str(i),str(i),q=100+i,cbm="0.12456789",weight="36.7") for i in range(25)]
    result=solve({"atoms":atoms},seconds=.001)
    assert not result["optimal"]
    assert not validate(result["containers"],atoms)


def test_overweight_and_invalid_lock():
    with pytest.raises(ValueError,match="单件"):
        solve({"atoms":[make_atom(q=1,weight="22800.0001")]})
    atoms=[make_atom(q=1,cbm="28.00000001")]
    result=solve({"atoms":atoms})
    result["containers"][0]["type"]="20GP"
    assert any("超体积" in e for e in validate(result["containers"],atoms))
    with pytest.raises(ValueError,match="锁定"):
        solve({"atoms":atoms},result["containers"])


def test_new_products_separate_and_undated_cabinets_can_receive_dates():
    atoms = [make_atom(day=""), {**make_atom("b", "b", day=""), "load_class":"NEW"}]
    result = solve({"atoms":atoms}, seconds=1)
    assert len(result["containers"]) == 2
    assert not validate(result["containers"], atoms)
    result["containers"][0]["date"] = "2026-11-20"
    assert not validate(result["containers"], atoms)
    mixed = deepcopy(result["containers"])
    mixed[0]["allocations"].extend(mixed[1]["allocations"])
    assert any("新品" in e for e in validate(mixed[:1], atoms))
    dated = [make_atom()]
    plan = solve({"atoms":dated})
    plan["containers"][0]["date"] = "2026-11-20"
    assert any("已确认" in e for e in validate(plan["containers"], dated))


def test_abc_prefers_same_grade_without_extra_cabinets():
    atoms = [{**make_atom(str(i),str(i),q=200),"abc":grade} for i,grade in enumerate(["A","B","A","B"])]
    result = solve({"atoms":atoms},seconds=3)
    assert len(result["containers"]) == 2
    index = {a["id"]:a for a in atoms}
    assert all(len({index[r["atom_id"]]["abc"] for r in c["allocations"]}) == 1 for c in result["containers"])
    assert not validate(result["containers"],atoms)
