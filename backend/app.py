from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Optional

import httpx
import psycopg
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT.parent / "frontend" / "dist"
INDEX_HTML = FRONTEND_DIST / "index.html"


def _get_db_conn():
    required = ["APP_DB_HOST", "APP_DB_PORT", "APP_DB_NAME", "APP_DB_USER", "APP_DB_PASSWORD"]
    if not all(os.environ.get(key) for key in required): raise RuntimeError("database is not configured")
    return psycopg.connect(host=os.environ["APP_DB_HOST"], port=int(os.environ["APP_DB_PORT"]), dbname=os.environ["APP_DB_NAME"], user=os.environ["APP_DB_USER"], password=os.environ["APP_DB_PASSWORD"], row_factory=dict_row)

async def _llm_chat(messages: list[dict], max_tokens: int = 7000) -> str:
    base_url, api_key, model = os.environ.get("APP_LLM_BASE_URL"), os.environ.get("APP_LLM_API_KEY"), os.environ.get("APP_LLM_MODEL")
    if not base_url or not api_key or not model: raise RuntimeError("LLM service is not configured")
    async with httpx.AsyncClient(timeout=75) as client:
        resp = await client.post(f"{base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "messages": messages, "max_tokens": max_tokens, "response_format": {"type": "json_object"}})
    resp.raise_for_status(); return resp.json()["choices"][0]["message"]["content"]

def _require_user(x_user_id: Optional[str]) -> dict:
    if not x_user_id: raise HTTPException(status_code=401, detail="missing X-User-ID")
    return {"userId": x_user_id, "username": x_user_id, "email": None}


Category = Literal["蔬菜", "水果", "乳制品", "蛋白质", "主食", "调味及其他"]


class Preferences(BaseModel):
    budget: int = Field(default=100, ge=30, le=500)
    flavors: list[str] = Field(default_factory=list)
    avoid: str = ""
    pantry: str = ""
    max_minutes: int = Field(default=30, ge=10, le=60)
    preference_mode: Literal["balanced", "quick", "homestyle", "light", "custom"] = "balanced"
    staple_preferences: list[str] = Field(default_factory=list)
    meal_styles: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=lambda: ["灶台"])
    meal_slots: list[str] = Field(
        default_factory=lambda: ["mon-d", "tue-d", "wed-d", "thu-d", "fri-d", "sat-l", "sat-d", "sun-l", "sun-d"],
        min_length=1, max_length=21,
    )


class Ingredient(BaseModel):
    name: str
    quantity: float = Field(gt=0)
    unit: str
    category: Category


class Meal(BaseModel):
    id: str
    day: str
    date: str = ""
    mealType: Literal["早餐", "午餐", "晚餐"]
    title: str
    emoji: str = "🍜"
    minutes: int = Field(ge=5, le=60)
    tags: list[str]
    nutrition: str
    ingredients: list[Ingredient]
    steps: list[str] = Field(min_length=3, max_length=4)


class ShoppingItem(Ingredient):
    meals: list[str]


