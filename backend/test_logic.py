from datetime import date
import sys
import types

# 本地测试环境未必预装 psycopg；逻辑测试不触发数据库，提供最小导入桩。
try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    pg = types.ModuleType("psycopg")
    rows = types.ModuleType("psycopg.rows")
    json_types = types.ModuleType("psycopg.types.json")
    rows.dict_row = object()
    json_types.Jsonb = lambda value: value
    pg.rows = rows
    sys.modules["psycopg"] = pg
    sys.modules["psycopg.rows"] = rows
    sys.modules["psycopg.types"] = types.ModuleType("psycopg.types")
    sys.modules["psycopg.types.json"] = json_types

from backend.app import (
    Preferences, _fallback_plan, _is_banned, _parse_pantry,
    _shopping, _shopping_diff, _validate_plan,
)


def run():
    parsed = _parse_pantry("2个鸡蛋、1包粉丝、半包粉丝、青菜200克")
    assert any(x["name"] == "鸡蛋" and x["quantity"] == 2 for x in parsed)
    assert sum(x["quantity"] for x in parsed if x["name"] == "粉丝") == 4.5
    assert any(x["name"] == "青菜" and x["quantity"] == 200 for x in parsed)

    pref = Preferences(budget=80, flavors=["清淡"], avoid="鸡蛋、牛肉", pantry="2个鸡蛋、1包粉丝", max_minutes=15)
    plan = _fallback_plan(pref)
    assert len(plan.meals) == 9
    assert [m.id for m in plan.meals] == ["mon-d", "tue-d", "wed-d", "thu-d", "fri-d", "sat-l", "sat-d", "sun-l", "sun-d"]
    assert len({m.date for m in plan.meals}) == 7
    assert all(m.minutes <= 15 for m in plan.meals)
    assert all(not _is_banned(m.title + " " + " ".join(i.name for i in m.ingredients), pref.avoid) for m in plan.meals)
    assert not _validate_plan(plan, pref)

    full, _ = _shopping(plan.meals, "")
    reduced, used = _shopping(plan.meals, "1包粉丝")
    full_qty = sum(x.quantity for x in full if "粉丝" in x.name)
    reduced_qty = sum(x.quantity for x in reduced if "粉丝" in x.name)
    assert reduced_qty == max(0, full_qty - 3)
    assert used

    diff = _shopping_diff(full, reduced)
    assert any("粉丝" in x for x in diff.removed)
    assert plan.estimatedCostMin <= plan.estimatedCostMax
    assert date.fromisoformat(plan.weekStart)
    print("logic tests passed", {"meals": len(plan.meals), "shopping": len(plan.shoppingList), "pantryUsed": plan.pantryUsed})


if __name__ == "__main__":
    run()
