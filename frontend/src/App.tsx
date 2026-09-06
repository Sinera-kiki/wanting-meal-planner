import { useEffect, useMemo, useState } from 'react'
import './styles.css'
import { FoodIcon } from './FoodIcon'
import { buildDemoPlan, demoSwap, mockPlan } from './mockPlan'

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'
const DEMO_VIEW = DEMO_MODE ? new URLSearchParams(window.location.search).get('view') : null

type Ingredient = { name: string; quantity: number; unit: string; category: string }
type Meal = { id: string; day: string; date: string; mealType: string; title: string; emoji: string; minutes: number; tags: string[]; nutrition: string; ingredients: Ingredient[]; steps: string[] }
type ShoppingItem = Ingredient & { meals: string[] }
type ShoppingDelta = { added: string[]; removed: string[] }
type Plan = { summary: string; weekStart: string; estimatedCostMin: number; estimatedCostMax: number; budgetWarning: boolean; meals: Meal[]; shoppingList: ShoppingItem[]; pantryUsed: string[]; tips: string[]; lastShoppingDelta?: ShoppingDelta | null }
type PreferenceMode = 'balanced' | 'quick' | 'homestyle' | 'light' | 'custom'
type Pref = { budget: number; flavors: string[]; avoid: string; pantry: string; max_minutes: number; meal_slots: string[]; preference_mode: PreferenceMode; staple_preferences: string[]; meal_styles: string[]; equipment: string[] }

const flavorOptions = ['酸辣', '清淡', '鲜香', '微辣']
const stapleOptions = ['米饭', '面食', '粉类', '杂粮轻食']
const styleOptions = ['家常菜', '一锅端', '轻食', '汤羹']
const equipmentOptions = ['灶台', '微波炉', '电饭锅', '空气炸锅', '无厨具']
const modeDefs: { id: PreferenceMode; title: string; desc: string }[] = [
  { id:'balanced', title:'不挑，合理搭配', desc:'自动轮换主食和蛋白质' },
  { id:'quick', title:'15分钟快手', desc:'步骤少，优先省时间' },
  { id:'homestyle', title:'家常均衡', desc:'米饭和家常菜为主' },
  { id:'light', title:'轻食少油', desc:'清爽、少油、不过重' },
]
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
const categoryIcon: Record<string, string> = { 蔬菜: '🥬', 水果: '🍎', 乳制品: '🥛', 蛋白质: '🥚', 主食: '🍚', 调味及其他: '🧂' }
const defaultPref: Pref = { budget: 100, flavors: [], avoid: '', pantry: '', max_minutes: 30, meal_slots: defaultSlots, preference_mode: 'balanced', staple_preferences: [], meal_styles: [], equipment: ['灶台'] }
const normalizePref = (value: Partial<Pref> | null | undefined): Pref => ({ ...defaultPref, ...(value || {}), meal_slots: value?.meal_slots?.length ? value.meal_slots : defaultSlots, flavors: value?.flavors || [], staple_preferences: value?.staple_preferences || [], meal_styles: value?.meal_styles || [], equipment: value?.equipment?.length ? value.equipment : ['灶台'] })
const fmt = (n: number) => Number.isInteger(n) ? String(n) : n.toFixed(1)

