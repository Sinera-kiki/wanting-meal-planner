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
    """Public adapter: configure PostgreSQL with APP_DB_* environment variables."""
    required = ["APP_DB_HOST", "APP_DB_PORT", "APP_DB_NAME", "APP_DB_USER", "APP_DB_PASSWORD"]
    if not all(os.environ.get(key) for key in required):
        raise RuntimeError("database is not configured")
    return psycopg.connect(
        host=os.environ["APP_DB_HOST"], port=int(os.environ["APP_DB_PORT"]),
        dbname=os.environ["APP_DB_NAME"], user=os.environ["APP_DB_USER"],
        password=os.environ["APP_DB_PASSWORD"], row_factory=dict_row,
    )


async def _llm_chat(messages: list[dict], max_tokens: int = 7000) -> str:
    """Provider-neutral OpenAI-compatible adapter used by the public repository."""
    base_url = os.environ.get("APP_LLM_BASE_URL")
    api_key = os.environ.get("APP_LLM_API_KEY")
    model = os.environ.get("APP_LLM_MODEL")
    if not base_url or not api_key or not model:
        raise RuntimeError("LLM service is not configured")
    async with httpx.AsyncClient(timeout=75) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens,
                  "response_format": {"type": "json_object"}},
        )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _require_user(x_user_id: Optional[str]) -> dict:
    """Public adapter: replace this header with your own authentication provider in production."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing X-User-ID")
    return {"userId": x_user_id, "username": x_user_id, "email": None}


Category = Literal["蔬菜", "蛋白质", "主食", "调味及其他"]


class Preferences(BaseModel):
    budget: int = Field(default=100, ge=30, le=500)
    flavors: list[str] = Field(default_factory=lambda: ["酸辣", "清淡"])
    avoid: str = ""
    pantry: str = ""
    max_minutes: int = Field(default=15, ge=10, le=60)


class Ingredient(BaseModel):
    name: str
    quantity: float = Field(gt=0)
    unit: str
    category: Category


class Meal(BaseModel):
    id: str
    day: str
    date: str = ""
    mealType: Literal["午餐", "晚餐"]
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


DAYS = [("mon-d", "周一", "晚餐"), ("tue-d", "周二", "晚餐"), ("wed-d", "周三", "晚餐"),
        ("thu-d", "周四", "晚餐"), ("fri-d", "周五", "晚餐"), ("sat-l", "周六", "午餐"),
        ("sat-d", "周六", "晚餐"), ("sun-l", "周日", "午餐"), ("sun-d", "周日", "晚餐")]
DAY_INDEX = {name: index for index, (_, name, _) in enumerate(DAYS[:5])}
DAY_INDEX.update({"周六": 5, "周日": 6})
LEAFY = ("青菜", "菠菜", "生菜", "油菜", "菜心", "茼蒿", "空心菜", "娃娃菜", "白菜")


def _week_start() -> date:
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    # 周末通常是在为下一周采购；工作日则继续规划本周。
    return current_monday + timedelta(days=7) if today.weekday() >= 5 else current_monday


def _assign_schedule(plan: Plan, start: Optional[date] = None) -> Plan:
    start = start or _week_start()
    plan.weekStart = start.isoformat()
    for meal, (mid, day_name, meal_type) in zip(plan.meals, DAYS):
        meal.id, meal.day, meal.mealType = mid, day_name, meal_type
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
               ("鸡胸肉", "克", 100, "🍗"), ("豆皮", "克", 80, "🥢"), ("鹰嘴豆", "克", 100, "🫘")]
    safe = [x for x in options if not _is_banned(x[0], avoid)] or [("鹰嘴豆", "克", 100, "🫘")]
    return safe[index % len(safe)]


def _fallback_meals(pref: Preferences) -> list[Meal]:
    bases = [
        ("番茄青菜{p}面", "番茄", 1, "个", "小青菜", 150, "克", "挂面", 100, "克", "清淡鲜香"),
        ("酸辣娃娃菜{p}土豆粉", "娃娃菜", 180, "克", "香菇", 80, "克", "土豆粉", 1, "包", "酸辣开胃"),
        ("菠菜菌菇{p}粉丝汤", "菠菜", 150, "克", "鲜香菇", 100, "克", "粉丝", 1, "把", "清淡暖胃"),
        ("番茄香菇{p}荞麦面", "番茄", 1, "个", "鲜香菇", 100, "克", "荞麦面", 100, "克", "鲜香耐饱"),
        ("西兰花{p}拌面", "西兰花", 180, "克", "胡萝卜", 60, "克", "挂面", 100, "克", "少油快拌"),
        ("胡萝卜玉米{p}汤面", "胡萝卜", 100, "克", "冷冻玉米", 80, "克", "荞麦面", 100, "克", "周末快手"),
        ("金针菇酸汤{p}土豆粉", "金针菇", 120, "克", "番茄", 1, "个", "土豆粉", 1, "包", "酸汤满足"),
        ("香菇胡萝卜{p}炒面", "鲜香菇", 100, "克", "胡萝卜", 100, "克", "挂面", 100, "克", "耐储食材"),
        ("紫菜番茄{p}粉丝汤", "紫菜", 5, "克", "番茄", 1, "个", "粉丝", 1, "把", "清淡收尾"),
    ]
    meals: list[Meal] = []
    for idx, ((mid, day_name, meal_type), base) in enumerate(zip(DAYS, bases)):
        template, veg1, q1, u1, veg2, q2, u2, staple, qs, us, tag = base
        protein, pu, pq, emoji = _safe_protein(pref.avoid, idx)
        title = template.format(p=protein)
        ingredients = [I(veg1, q1, u1, "蔬菜"), I(veg2, q2, u2, "蔬菜"),
                       I(protein, pq, pu, "蛋白质"), I(staple, qs, us, "主食")]
        meals.append(Meal(
            id=mid, day=day_name, mealType=meal_type, title=title, emoji=emoji, minutes=15,
            tags=[tag, "15分钟"], nutrition="主食、蛋白质和蔬菜搭配完整",
            ingredients=ingredients,
            steps=[f"洗净并切好{veg1}、{veg2}，处理好{protein}", f"锅中加少量油或水，先将{protein}和耐煮食材煮熟", f"加入{staple}和其余蔬菜，调味后即可开饭"],
        ))
    return meals


def _canonical(name: str) -> str:
    name = re.sub(r"\s+", "", name)
    aliases = {
        "蛋": "鸡蛋", "土鸡蛋": "鸡蛋", "龙口粉丝": "粉丝", "小青菜": "青菜", "油菜": "青菜",
        "嫩豆腐": "豆腐", "老豆腐": "豆腐", "西红柿": "番茄", "鲜香菇": "香菇",
    }
    return aliases.get(name, name)


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
    order = {"蔬菜": 0, "蛋白质": 1, "主食": 2, "调味及其他": 3}
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
    vegetarian = all(not any(k in x.name for k in ("肉", "虾", "鱼")) for x in shopping)
    cost_min, cost_max = (58, 78) if vegetarian else (72, 98)
    plan = Plan(
        summary="先吃绿叶菜，再用耐储食材收尾；9顿复用原料，一个人也尽量不浪费。",
        estimatedCostMin=cost_min, estimatedCostMax=cost_max, budgetWarning=cost_max > pref.budget,
        meals=meals, shoppingList=shopping, pantryUsed=used,
        tips=["绿叶菜集中在周一至周三，洗净沥干后用厨房纸包好冷藏", "蛋白质按单顿分装冷冻，前一晚移到冷藏解冻", "周五后优先使用胡萝卜、紫菜、菌菇和冷冻食材"],
    )
    return _assign_schedule(plan)


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
    if len(plan.meals) != 9 or [m.id for m in plan.meals] != [x[0] for x in DAYS]:
        errors.append("必须严格返回固定顺序的9顿")
    titles = [m.title.strip() for m in plan.meals]
    if len(set(titles)) != len(titles):
        errors.append("菜名不能重复")
    for meal in plan.meals:
        joined = meal.title + " " + " ".join(i.name for i in meal.ingredients)
        if meal.minutes > pref.max_minutes:
            errors.append(f"{meal.id}超过时间限制")
        if _is_banned(joined, pref.avoid):
            errors.append(f"{meal.id}含忌口食材")
    late_leafy = 0
    for meal in plan.meals[3:]:
        if any(any(word in i.name for word in LEAFY) for i in meal.ingredients):
            late_leafy += 1
    if late_leafy > 1:
        errors.append("绿叶菜应主要安排在周一至周三")
    for flavor in pref.flavors:
        count = sum(flavor in (m.title + "".join(m.tags)) for m in plan.meals)
        if count > 4:
            errors.append(f"{flavor}口味重复超过4顿")
    if plan.estimatedCostMin > plan.estimatedCostMax:
        errors.append("预算区间顺序错误")
    return errors


def _plan_prompt(pref: Preferences) -> str:
    return f"""你是一位擅长独居饮食规划的营养餐单助手。为北京独居用户规划一周9顿：周一至周五晚餐，周末午晚餐。每顿总耗时不超过{pref.max_minutes}分钟，偏好粉面、粉丝、土豆粉等快手一锅餐。
