import { useEffect, useMemo, useState } from 'react'
import './styles.css'
import { buildDemoPlan, demoSwap, mockPlan } from './mockPlan'

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'
const DEMO_VIEW = DEMO_MODE ? new URLSearchParams(window.location.search).get('view') : null

type Ingredient = { name: string; quantity: number; unit: string; category: string }
type Meal = { id: string; day: string; date: string; mealType: string; title: string; emoji: string; minutes: number; tags: string[]; nutrition: string; ingredients: Ingredient[]; steps: string[] }
type ShoppingItem = Ingredient & { meals: string[] }
type ShoppingDelta = { added: string[]; removed: string[] }
type Plan = { summary: string; weekStart: string; estimatedCostMin: number; estimatedCostMax: number; budgetWarning: boolean; meals: Meal[]; shoppingList: ShoppingItem[]; pantryUsed: string[]; tips: string[]; lastShoppingDelta?: ShoppingDelta | null }
type Pref = { budget: number; flavors: string[]; avoid: string; pantry: string; max_minutes: number; meal_slots: string[] }

const flavorOptions = ['酸辣', '清淡', '鲜香', '少油', '微辣']
const dayOrder = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const dayDefs = [['mon','周一'],['tue','周二'],['wed','周三'],['thu','周四'],['fri','周五'],['sat','周六'],['sun','周日']] as const
const mealDefs = [['b','早餐'],['l','午餐'],['d','晚餐']] as const
const defaultSlots = ['mon-d','tue-d','wed-d','thu-d','fri-d','sat-l','sat-d','sun-l','sun-d']
const presetSlots: Record<string,string[]> = {
  '默认9顿': defaultSlots,
  '工作日晚餐': ['mon-d','tue-d','wed-d','thu-d','fri-d'],
  '每天晚餐': dayDefs.map(([code]) => `${code}-d`),
  '全周三餐': dayDefs.flatMap(([code]) => mealDefs.map(([meal]) => `${code}-${meal}`)),
}
const categoryIcon: Record<string, string> = { 蔬菜: '🥬', 蛋白质: '🥚', 主食: '🍜', 调味及其他: '🧂' }
const fmt = (n: number) => Number.isInteger(n) ? String(n) : n.toFixed(1)