export default function App() {
  const [pref, setPref] = useState<Pref>(defaultPref)
  const [savedPref, setSavedPref] = useState<Pref | null>(null)
  const [plan, setPlan] = useState<Plan | null>(DEMO_VIEW ? JSON.parse(JSON.stringify(mockPlan)) : null)
  const [selected, setSelected] = useState<Meal | null>(DEMO_VIEW === 'detail' ? JSON.parse(JSON.stringify(mockPlan.meals[0])) : null)
  const [tab, setTab] = useState<'plan' | 'list' | 'settings'>(DEMO_VIEW === 'list' ? 'list' : 'plan')
  const [loading, setLoading] = useState(false)
  const [swapping, setSwapping] = useState<string | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [notice, setNotice] = useState('')
  const [restoring, setRestoring] = useState(true)
  const [toast, setToast] = useState('')
  const [staleWeek, setStaleWeek] = useState(false)

  useEffect(() => {
    if (DEMO_MODE) { setRestoring(false); return }
    fetch('/api/meal-plan/current').then(async r => {
      if (!r.ok) return
      const data = await r.json()
      if (data.plan) setPlan(data.plan)
      if (data.preferences) { const restored = normalizePref(data.preferences); setPref(restored); setSavedPref(restored) }
      if (data.checkedItems) setChecked(new Set(data.checkedItems))
      if (data.stale) setStaleWeek(true)
    }).catch(() => {}).finally(() => setRestoring(false))
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 4200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const groups = useMemo(() => dayOrder.map(day => ({ day, meals: plan?.meals.filter(m => m.day === day) || [] })).filter(g => g.meals.length), [plan])
  const shoppingGroups = useMemo(() => ['蔬菜', '水果', '乳制品', '蛋白质', '主食', '调味及其他'].map(category => ({ category, items: plan?.shoppingList.filter(i => i.category === category) || [] })).filter(g => g.items.length), [plan])

  const toggleFlavor = (flavor: string) => setPref(p => ({ ...p, flavors: p.flavors.includes(flavor) ? p.flavors.filter(x => x !== flavor) : [...p.flavors, flavor] }))

  async function generate() {
    setLoading(true); setNotice('')
    try {
      if (DEMO_MODE) {
        await new Promise(resolve => window.setTimeout(resolve, 650))
        setPlan(buildDemoPlan(pref)); setSavedPref({ ...pref }); setStaleWeek(false); setChecked(new Set()); setTab('plan'); return
      }
      const r = await fetch('/api/meal-plan/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pref) })
      if (!r.ok) throw new Error('生成失败')
      setPlan(await r.json()); setSavedPref({ ...pref }); setStaleWeek(false); setChecked(new Set()); setTab('plan')
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
  const prefSignature = (value: Pref) => JSON.stringify({ ...value, flavors:[...value.flavors].sort(), meal_slots:[...value.meal_slots].sort(), staple_preferences:[...value.staple_preferences].sort(), meal_styles:[...value.meal_styles].sort(), equipment:[...value.equipment].sort() })
  const preferencesDirty = !!(plan && savedPref && prefSignature(pref) !== prefSignature(savedPref))
  const safetyDirty = !!(savedPref && (pref.avoid !== savedPref.avoid || pref.equipment.join('|') !== savedPref.equipment.join('|')))

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand-mark">好</div>
      <div><strong>一周好好吃</strong><span>一个人的轻松餐桌</span></div>
      {plan && <button className="icon-button" onClick={() => setTab('settings')} aria-label="偏好设置">⚙</button>}
    </header>

    <main>
      {restoring && <section className="restore-page"><span className="spinner dark"/><p>正在取回这周的餐单…</p></section>}
      {!restoring && !plan && <section className="onboarding">
        {staleWeek && <div className="week-renew"><b>新的一周到了</b><span>上周餐单已收起，你的设置已经保留。</span></div>}
        {DEMO_MODE && <div className="demo-badge">公开演示版 · 使用示例数据</div>}
        <div className="hero-art"><span className="leaf leaf-a">●</span><span className="leaf leaf-b">●</span><div className="bowl" aria-hidden="true"><svg viewBox="0 0 100 100"><path d="M18 46h64c0 24-13 38-32 38S18 70 18 46Z" fill="#fffaf0" stroke="#345c43" strokeWidth="4"/><path d="M26 45c5-9 13-14 24-14s20 5 25 14" fill="none" stroke="#dc7c43" strokeWidth="5" strokeLinecap="round"/><path d="M39 27c-3-7 4-9 1-15M57 27c-3-7 4-9 1-15" fill="none" stroke="#93ab78" strokeWidth="4" strokeLinecap="round"/><path d="M32 57h36" stroke="#d9c7a6" strokeWidth="3" strokeLinecap="round"/></svg></div></div>
        <p className="eyebrow">MEAL PLANNER</p>
        <h1>一周吃什么，<br/><em>交给我来想。</em></h1>
        <p className="hero-copy">先选这周准备自己做饭的时段，再选择一种轻松的搭配方式。第一次简单设置，以后可以直接沿用。</p>
        <PreferenceForm pref={pref} setPref={setPref} toggleFlavor={toggleFlavor} savedPref={savedPref} />
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
              <div className="meal-emoji"><FoodIcon emoji={meal.emoji} title={meal.title} size={26} /></div>
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
        <p className="eyebrow">PREFERENCES</p><h1>调整这一周</h1><p className="subcopy">可以沿用上次设置，也可以只改这一周。</p>
        <PreferenceForm pref={pref} setPref={setPref} toggleFlavor={toggleFlavor} savedPref={savedPref} />
        {preferencesDirty && <div className={`change-warning ${safetyDirty?'important':''}`}><b>{safetyDirty?'忌口或厨具已改变':'设置已经调整'}</b><span>重新生成后，新设置才会应用到餐单。</span></div>}
        {notice && <p className="notice">{notice}</p>}
        <button className="primary" onClick={generate} disabled={loading || pref.meal_slots.length === 0}>{loading ? '正在重新搭配…' : `按新偏好生成 ${pref.meal_slots.length} 顿`}</button>
      </section>}
    </main>

    {toast && <div className="toast">{toast}</div>}

    {plan && <nav className="bottom-nav"><button className={tab === 'plan' ? 'active' : ''} onClick={() => setTab('plan')}><span>▦</span>周餐单</button><button className={tab === 'list' ? 'active' : ''} onClick={() => setTab('list')}><span>✓</span>采购单</button><button className={tab === 'settings' ? 'active' : ''} onClick={() => setTab('settings')}><span>⚙</span>偏好</button></nav>}

    {selected && <div className="sheet-backdrop" onClick={() => setSelected(null)}><article className="sheet" onClick={e => e.stopPropagation()}>
      <div className="grabber"/><button className="sheet-close" onClick={() => setSelected(null)}>×</button>
      <div className="sheet-hero"><span><FoodIcon emoji={selected.emoji} title={selected.title} size={36} /></span><div><small>{selected.day} {showDate(selected.date)} · {selected.mealType} · {selected.minutes}分钟</small><h2>{selected.title}</h2></div></div>
      <p className="nutrition">搭配说明 · {selected.nutrition}</p>
      <h3 className="section-title">准备这些</h3><div className="ingredient-grid">{selected.ingredients.map(i => <div key={`${i.name}-${i.unit}`}><span>{i.name}</span><b>{fmt(i.quantity)}{i.unit}</b></div>)}</div>
      <h3 className="section-title">预计 {selected.minutes} 分钟</h3><ol className="steps">{selected.steps.map((s, i) => <li key={s}><b>{i+1}</b><span>{s}</span></li>)}</ol>
      <button className="swap-button" disabled={swapping === selected.id} onClick={() => swap(selected)}>{swapping === selected.id ? '正在想一道新的…' : '↻ 这顿换一道'}</button>
    </article></div>}
  </div>
}

function PreferenceForm({ pref, setPref, toggleFlavor, savedPref }: { pref: Pref; setPref: (p: Pref | ((p: Pref) => Pref)) => void; toggleFlavor: (s: string) => void; savedPref: Pref | null }) {
  const [advanced, setAdvanced] = useState(pref.preference_mode === 'custom')
  const toggleSlot = (slot: string) => setPref(p => {
    const exists = p.meal_slots.includes(slot)
    if (exists && p.meal_slots.length === 1) return p
    return { ...p, meal_slots: exists ? p.meal_slots.filter(x => x !== slot) : [...p.meal_slots, slot] }
  })
  const toggleList = (field: 'staple_preferences' | 'meal_styles', value: string) => setPref(p => ({ ...p, preference_mode:'custom', [field]: p[field].includes(value) ? p[field].filter(x => x !== value) : [...p[field], value] }))
  const toggleEquipment = (value: string) => setPref(p => {
    if (value === '无厨具') return { ...p, preference_mode:'custom', equipment:['无厨具'] }
    const current = p.equipment.filter(x => x !== '无厨具')
    return { ...p, preference_mode:'custom', equipment: current.includes(value) ? current.filter(x => x !== value) : [...current, value] }
  })
  const applyMode = (mode: PreferenceMode) => {
    const configs: Record<Exclude<PreferenceMode,'custom'>, Partial<Pref>> = {
      balanced:{ flavors:[], staple_preferences:[], meal_styles:[], max_minutes:30 },
      quick:{ flavors:[], staple_preferences:[], meal_styles:['一锅端'], max_minutes:15 },
      homestyle:{ flavors:[], staple_preferences:['米饭'], meal_styles:['家常菜'], max_minutes:30 },
      light:{ flavors:['清淡'], staple_preferences:['杂粮轻食'], meal_styles:['轻食'], max_minutes:20 },
    }
    if (mode === 'custom') { setAdvanced(true); setPref(p => ({...p, preference_mode:'custom'})); return }
    setPref(p => ({ ...p, ...configs[mode], preference_mode:mode })); setAdvanced(false)
  }
  return <div className="pref-card">
    {savedPref && <button type="button" className="restore-pref" onClick={() => { setPref(normalizePref(savedPref)); setAdvanced(savedPref.preference_mode === 'custom') }}><span>↻</span><div><b>沿用上次设置</b><small>{savedPref.meal_slots.length}顿 · {savedPref.max_minutes}分钟 · {savedPref.staple_preferences.join('、') || '主食合理轮换'}</small></div></button>}
    <label className="field-label meal-count-label">这周准备自己做几顿？ <strong>{pref.meal_slots.length}顿</strong></label>
    <div className="preset-row">{Object.entries(presetSlots).map(([name, slots]) => <button type="button" key={name} onClick={() => setPref(p => ({...p, meal_slots:[...slots]}))}>{name}</button>)}</div>
    <div className="meal-schedule">
      <div className="schedule-head"><span></span>{mealDefs.map(([,name]) => <b key={name}>{name}</b>)}</div>
      {dayDefs.map(([dayCode, dayName]) => <div className="schedule-row" key={dayCode}><strong>{dayName}</strong>{mealDefs.map(([mealCode, mealName]) => { const slot=`${dayCode}-${mealCode}`; const active=pref.meal_slots.includes(slot); return <button type="button" aria-label={`${dayName}${mealName}`} aria-pressed={active} className={active?'active':''} key={slot} onClick={() => toggleSlot(slot)}>{active?'✓':'+'}</button> })}</div>)}
    </div>
    <p className="schedule-tip">至少选择1顿；可自由组合一周最多21顿</p>

    <label className="field-label">想怎么吃？</label>
    <div className="mode-grid">{modeDefs.map(mode => <button type="button" key={mode.id} aria-pressed={pref.preference_mode===mode.id} className={pref.preference_mode===mode.id?'selected':''} onClick={() => applyMode(mode.id)}><b>{mode.title}</b><small>{mode.desc}</small></button>)}</div>
    <button type="button" className={`advanced-toggle ${advanced?'open':''}`} onClick={() => { setAdvanced(x => !x); if (!advanced) setPref(p => ({...p, preference_mode:'custom'})) }}><span>自定义偏好</span><i>{advanced?'收起':'展开'}⌄</i></button>

    {advanced && <div className="advanced-panel">
      <label className="mini-label">主食偏好 <span>可以多选，系统仍会适当轮换</span></label>
      <div className="chips">{stapleOptions.map(x => <button type="button" className={pref.staple_preferences.includes(x)?'selected':''} key={x} onClick={() => toggleList('staple_preferences',x)}>{x}</button>)}</div>
      <label className="mini-label">餐食风格</label>
      <div className="chips">{styleOptions.map(x => <button type="button" className={pref.meal_styles.includes(x)?'selected':''} key={x} onClick={() => toggleList('meal_styles',x)}>{x}</button>)}</div>
      <label className="mini-label">每顿最多用时</label>
      <div className="segment-row">{[10,15,30,45].map(x => <button type="button" className={pref.max_minutes===x?'selected':''} key={x} onClick={() => setPref(p => ({...p, preference_mode:'custom', max_minutes:x}))}>{x}分钟</button>)}</div>
      <label className="mini-label">可用厨具</label>
      <div className="chips">{equipmentOptions.map(x => <button type="button" className={pref.equipment.includes(x)?'selected':''} key={x} onClick={() => toggleEquipment(x)}>{x}</button>)}</div>
      <label className="mini-label">口味偏好</label>
      <div className="chips">{flavorOptions.map(f => <button type="button" className={pref.flavors.includes(f)?'selected':''} key={f} onClick={() => { toggleFlavor(f); setPref(p => ({...p, preference_mode:'custom'})) }}>{f}</button>)}</div>
    </div>}

    <label className="field-label">这周预算 <strong>¥{pref.budget}</strong></label>
    <input className="range" type="range" min="50" max="300" step="10" value={pref.budget} onChange={e => setPref(p => ({...p, budget: Number(e.target.value)}))}/>
    <div className="range-note"><span>¥50</span><span>¥300</span></div>
    <label className="field-label" htmlFor="pantry">家里还有什么？</label><input id="pantry" value={pref.pantry} onChange={e => setPref(p => ({...p, pantry: e.target.value}))} placeholder="比如：半包粉丝、2个鸡蛋"/>
    <label className="field-label" htmlFor="avoid">不吃或忌口</label><input id="avoid" value={pref.avoid} onChange={e => setPref(p => ({...p, avoid: e.target.value}))} placeholder="没有可以留空"/>
  </div>
}