预算：{pref.budget}元；偏好口味：{','.join(pref.flavors) or '不限'}；硬性忌口：{pref.avoid or '无'}；家中已有：{pref.pantry or '无'}。
硬约束：忌口绝不能出现；绿叶菜优先安排周一至周三；同一包装跨餐复用；每顿包含主食、蛋白质和蔬菜；口味只是偏好，不要求顿顿出现，同一种主要口味最多4顿；菜名不重复；所有步骤总耗时真实不超过限制；价格给北京生鲜零售的合理区间而非假精确值。
只返回JSON，不要Markdown：{{"summary":"一句话","estimatedCostMin":整数,"estimatedCostMax":整数,"meals":[9个meal],"tips":[3条]}}。
meal：{{"id":"固定id","day":"周一","mealType":"晚餐","title":"菜名","emoji":"emoji","minutes":15,"tags":["标签"],"nutrition":"一句话","ingredients":[{{"name":"食材","quantity":数值,"unit":"克/个/包/把/份/瓣","category":"蔬菜/蛋白质/主食/调味及其他"}}],"steps":["步骤1","步骤2","步骤3"]}}。
固定id顺序：mon-d,tue-d,wed-d,thu-d,fri-d,sat-l,sat-d,sun-l,sun-d。"""


def _finalize(plan: Plan, pref: Preferences) -> Plan:
    plan = _assign_schedule(plan)
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
        return {"plan": None, "preferences": None, "checkedItems": []}
    return {"plan": row["plan"], "preferences": row["preferences"], "checkedItems": row["checked_items"]}


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
        plan = _assign_schedule(plan)
        errors = _validate_plan(plan, body)
        if errors:
            repair = _plan_prompt(body) + "\n上一次结果存在这些问题：" + "；".join(errors) + "。请全部修正后重新输出完整JSON。"
            raw = await _llm_chat([{"role": "user", "content": repair}])
            data = _extract_json(raw)
            data.setdefault("shoppingList", [])
            data.setdefault("pantryUsed", [])
            data.setdefault("budgetWarning", False)
            plan = _assign_schedule(Plan.model_validate(data))
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
    prompt = f"""替换一顿独居快手餐。原餐：{current.model_dump_json(ensure_ascii=False)}。优先复用已采购食材和库存：{','.join(available)}；{body.preferences.pantry}。偏好：{','.join(body.preferences.flavors)}；硬性忌口：{body.preferences.avoid or '无'}。总耗时不超过{body.preferences.max_minutes}分钟，不能与其余菜名重复。只返回单个meal JSON，id/day/date/mealType保持原值，steps为3步，category只能是蔬菜/蛋白质/主食/调味及其他。"""
    replacement: Optional[Meal] = None
    try:
        raw = await _llm_chat([{"role": "user", "content": prompt}], max_tokens=2500)
        replacement = Meal.model_validate(_extract_json(raw))
        replacement.id, replacement.day, replacement.date, replacement.mealType = current.id, current.day, current.date, current.mealType
        joined = replacement.title + " " + " ".join(i.name for i in replacement.ingredients)
        other_titles = {m.title for m in body.plan.meals if m.id != current.id}
        if replacement.minutes > body.preferences.max_minutes or _is_banned(joined, body.preferences.avoid) or replacement.title in other_titles:
            raise ValueError("replacement violates rules")
    except Exception:
        alternatives = _fallback_meals(body.preferences)
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