export default function App() {
  const [pref, setPref] = useState<Pref>({ budget: 100, flavors: ['酸辣', '清淡'], avoid: '', pantry: '', max_minutes: 15, meal_slots: defaultSlots })
  const [plan, setPlan] = useState<Plan | null>(DEMO_VIEW ? JSON.parse(JSON.stringify(mockPlan)) : null)
  const [selected, setSelected] = useState<Meal | null>(DEMO_VIEW === 'detail' ? JSON.parse(JSON.stringify(mockPlan.meals[0])) : null)
  const [tab, setTab] = useState<'plan' | 'list' | 'settings'>(DEMO_VIEW === 'list' ? 'list' : 'plan')
  const [loading, setLoading] = useState(false)
  const [swapping, setSwapping] = useState<string | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [notice, setNotice] = useState('')
  const [restoring, setRestoring] = useState(true)
  const [toast, setToast] = useState('')

  useEffect(() => {
    if (DEMO_MODE) { setRestoring(false); return }
    fetch('/api/meal-plan/current').then(async r => {
      if (!r.ok) return
      const data = await r.json()
      if (data.plan) setPlan(data.plan)
      if (data.preferences) setPref({ ...data.preferences, meal_slots: data.preferences.meal_slots?.length ? data.preferences.meal_slots : defaultSlots })
      if (data.checkedItems) setChecked(new Set(data.checkedItems))
    }).catch(() => {}).finally(() => setRestoring(false))
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 4200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const groups = useMemo(() => dayOrder.map(day => ({ day, meals: plan?.meals.filter(m => m.day === day) || [] })).filter(g => g.meals.length), [plan])
  const shoppingGroups = useMemo(() => ['蔬菜', '蛋白质', '主食', '调味及其他'].map(category => ({ category, items: plan?.shoppingList.filter(i => i.category === category) || [] })).filter(g => g.items.length), [plan])

  const toggleFlavor = (flavor: string) => setPref(p => ({ ...p, flavors: p.flavors.includes(flavor) ? p.flavors.filter(x => x !== flavor) : [...p.flavors, flavor] }))

  async function generate() {
    setLoading(true); setNotice('')
    try {
      if (DEMO_MODE) {
        await new Promise(resolve => window.setTimeout(resolve, 650))
        setPlan(buildDemoPlan(pref.meal_slots)); setChecked(new Set()); setTab('plan'); return
      }
      const r = await fetch('/api/meal-plan/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pref) })
      if (!r.ok) throw new Error('生成失败')
      setPlan(await r.json()); setChecked(new Set()); setTab('plan')
    } catch {
      setNotice('刚刚有点忙，请再试一次')
    } finally { setLoading(false) }
  }

  async function swap(meal: Meal) {
    if (!plan) return
    setSwapping(meal.id)
    try {
      let next: Plan
      if (DEMO_MODE) {
        await new Promise(resolve => window.setTimeout(resolve, 450))
        next = demoSwap(plan, meal.id)
      } else {
        const r = await fetch('/api/meal-plan/swap', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preferences: pref, plan, mealId: meal.id }) })
        if (!r.ok) throw new Error('换菜失败')
        next = await r.json()
      }
      const validKeys = new Set(next.shoppingList.map((x: ShoppingItem) => `${x.category}-${x.name}`))
      setChecked(prev => new Set([...prev].filter(key => validKeys.has(key))))
      setPlan(next); setSelected(next.meals.find((m: Meal) => m.id === meal.id) || null)
      const delta = next.lastShoppingDelta as ShoppingDelta | undefined
      const parts = [delta?.added?.length ? `新增 ${delta.added.join('、')}` : '', delta?.removed?.length ? `减少 ${delta.removed.join('、')}` : ''].filter(Boolean)
      setToast(parts.length ? `采购变化：${parts.join('；')}` : '采购清单没有变化')
    } catch { setNotice('这道菜暂时没换成功，请再试一次') }
    finally { setSwapping(null) }
  }

  const toggleCheck = (item: ShoppingItem) => {
    const key = `${item.category}-${item.name}`
    setChecked(prev => {
      const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key)
      if (!DEMO_MODE) fetch('/api/meal-plan/checks', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ checkedItems: [...next] }) }).catch(() => {})
      return next
    })
  }

  const showDate = (value: string) => {
    const d = new Date(`${value}T00:00:00`)
    return Number.isNaN(d.getTime()) ? '' : `${d.getMonth() + 1}月${d.getDate()}日`
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand-mark">好</div>
      <div><strong>一周好好吃</strong><span>一个人的轻松餐桌</span></div>
      {plan && <button className="icon-button" onClick={() => setTab('settings')} aria-label="偏好设置">⚙</button>}
    </header>

    <main>
      {restoring && <section className="restore-page"><span className="spinner dark"/><p>正在取回这周的餐单…</p></section>}
      {!restoring && !plan && <section className="onboarding">
        {DEMO_MODE && <div className="demo-badge">公开演示版 · 使用示例数据</div>}
        <div className="hero-art"><span className="leaf leaf-a">●</span><span className="leaf leaf-b">●</span><div className="bowl" aria-hidden="true"><svg viewBox="0 0 100 100"><path d="M18 46h64c0 24-13 38-32 38S18 70 18 46Z" fill="#fffaf0" stroke="#345c43" strokeWidth="4"/><path d="M26 45c5-9 13-14 24-14s20 5 25 14" fill="none" stroke="#dc7c43" strokeWidth="5" strokeLinecap="round"/><path d="M39 27c-3-7 4-9 1-15M57 27c-3-7 4-9 1-15" fill="none" stroke="#93ab78" strokeWidth="4" strokeLinecap="round"/><path d="M32 57h36" stroke="#d9c7a6" strokeWidth="3" strokeLinecap="round"/></svg></div></div>
        <p className="eyebrow">MEAL PLANNER</p>
        <h1>一周吃什么，<br/><em>交给我来想。</em></h1>
        <p className="hero-copy">先选这周准备自己做饭的时段，再按预算、口味和库存安排快手餐。选几顿，就只规划几顿。</p>
        <PreferenceForm pref={pref} setPref={setPref} toggleFlavor={toggleFlavor} />
        {notice && <p className="notice">{notice}</p>}
        <button className="primary" onClick={generate} disabled={loading || pref.meal_slots.length === 0}>{loading ? <><span className="spinner"/>正在搭配这一周…</> : <>生成我的 {pref.meal_slots.length} 顿餐单 <span>→</span></>}</button>
        <p className="fineprint">{DEMO_MODE ? '演示版不会请求真实 AI，也不会上传你的输入' : '会优先复用食材，并照顾基础营养搭配'}</p>
      </section>}

      {plan && tab === 'plan' && <section className="plan-page">
        <div className="week-head"><div><p className="eyebrow">THIS WEEK · {showDate(plan.weekStart)} 起</p><h1>这周，好好吃饭</h1></div><div className={`budget-ring ${plan.budgetWarning ? 'warning' : ''}`}><strong>¥{plan.estimatedCostMin}–{plan.estimatedCostMax}</strong><span>{plan.budgetWarning ? '可能超预算' : '预计区间'}</span></div></div>
        <div className="summary-card"><span>🌱</span><p>{plan.summary}</p></div>
        <div className="day-list">
          {groups.map(group => <div className="day-block" key={group.day}>
            <div className="day-label"><span>{group.day.replace('周', '')}</span><small>{group.day}</small></div>
            <div className="day-meals">{group.meals.map(meal => <button className="meal-card" key={meal.id} onClick={() => setSelected(meal)}>
              <div className="meal-emoji">{meal.emoji}</div>
              <div className="meal-main"><div className="meal-meta"><span>{showDate(meal.date)}</span><i>·</i><span>{meal.mealType}</span><i>·</i><span>{meal.minutes}分钟</span></div><h3>{meal.title}</h3><div className="tag-row">{meal.tags.slice(0,2).map(t => <b key={t}>{t}</b>)}</div></div>
              <span className="chevron">›</span>
            </button>)}</div>
          </div>)}
        </div>
        <div className="tip-card"><b>保存小提示</b><p>{plan.tips[0]}</p></div>
      </section>}

      {plan && tab === 'list' && <section className="list-page">
        <p className="eyebrow">SHOPPING LIST</p><h1>这周要买的</h1>
        <div className="list-progress"><div><strong>{checked.size}</strong><span> / {plan.shoppingList.length} 已完成</span></div><div className="progress-track"><i style={{width: `${plan.shoppingList.length ? checked.size / plan.shoppingList.length * 100 : 0}%`}}/></div></div>
        {plan.pantryUsed?.length > 0 && <div className="pantry-card"><b>家中库存已抵扣</b><p>{plan.pantryUsed.join('、')}</p></div>}
        {shoppingGroups.map(group => <div className="shopping-group" key={group.category}><h2><span>{categoryIcon[group.category]}</span>{group.category}<small>{group.items.length}样</small></h2>
          {group.items.map(item => { const key = `${item.category}-${item.name}`, done = checked.has(key); return <button className={`shop-item ${done ? 'done' : ''}`} key={key} onClick={() => toggleCheck(item)}><i>{done ? '✓' : ''}</i><span>{item.name}</span><b>{fmt(item.quantity)}{item.unit}</b></button> })}
        </div>)}
        <div className="tip-card"><b>按什么顺序吃？</b><p>{plan.tips[1]}</p><p>{plan.tips[2]}</p></div>
      </section>}

      {plan && tab === 'settings' && <section className="settings-page">
        <p className="eyebrow">PREFERENCES</p><h1>调整这一周</h1><p className="subcopy">改完后会重新生成整周餐单。</p>
        <PreferenceForm pref={pref} setPref={setPref} toggleFlavor={toggleFlavor} />
        {notice && <p className="notice">{notice}</p>}
        <button className="primary" onClick={generate} disabled={loading || pref.meal_slots.length === 0}>{loading ? '正在重新搭配…' : `按新偏好生成 ${pref.meal_slots.length} 顿`}</button>
      </section>}
    </main>

    {toast && <div className="toast">{toast}</div>}

    {plan && <nav className="bottom-nav"><button className={tab === 'plan' ? 'active' : ''} onClick={() => setTab('plan')}><span>▦</span>周餐单</button><button className={tab === 'list' ? 'active' : ''} onClick={() => setTab('list')}><span>✓</span>采购单</button><button className={tab === 'settings' ? 'active' : ''} onClick={() => setTab('settings')}><span>⚙</span>偏好</button></nav>}

    {selected && <div className="sheet-backdrop" onClick={() => setSelected(null)}><article className="sheet" onClick={e => e.stopPropagation()}>
      <div className="grabber"/><button className="sheet-close" onClick={() => setSelected(null)}>×</button>
      <div className="sheet-hero"><span>{selected.emoji}</span><div><small>{selected.day} {showDate(selected.date)} · {selected.mealType} · {selected.minutes}分钟</small><h2>{selected.title}</h2></div></div>
      <p className="nutrition">营养搭配 · {selected.nutrition}</p>
      <h3 className="section-title">准备这些</h3><div className="ingredient-grid">{selected.ingredients.map(i => <div key={`${i.name}-${i.unit}`}><span>{i.name}</span><b>{fmt(i.quantity)}{i.unit}</b></div>)}</div>
      <h3 className="section-title">15分钟开饭</h3><ol className="steps">{selected.steps.map((s, i) => <li key={s}><b>{i+1}</b><span>{s}</span></li>)}</ol>
      <button className="swap-button" disabled={swapping === selected.id} onClick={() => swap(selected)}>{swapping === selected.id ? '正在想一道新的…' : '↻ 这顿换一道'}</button>
    </article></div>}
  </div>
}