class ShoppingDelta(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    summary: str
    weekStart: str = ""
    estimatedCostMin: int = Field(default=0, ge=0)
    estimatedCostMax: int = Field(default=0, ge=0)
    budgetWarning: bool = False
    meals: list[Meal]
    shoppingList: list[ShoppingItem] = Field(default_factory=list)
    pantryUsed: list[str] = Field(default_factory=list)
    tips: list[str]
    lastShoppingDelta: Optional[ShoppingDelta] = None


class SwapIn(BaseModel):
    preferences: Preferences
    plan: Plan
    mealId: str


class ChecksIn(BaseModel):
    checkedItems: list[str]


DAY_DEFS = [("mon", "周一"), ("tue", "周二"), ("wed", "周三"), ("thu", "周四"),
            ("fri", "周五"), ("sat", "周六"), ("sun", "周日")]
MEAL_DEFS = [("b", "早餐"), ("l", "午餐"), ("d", "晚餐")]
ALL_SLOTS = [(f"{day_code}-{meal_code}", day_name, meal_name)
             for day_code, day_name in DAY_DEFS for meal_code, meal_name in MEAL_DEFS]
SLOT_MAP = {slot_id: (day_name, meal_name) for slot_id, day_name, meal_name in ALL_SLOTS}
SLOT_ORDER = {slot_id: index for index, (slot_id, _, _) in enumerate(ALL_SLOTS)}
DAY_INDEX = {day_name: index for index, (_, day_name) in enumerate(DAY_DEFS)}
LEAFY = ("青菜", "菠菜", "生菜", "油菜", "菜心", "茼蒿", "空心菜", "娃娃菜", "白菜")


def _selected_slots(pref: Preferences) -> list[tuple[str, str, str]]:
    unique = list(dict.fromkeys(pref.meal_slots))
    invalid = [slot for slot in unique if slot not in SLOT_MAP]
    if invalid:
        raise HTTPException(status_code=422, detail=f"invalid meal slots: {invalid}")
    return [(slot, *SLOT_MAP[slot]) for slot in sorted(unique, key=SLOT_ORDER.get)]


def _current_week_start(today: Optional[date] = None) -> date:
    today = today or date.today()
    return today - timedelta(days=today.weekday())


def _week_start(today: Optional[date] = None) -> date:
    today = today or date.today()
    current_monday = _current_week_start(today)
    return current_monday + timedelta(days=7) if today.weekday() >= 5 else current_monday


def _plan_is_stale(stored_week: date | str, today: Optional[date] = None) -> bool:
    stored = date.fromisoformat(stored_week) if isinstance(stored_week, str) else stored_week
    return stored < _current_week_start(today)


def _assign_schedule(plan: Plan, pref: Preferences, start: Optional[date] = None) -> Plan:
    slots = _selected_slots(pref)
    if len(plan.meals) != len(slots):
        raise ValueError("meal count does not match selected slots")
    start = start or _week_start()
    plan.weekStart = start.isoformat()
    for meal, (slot_id, day_name, meal_type) in zip(plan.meals, slots):
        meal.id, meal.day, meal.mealType = slot_id, day_name, meal_type
        meal.date = (start + timedelta(days=DAY_INDEX[day_name])).isoformat()
    return plan


def I(name: str, quantity: float, unit: str, category: Category) -> Ingredient:
    return Ingredient(name=name, quantity=quantity, unit=unit, category=category)


def _avoid_terms(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,，、;；\s]+", text) if x.strip()]


def _is_banned(name: str, avoid: str) -> bool:
    terms = _avoid_terms(avoid)
    groups = {
        "鸡蛋": ("鸡蛋", "蛋"), "蛋": ("鸡蛋", "蛋"), "牛肉": ("牛", "肥牛"), "牛": ("牛", "肥牛"),
        "猪肉": ("猪", "肉末", "火腿"), "鸡肉": ("鸡肉", "鸡胸", "鸡腿", "鸡丝"),
        "肉类": ("肉", "牛", "猪", "鸡胸", "鸡腿", "鸡丝", "火腿", "虾", "鱼"),
        "海鲜": ("虾", "鱼", "海鲜", "贝"), "豆制品": ("豆腐", "豆皮", "豆干", "豆浆"),
    }
    lowered = name.lower()
    for term in terms:
        needles = groups.get(term, (term,))
        if any(n.lower() in lowered for n in needles):
            return True
    return False


def _safe_protein(avoid: str, index: int) -> tuple[str, str, float, str]:
    options = [("鸡蛋", "个", 1, "🥚"), ("嫩豆腐", "克", 120, "🥢"), ("虾滑", "克", 100, "🦐"),
               ("鸡胸肉", "克", 100, "🍗"), ("豆皮", "克", 80, "🥢"), ("鹰嘴豆", "克", 100, "🫘"),
               ("鱼片", "克", 100, "🐟")]
    safe = [x for x in options if not _is_banned(x[0], avoid)] or [("鹰嘴豆", "克", 100, "🫘")]
    return safe[index % len(safe)]


def _fallback_meals(pref: Preferences, rotation: int = 0) -> list[Meal]:
    breakfast = [
        ("香蕉燕麦酸奶杯", "香蕉", 1, "个", "即食燕麦", 40, "克", "无糖酸奶", 1, "盒", "快手早餐"),
        ("番茄鸡蛋全麦吐司", "番茄", 1, "个", "全麦吐司", 2, "片", "鸡蛋", 1, "个", "能量早餐"),
        ("玉米豆浆水果碗", "冷冻玉米", 100, "克", "无糖豆浆", 1, "盒", "苹果", 1, "个", "清爽早餐"),
        ("紫薯酸奶坚果碗", "紫薯", 1, "个", "无糖酸奶", 1, "盒", "坚果", 15, "克", "高纤早餐"),
        ("豆腐蔬菜全麦卷", "番茄", 1, "个", "全麦饼", 1, "张", "嫩豆腐", 100, "克", "均衡早餐"),
        ("花生酱香蕉吐司", "香蕉", 1, "个", "全麦吐司", 2, "片", "花生酱", 1, "份", "周末早餐"),
        ("燕麦鸡蛋蔬菜粥", "即食燕麦", 40, "克", "鸡蛋", 1, "个", "冷冻蔬菜", 80, "克", "饱腹早餐"),
    ]
    # 备用餐单故意覆盖米饭、面食、粉类与杂粮轻食，避免默认被单一用户口味绑架。
    main = [
        ("番茄青菜{p}汤面", "番茄", 1, "个", "小青菜", 150, "克", "挂面", 100, "克", "清淡鲜香", "面食", "汤羹"),
        ("西兰花{p}盖饭", "西兰花", 180, "克", "胡萝卜", 60, "克", "即食米饭", 1, "份", "家常均衡", "米饭", "家常菜"),
        ("菠菜菌菇{p}粉丝汤", "菠菜", 150, "克", "鲜香菇", 100, "克", "粉丝", 1, "把", "清淡暖胃", "粉类", "汤羹"),
        ("彩蔬{p}杂粮碗", "西兰花", 150, "克", "冷冻玉米", 80, "克", "即食杂粮饭", 1, "份", "轻盈饱腹", "杂粮轻食", "轻食"),
        ("香菇胡萝卜{p}拌饭", "鲜香菇", 100, "克", "胡萝卜", 100, "克", "即食米饭", 1, "份", "一碗满足", "米饭", "一锅端"),
        ("番茄玉米{p}米线", "番茄", 1, "个", "冷冻玉米", 80, "克", "米线", 1, "包", "酸甜鲜香", "粉类", "一锅端"),
        ("西葫芦{p}荞麦面", "西葫芦", 180, "克", "胡萝卜", 60, "克", "荞麦面", 100, "克", "清爽快拌", "面食", "轻食"),
        ("紫菜豆腐{p}汤饭", "紫菜", 5, "克", "番茄", 1, "个", "即食米饭", 1, "份", "暖胃收尾", "米饭", "汤羹"),
        ("西兰花{p}土豆泥碗", "西兰花", 150, "克", "土豆", 1, "个", "即食杂粮饭", 1, "份", "高纤饱腹", "杂粮轻食", "轻食"),
        ("胡萝卜玉米{p}拌饭", "胡萝卜", 100, "克", "冷冻玉米", 80, "克", "即食米饭", 1, "份", "耐储食材", "米饭", "家常菜"),
        ("菌菇{p}乌冬面", "鲜香菇", 120, "克", "西兰花", 120, "克", "乌冬面", 1, "包", "鲜香快手", "面食", "一锅端"),
        ("番茄{p}米粉", "番茄", 1, "个", "金针菇", 100, "克", "米粉", 1, "包", "酸香开胃", "粉类", "汤羹"),
        ("彩蔬{p}全麦卷", "生菜", 100, "克", "番茄", 1, "个", "全麦饼", 1, "张", "轻食便携", "杂粮轻食", "轻食"),
        ("土豆胡萝卜{p}盖饭", "土豆", 1, "个", "胡萝卜", 80, "克", "即食米饭", 1, "份", "家常下饭", "米饭", "家常菜"),
    ]
    preferred_staples = set(pref.staple_preferences)
    preferred_styles = set(pref.meal_styles)
    main = sorted(main, key=lambda x: -((3 if x[-2] in preferred_staples else 0) + (2 if x[-1] in preferred_styles else 0)))
    meals: list[Meal] = []
    main_index = 0
    equipment = pref.equipment or ["灶台"]
    for index, (slot_id, day_name, meal_type) in enumerate(_selected_slots(pref)):
        if meal_type == "早餐":
            template, veg1, q1, u1, staple, qs, us, protein, pq, pu, tag = breakfast[(DAY_INDEX[day_name] + rotation) % len(breakfast)]
            if _is_banned(protein, pref.avoid):
                protein, pu, pq, _ = _safe_protein(pref.avoid, index + rotation)
            title = template if not _is_banned(template, pref.avoid) else f"{veg1}{protein}{staple}早餐"
            first_category: Category = "水果" if any(x in veg1 for x in ("香蕉", "苹果", "水果")) else "蔬菜"
            protein_category: Category = "乳制品" if any(x in protein for x in ("酸奶", "牛奶")) else "蛋白质"
            ingredients = [I(veg1, q1, u1, first_category), I(staple, qs, us, "主食"), I(protein, pq, pu, protein_category)]
            emoji = "☀️"
        else:
            base = main[(main_index + rotation) % len(main)]
            main_index += 1
            template, veg1, q1, u1, veg2, q2, u2, staple, qs, us, tag, _, _ = base
            protein, pu, pq, emoji = _safe_protein(pref.avoid, index + rotation)
            title = template.format(p=protein)
            ingredients = [I(veg1, q1, u1, "蔬菜"), I(veg2, q2, u2, "蔬菜"), I(protein, pq, pu, "蛋白质"), I(staple, qs, us, "主食")]
        if "灶台" in equipment:
            steps = ["洗净并准备所有食材", "用锅先处理蛋白质和耐煮食材", "加入主食和其余食材，调味后即可开饭"]
        elif "微波炉" in equipment:
            steps = ["食材切成小块放入可微波容器", "加入少量水，分段加热并中途翻拌", "确认熟透后加入主食和调味料"]
        elif "空气炸锅" in equipment and pref.max_minutes >= 15:
            title = f"空气炸锅{veg1}{protein}能量碗"
            steps = ["食材切小块并薄薄刷油", "空气炸锅加热至熟，中途翻面", "搭配即食主食和蔬菜装碗"]
        else:
            title = f"免开火{veg1}{protein}能量碗"
            steps = ["选择可即食食材并洗净切块", "将主食、蔬菜和蛋白质分区装碗", "加入简单酱汁拌匀即可"]
        minutes = min(pref.max_minutes, 15)
        meals.append(Meal(
            id=slot_id, day=day_name, mealType=meal_type, title=title, emoji=emoji, minutes=minutes,
            tags=[tag, f"{minutes}分钟"], nutrition="主食、蛋白质和蔬菜搭配完整",
            ingredients=ingredients, steps=steps,
        ))
    return meals


def _canonical(name: str) -> str:
    name = re.sub(r"\s+", "", name)
    aliases = {
        "蛋": "鸡蛋", "土鸡蛋": "鸡蛋", "龙口粉丝": "粉丝", "小青菜": "青菜", "油菜": "青菜",
        "嫩豆腐": "豆腐", "老豆腐": "豆腐", "西红柿": "番茄", "鲜香菇": "香菇",
    }
    return aliases.get(name, name)


STAPLE_GROUPS = {
    "米饭": ("米饭", "大米", "白粥"),
    "面食": ("面", "乌冬", "意面", "吐司", "全麦饼", "馒头"),
    "粉类": ("粉丝", "米粉", "米线", "土豆粉", "年糕"),
    "杂粮轻食": ("燕麦", "杂粮", "玉米", "紫薯", "土豆", "芋头"),
}
PROTEIN_GROUPS = {
    "蛋类": ("鸡蛋", "蛋"), "豆制品": ("豆腐", "豆皮", "豆干", "豆浆"),
    "禽类": ("鸡胸", "鸡腿", "鸡丝", "鸡肉"), "畜肉": ("牛", "猪", "肉末", "火腿"),
    "水产": ("虾", "鱼", "海鲜"), "乳制品": ("酸奶", "牛奶"), "豆类": ("鹰嘴豆", "豆类"),
}


def _ingredient_group(meal: Meal, groups: dict[str, tuple[str, ...]]) -> Optional[str]:
    names = " ".join(i.name for i in meal.ingredients)
    for group, tokens in groups.items():
        if any(token in names for token in tokens):
            return group
    return None


def _equipment_error(meal: Meal, equipment: list[str]) -> bool:
    allowed = set(equipment or ["灶台"])
    if "无厨具" in allowed:
        allowed = {"无厨具"}
    if "灶台" in allowed:
        return False
    steps = " ".join(meal.steps)
    stove_words = ("热锅", "炒锅", "翻炒", "焯水", "煮开", "锅中")
    if any(word in steps for word in stove_words):
        return True
    tool_markers = {"微波炉": ("微波",), "空气炸锅": ("空气炸锅",), "电饭锅": ("电饭锅",)}
    for tool, markers in tool_markers.items():
        if tool not in allowed and any(marker in steps for marker in markers):
            return True
    if allowed == {"无厨具"}:
        return not any(word in steps for word in ("免开火", "即食", "直接食用", "拌匀即可"))
    return not any(any(marker in steps for marker in markers) for tool, markers in tool_markers.items() if tool in allowed) and "免开火" not in steps


def _meal_structure_error(meal: Meal) -> bool:
    categories = {item.category for item in meal.ingredients}
    has_produce = bool(categories & {"蔬菜", "水果"})
    has_protein = bool(categories & {"蛋白质", "乳制品"})
    has_staple = "主食" in categories
    return not (has_produce and has_protein and has_staple)


def _time_realism_error(meal: Meal) -> bool:
    text = meal.title + " " + " ".join(meal.steps)
    minimums = {"慢炖": 40, "炖": 30, "焖饭": 25, "卤": 30, "煲汤": 30, "烘焙": 25}
    return any(keyword in text and meal.minutes < minimum for keyword, minimum in minimums.items())


def _parse_pantry(text: str) -> list[dict]:
    entries: list[dict] = []
    for raw in re.split(r"[,，、;；\n]+", text):
        raw = raw.strip()
        if not raw:
            continue
        half = re.match(r"半\s*(包|把|个|克|盒|份)\s*(.+)", raw)
        front = re.match(r"(\d+(?:\.\d+)?)\s*(包|把|个|克|盒|份|瓣)\s*(.+)", raw)
        back = re.match(r"(.+?)\s*(\d+(?:\.\d+)?)\s*(包|把|个|克|盒|份|瓣)", raw)
        if half:
            unit, name, qty = half.group(1), half.group(2), 0.5
        elif front:
            qty, unit, name = float(front.group(1)), front.group(2), front.group(3)
        elif back:
            name, qty, unit = back.group(1), float(back.group(2)), back.group(3)
        else:
            continue
        qty = float(qty)
        canon = _canonical(name)
        if canon == "粉丝" and unit == "包":
            qty, unit = qty * 3, "把"
        entries.append({"name": canon, "quantity": qty, "unit": unit, "source": raw})
    return entries


def _shopping(meals: list[Meal], pantry: str = "") -> tuple[list[ShoppingItem], list[str]]:
    merged: dict[tuple[str, str, str], ShoppingItem] = {}
    for meal in meals:
        for item in meal.ingredients:
            key = (_canonical(item.name), item.unit, item.category)
            if key not in merged:
                merged[key] = ShoppingItem(name=item.name, quantity=item.quantity, unit=item.unit, category=item.category, meals=[meal.id])
            else:
                merged[key].quantity += item.quantity
                if meal.id not in merged[key].meals:
                    merged[key].meals.append(meal.id)
    used: list[str] = []
    pantry_entries = _parse_pantry(pantry)
    for entry in pantry_entries:
        for key, item in merged.items():
            if key[0] == entry["name"] and item.unit == entry["unit"] and item.quantity > 0:
                consumed = min(item.quantity, entry["quantity"])
                item.quantity = round(item.quantity - consumed, 2)
                if consumed > 0:
                    used.append(f"{item.name} {consumed:g}{item.unit}")
                break
    order = {"蔬菜": 0, "水果": 1, "乳制品": 2, "蛋白质": 3, "主食": 4, "调味及其他": 5}
    result = [x for x in merged.values() if x.quantity > 0]
    return sorted(result, key=lambda x: (order[x.category], x.name)), used


def _shopping_diff(old: list[ShoppingItem], new: list[ShoppingItem]) -> ShoppingDelta:
    def mapping(items):
        return {(_canonical(x.name), x.unit, x.category): x for x in items}
    a, b = mapping(old), mapping(new)
    added, removed = [], []
    for key in sorted(set(a) | set(b)):
        old_q = a[key].quantity if key in a else 0
        new_q = b[key].quantity if key in b else 0
        name = (b.get(key) or a[key]).name
        unit = (b.get(key) or a[key]).unit
        delta = round(new_q - old_q, 2)
        if delta > 0:
            added.append(f"{name} +{delta:g}{unit}")
        elif delta < 0:
            removed.append(f"{name} -{abs(delta):g}{unit}")
    return ShoppingDelta(added=added, removed=removed)


def _fallback_plan(pref: Preferences) -> Plan:
    meals = _fallback_meals(pref)
    shopping, used = _shopping(meals, pref.pantry)
    breakfasts = sum(m.mealType == "早餐" for m in meals)
    main_meals = len(meals) - breakfasts
    cost_min = breakfasts * 5 + main_meals * 8
    cost_max = breakfasts * 9 + main_meals * 13
    count = len(meals)
    plan = Plan(
        summary=f"按你选择的{count}顿来安排：优先消耗易坏食材，再用耐储食材收尾。",
        estimatedCostMin=cost_min, estimatedCostMax=cost_max, budgetWarning=cost_max > pref.budget,
        meals=meals, shoppingList=shopping, pantryUsed=used,
        tips=["易坏绿叶菜优先安排在最早的用餐日", "蛋白质按单顿分装冷冻，前一晚移到冷藏解冻", "未选择的餐次不会生成，也不会计入采购量"],
    )
    return _assign_schedule(plan, pref)


def _extract_json(text: str) -> dict:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start, end = clean.find("{"), clean.rfind("}")
        if start >= 0 and end > start:
            return json.loads(clean[start:end + 1])
        raise


def _validate_plan(plan: Plan, pref: Preferences) -> list[str]:
    errors: list[str] = []
    slots = _selected_slots(pref)
    expected_ids = [x[0] for x in slots]
    if len(plan.meals) != len(slots) or [m.id for m in plan.meals] != expected_ids:
        errors.append(f"必须严格返回用户选中的{len(slots)}顿及固定顺序")
    titles = [m.title.strip() for m in plan.meals]
    if len(set(titles)) != len(titles):
        errors.append("菜名不能重复")
    for meal in plan.meals:
        joined = meal.title + " " + " ".join(i.name for i in meal.ingredients)
        if meal.minutes > pref.max_minutes:
            errors.append(f"{meal.id}超过时间限制")
        if _is_banned(joined, pref.avoid):
            errors.append(f"{meal.id}含忌口食材")
        if _equipment_error(meal, pref.equipment):
            errors.append(f"{meal.id}使用了不可用厨具")
        if _meal_structure_error(meal):
            errors.append(f"{meal.id}缺少主食、蛋白质或蔬果中的一类")
        if _time_realism_error(meal):
            errors.append(f"{meal.id}的菜式与标注耗时不匹配")
    early_days_selected = any(DAY_INDEX[day] <= 2 for _, day, _ in slots)
    late_leafy = sum(
        1 for meal in plan.meals
        if DAY_INDEX.get(meal.day, 6) > 2 and any(any(word in i.name for word in LEAFY) for i in meal.ingredients)
    )
    if early_days_selected and late_leafy > max(1, len(plan.meals) // 7):
        errors.append("易坏绿叶菜应尽量安排在较早的用餐日")
    flavor_limit = max(1, round(len(plan.meals) * 0.45))
    for flavor in pref.flavors:
        count = sum(flavor in (m.title + "".join(m.tags)) for m in plan.meals)
        if count > flavor_limit:
            errors.append(f"{flavor}口味重复超过{flavor_limit}顿")
    if len(plan.meals) >= 5:
        staple_counts: dict[str, int] = {}
        protein_counts: dict[str, int] = {}
        for meal in plan.meals:
            staple = _ingredient_group(meal, STAPLE_GROUPS)
            protein = _ingredient_group(meal, PROTEIN_GROUPS)
            if staple: staple_counts[staple] = staple_counts.get(staple, 0) + 1
            if protein: protein_counts[protein] = protein_counts.get(protein, 0) + 1
        staple_limit = max(2, round(len(plan.meals) * (0.55 if pref.staple_preferences else 0.45)))
        if staple_counts and max(staple_counts.values()) > staple_limit:
            errors.append(f"同一主食大类不应超过{staple_limit}顿")
        protein_limit = 3 if len(plan.meals) <= 18 else 4
        if protein_counts and max(protein_counts.values()) > protein_limit:
            errors.append(f"同一蛋白质大类不应超过{protein_limit}顿")
    if plan.estimatedCostMin > plan.estimatedCostMax:
        errors.append("预算区间顺序错误")
    return errors


def _plan_prompt(pref: Preferences) -> str:
    slots = _selected_slots(pref)
    slot_text = "、".join(f"{slot_id}={day}{meal_type}" for slot_id, day, meal_type in slots)
    count = len(slots)
    flavor_limit = max(1, round(count * 0.45))
    mode_names = {"balanced":"不挑，合理搭配", "quick":"15分钟快手", "homestyle":"家常均衡", "light":"轻食少油", "custom":"自定义"}
    staple_text = ','.join(pref.staple_preferences) or '不限制，主动轮换米饭、面食、粉类和杂粮轻食'
    style_text = ','.join(pref.meal_styles) or '不限制'
    equipment_text = ','.join(pref.equipment) or '无厨具/免开火'
    return f"""你是一位面向多种生活方式的独居饮食规划助手。用户选择了{count}个用餐时段：{slot_text}。只为这些时段规划，不得补充未选择的餐次。
方案模式：{mode_names[pref.preference_mode]}；预算：{pref.budget}元；每顿总耗时不超过{pref.max_minutes}分钟；可用厨具：{equipment_text}。
软偏好（只提高推荐概率，绝不能让每顿都一样）：主食={staple_text}；餐食风格={style_text}；口味={','.join(pref.flavors) or '不限制'}。
硬性忌口：{pref.avoid or '无'}；家中已有：{pref.pantry or '无'}。
硬约束：忌口绝不能出现；步骤只能使用用户拥有的厨具；每餐必须同时包含主食、蛋白质来源和蔬果；易坏食材安排在较早用餐日；同一包装跨餐复用；菜名不重复；耗时必须真实，炖、焖饭、卤、煲汤等慢菜不能伪装成10或15分钟；价格给合理区间。选择5顿及以上时，默认同一主食大类不超过约45%，同一蛋白质大类不超过3次，并轮换米饭、面食、粉类、杂粮及不同烹饪方式；用户的主食偏好是倾向而不是唯一答案。
只返回JSON，不要Markdown：{{"summary":"一句话","estimatedCostMin":整数,"estimatedCostMax":整数,"meals":[严格{count}个meal],"tips":[3条]}}。
meal：{{"id":"指定slot id","day":"周一","mealType":"早餐/午餐/晚餐","title":"菜名","emoji":"emoji","minutes":15,"tags":["标签"],"nutrition":"一句话","ingredients":[{{"name":"食材","quantity":数值,"unit":"克/个/包/把/份/瓣/片/盒/张","category":"蔬菜/水果/乳制品/蛋白质/主食/调味及其他"}}],"steps":["步骤1","步骤2","步骤3"]}}。
meal的id必须严格按这个顺序：{','.join(x[0] for x in slots)}。"""


def _finalize(plan: Plan, pref: Preferences) -> Plan:
    plan = _assign_schedule(plan, pref)
    plan.shoppingList, plan.pantryUsed = _shopping(plan.meals, pref.pantry)
    plan.budgetWarning = plan.estimatedCostMax > pref.budget
    plan.lastShoppingDelta = None
    return plan


def _load_current(owner_id: str) -> Optional[dict]:
    try:
        with _get_db_conn() as conn:
            row = conn.execute("SELECT preferences, plan, checked_items, week_start FROM meal_plans WHERE owner_id = %s", (owner_id,)).fetchone()
            return row
    except Exception:
        return None


def _save_current(owner_id: str, pref: Preferences, plan: Plan, checked: Optional[list[str]] = None) -> None:
    try:
        if checked is None:
            current = _load_current(owner_id)
            checked = list(current["checked_items"]) if current else []
        with _get_db_conn() as conn:
            conn.execute(
                "INSERT INTO meal_plans (owner_id, preferences, plan, checked_items, week_start, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW()) ON CONFLICT (owner_id) DO UPDATE SET "
                "preferences = EXCLUDED.preferences, plan = EXCLUDED.plan, checked_items = EXCLUDED.checked_items, "
                "week_start = EXCLUDED.week_start, updated_at = NOW()",
                (owner_id, Jsonb(pref.model_dump()), Jsonb(plan.model_dump()), Jsonb(checked), date.fromisoformat(plan.weekStart)),
            )
            conn.commit()
    except Exception:
        pass


app = FastAPI(title="一周好好吃")
SECURITY_CSP = "frame-ancestors 'self'"


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["content-security-policy"] = SECURITY_CSP
    return response


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/whoami")
def whoami(x_user_id: Optional[str] = Header(None, alias="X-User-ID")):
    return _require_user(x_user_id)


@app.get("/api/meal-plan/current")
def current_plan(x_user_id: Optional[str] = Header(None, alias="X-User-ID")):
    user = _require_user(x_user_id)
    row = _load_current(user["userId"])
    if not row:
        return {"plan": None, "preferences": None, "checkedItems": [], "stale": False}
    if _plan_is_stale(row["week_start"]):
        return {"plan": None, "preferences": row["preferences"], "checkedItems": [], "stale": True}
    return {"plan": row["plan"], "preferences": row["preferences"], "checkedItems": row["checked_items"], "stale": False}


@app.post("/api/meal-plan/generate", response_model=Plan)
async def generate_plan(body: Preferences, x_user_id: Optional[str] = Header(None, alias="X-User-ID")):
    user = _require_user(x_user_id)
    plan: Optional[Plan] = None
    try:
        raw = await _llm_chat([{"role": "user", "content": _plan_prompt(body)}])
        data = _extract_json(raw)
        data.setdefault("shoppingList", [])
        data.setdefault("pantryUsed", [])
        data.setdefault("budgetWarning", False)
        plan = Plan.model_validate(data)
        plan = _assign_schedule(plan, body)
        errors = _validate_plan(plan, body)
        if errors:
            repair = _plan_prompt(body) + "\n上一次结果存在这些问题：" + "；".join(errors) + "。请全部修正后重新输出完整JSON。"
            raw = await _llm_chat([{"role": "user", "content": repair}])
            data = _extract_json(raw)
            data.setdefault("shoppingList", [])
            data.setdefault("pantryUsed", [])
            data.setdefault("budgetWarning", False)
            plan = _assign_schedule(Plan.model_validate(data), body)
            if _validate_plan(plan, body):
                raise ValueError("repaired plan still violates rules")
        plan = _finalize(plan, body)
    except Exception:
        plan = _fallback_plan(body)
    _save_current(user["userId"], body, plan, checked=[])
    return plan


@app.post("/api/meal-plan/swap", response_model=Plan)
async def swap_meal(body: SwapIn, x_user_id: Optional[str] = Header(None, alias="X-User-ID")):
    user = _require_user(x_user_id)
    idx = next((i for i, meal in enumerate(body.plan.meals) if meal.id == body.mealId), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="没有找到这一顿")
    current = body.plan.meals[idx]
    available = sorted({i.name for m in body.plan.meals for i in m.ingredients})
    prompt = f"""替换一顿独居餐。原餐：{current.model_dump_json(ensure_ascii=False)}。优先复用已采购食材和库存：{','.join(available)}；{body.preferences.pantry}。软偏好：口味={','.join(body.preferences.flavors) or '不限'}，主食={','.join(body.preferences.staple_preferences) or '不限'}，风格={','.join(body.preferences.meal_styles) or '不限'}；硬性忌口：{body.preferences.avoid or '无'}；可用厨具：{','.join(body.preferences.equipment) or '无厨具'}。总耗时不超过{body.preferences.max_minutes}分钟，不能与其余菜名重复，不能把软偏好理解为每顿强制。只返回单个meal JSON，id/day/date/mealType保持原值，steps为3步，category只能是蔬菜/水果/乳制品/蛋白质/主食/调味及其他。"""
    replacement: Optional[Meal] = None
    try:
        raw = await _llm_chat([{"role": "user", "content": prompt}], max_tokens=2500)
        replacement = Meal.model_validate(_extract_json(raw))
        replacement.id, replacement.day, replacement.date, replacement.mealType = current.id, current.day, current.date, current.mealType
        joined = replacement.title + " " + " ".join(i.name for i in replacement.ingredients)
        other_titles = {m.title for m in body.plan.meals if m.id != current.id}
        if replacement.minutes > body.preferences.max_minutes or _is_banned(joined, body.preferences.avoid) or replacement.title in other_titles or _equipment_error(replacement, body.preferences.equipment) or _meal_structure_error(replacement) or _time_realism_error(replacement):
            raise ValueError("replacement violates rules")
    except Exception:
        alternatives = _fallback_meals(body.preferences, rotation=3)
        for offset in range(1, len(alternatives) + 1):
            candidate = alternatives[(idx + offset) % len(alternatives)].model_copy(deep=True)
            if candidate.title not in {m.title for m in body.plan.meals if m.id != current.id}:
                replacement = candidate
                break
        assert replacement is not None
        replacement.id, replacement.day, replacement.date, replacement.mealType = current.id, current.day, current.date, current.mealType
    old_list = body.plan.shoppingList
    meals = body.plan.meals[:]
    meals[idx] = replacement
    new_list, used = _shopping(meals, body.preferences.pantry)
    body.plan.meals = meals
    body.plan.shoppingList = new_list
    body.plan.pantryUsed = used
    body.plan.lastShoppingDelta = _shopping_diff(old_list, new_list)
    current_row = _load_current(user["userId"])
    checked = list(current_row["checked_items"]) if current_row else []
    valid = {f"{x.category}-{x.name}" for x in new_list}
    checked = [x for x in checked if x in valid]
    _save_current(user["userId"], body.preferences, body.plan, checked=checked)
    return body.plan


@app.put("/api/meal-plan/checks")
def save_checks(body: ChecksIn, x_user_id: Optional[str] = Header(None, alias="X-User-ID")):
    user = _require_user(x_user_id)
    try:
        with _get_db_conn() as conn:
            conn.execute("UPDATE meal_plans SET checked_items = %s, updated_at = NOW() WHERE owner_id = %s", (Jsonb(body.checkedItems), user["userId"]))
            conn.commit()
    except Exception:
        pass
    return {"ok": True}


if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


@app.get("/")
def index():
    if not INDEX_HTML.exists():
        return HTMLResponse("<h1>frontend/dist 不存在</h1>", status_code=503)
    return FileResponse(INDEX_HTML)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"error": "not found"}, status_code=404)
    real = FRONTEND_DIST / full_path
    if real.is_file():
        return FileResponse(real)
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return JSONResponse({"error": "frontend/dist 未 build"}, status_code=503)