function PreferenceForm({ pref, setPref, toggleFlavor }: { pref: Pref; setPref: (p: Pref | ((p: Pref) => Pref)) => void; toggleFlavor: (s: string) => void }) {
  const toggleSlot = (slot: string) => setPref(p => {
    const exists = p.meal_slots.includes(slot)
    if (exists && p.meal_slots.length === 1) return p
    return { ...p, meal_slots: exists ? p.meal_slots.filter(x => x !== slot) : [...p.meal_slots, slot] }
  })
  return <div className="pref-card">
    <label className="field-label meal-count-label">这周准备自己做几顿？ <strong>{pref.meal_slots.length}顿</strong></label>
    <div className="preset-row">{Object.entries(presetSlots).map(([name, slots]) => <button type="button" key={name} onClick={() => setPref(p => ({...p, meal_slots:[...slots]}))}>{name}</button>)}</div>
    <div className="meal-schedule">
      <div className="schedule-head"><span></span>{mealDefs.map(([,name]) => <b key={name}>{name}</b>)}</div>
      {dayDefs.map(([dayCode, dayName]) => <div className="schedule-row" key={dayCode}><strong>{dayName}</strong>{mealDefs.map(([mealCode, mealName]) => { const slot=`${dayCode}-${mealCode}`; const active=pref.meal_slots.includes(slot); return <button type="button" aria-label={`${dayName}${mealName}`} aria-pressed={active} className={active?'active':''} key={slot} onClick={() => toggleSlot(slot)}>{active?'✓':'+'}</button> })}</div>)}
    </div>
    <p className="schedule-tip">至少选择1顿；可自由组合一周最多21顿</p>
    <label className="field-label">这周预算 <strong>¥{pref.budget}</strong></label>
    <input className="range" type="range" min="50" max="200" step="10" value={pref.budget} onChange={e => setPref(p => ({...p, budget: Number(e.target.value)}))}/>
    <div className="range-note"><span>¥50</span><span>¥200</span></div>
    <label className="field-label">喜欢的口味</label><div className="chips">{flavorOptions.map(f => <button className={pref.flavors.includes(f) ? 'selected' : ''} key={f} onClick={() => toggleFlavor(f)}>{f}</button>)}</div>
    <label className="field-label" htmlFor="pantry">家里还有什么？</label><input id="pantry" value={pref.pantry} onChange={e => setPref(p => ({...p, pantry: e.target.value}))} placeholder="比如：半包粉丝、2个鸡蛋"/>
    <label className="field-label" htmlFor="avoid">不吃或忌口</label><input id="avoid" value={pref.avoid} onChange={e => setPref(p => ({...p, avoid: e.target.value}))} placeholder="没有可以留空"/>
  </div>
}
