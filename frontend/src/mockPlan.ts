type Ingredient = { name: string; quantity: number; unit: string; category: string }
type Meal = { id: string; day: string; date: string; mealType: string; title: string; emoji: string; minutes: number; tags: string[]; nutrition: string; ingredients: Ingredient[]; steps: string[] }
type Shop = Ingredient & { meals: string[] }

const ing = (name: string, quantity: number, unit: string, category: string): Ingredient => ({ name, quantity, unit, category })
const meals: Meal[] = [
  { id:'mon-d',day:'周一',date:'2026-09-07',mealType:'晚餐',title:'番茄青菜嫩豆腐面',emoji:'🍅',minutes:15,tags:['优先吃绿叶菜','清淡'],nutrition:'主食、植物蛋白和深色蔬菜搭配完整',ingredients:[ing('番茄',1,'个','蔬菜'),ing('小青菜',150,'克','蔬菜'),ing('嫩豆腐',120,'克','蛋白质'),ing('挂面',100,'克','主食')],steps:['番茄切块，青菜洗净，豆腐切小块','番茄炒软后加一碗水，放豆腐煮开','下面条，最后放青菜和少许盐调味']},
  { id:'tue-d',day:'周二',date:'2026-09-08',mealType:'晚餐',title:'酸辣娃娃菜虾滑土豆粉',emoji:'🥬',minutes:15,tags:['酸辣','高蛋白'],nutrition:'虾滑补充蛋白质，娃娃菜增加蔬菜摄入',ingredients:[ing('娃娃菜',180,'克','蔬菜'),ing('虾滑',100,'克','蛋白质'),ing('土豆粉',1,'包','主食'),ing('酸汤底',1,'份','调味及其他')],steps:['娃娃菜切段，土豆粉冲洗备用','水开后挤入虾滑，煮至浮起','放土豆粉和娃娃菜，加入酸汤底煮熟']},
  { id:'wed-d',day:'周三',date:'2026-09-09',mealType:'晚餐',title:'菠菜菌菇鸡蛋粉丝汤',emoji:'🍄',minutes:15,tags:['清库存','暖胃'],nutrition:'菌菇和菠菜补充纤维，鸡蛋补充蛋白质',ingredients:[ing('菠菜',150,'克','蔬菜'),ing('鲜香菇',100,'克','蔬菜'),ing('鸡蛋',1,'个','蛋白质'),ing('粉丝',1,'把','主食')],steps:['粉丝泡软，菠菜和香菇洗净','香菇加水煮5分钟，再放粉丝','淋入蛋液，最后放菠菜调味']},
  { id:'thu-d',day:'周四',date:'2026-09-10',mealType:'晚餐',title:'番茄豆腐荞麦面',emoji:'🍜',minutes:15,tags:['低负担','复用番茄'],nutrition:'豆腐提供植物蛋白，荞麦面更耐饱',ingredients:[ing('番茄',1,'个','蔬菜'),ing('嫩豆腐',120,'克','蛋白质'),ing('荞麦面',100,'克','主食'),ing('紫菜',5,'克','蔬菜')],steps:['番茄和豆腐切块','番茄炒软后加水，放豆腐煮开','下荞麦面煮熟，撒紫菜调味']},
  { id:'fri-d',day:'周五',date:'2026-09-11',mealType:'晚餐',title:'西兰花鸡胸肉拌面',emoji:'🥦',minutes:15,tags:['少油','高蛋白'],nutrition:'鸡胸肉提供优质蛋白，西兰花耐储且高纤维',ingredients:[ing('西兰花',180,'克','蔬菜'),ing('鸡胸肉',100,'克','蛋白质'),ing('挂面',100,'克','主食'),ing('生抽',1,'份','调味及其他')],steps:['鸡胸肉切薄片，西兰花切小朵','面条和西兰花煮熟捞出，鸡肉煎熟','加入生抽和少许醋，拌匀即可']},
  { id:'sat-l',day:'周六',date:'2026-09-12',mealType:'午餐',title:'胡萝卜玉米鸡肉汤面',emoji:'🥕',minutes:15,tags:['周末快手','耐储食材'],nutrition:'鸡肉、玉米和胡萝卜组合均衡',ingredients:[ing('胡萝卜',100,'克','蔬菜'),ing('冷冻玉米',80,'克','蔬菜'),ing('鸡胸肉',100,'克','蛋白质'),ing('荞麦面',100,'克','主食')],steps:['胡萝卜切丝，鸡肉切薄片','锅中加水，放胡萝卜、玉米和鸡肉煮熟','下荞麦面，煮熟后调味']},
  { id:'sat-d',day:'周六',date:'2026-09-12',mealType:'晚餐',title:'金针菇酸汤肥牛土豆粉',emoji:'🥘',minutes:15,tags:['酸汤','满足感'],nutrition:'肥牛补充蛋白质和铁，菌菇增加纤维',ingredients:[ing('金针菇',120,'克','蔬菜'),ing('番茄',1,'个','蔬菜'),ing('肥牛卷',120,'克','蛋白质'),ing('土豆粉',1,'包','主食')],steps:['肥牛焯水，金针菇去根','番茄炒软后加水煮开','下金针菇、土豆粉和肥牛，调成酸汤口']},
  { id:'sun-l',day:'周日',date:'2026-09-13',mealType:'午餐',title:'香菇胡萝卜鸡蛋炒面',emoji:'🍳',minutes:15,tags:['耐储食材','快炒'],nutrition:'耐储蔬菜搭配鸡蛋，适合周末收尾',ingredients:[ing('鲜香菇',100,'克','蔬菜'),ing('胡萝卜',100,'克','蔬菜'),ing('鸡蛋',1,'个','蛋白质'),ing('挂面',100,'克','主食')],steps:['面条煮至八成熟，香菇胡萝卜切丝','鸡蛋炒散盛出，再炒软蔬菜','放面条和鸡蛋，加生抽快速翻匀']},
  { id:'sun-d',day:'周日',date:'2026-09-13',mealType:'晚餐',title:'紫菜番茄豆腐粉丝汤',emoji:'🌿',minutes:12,tags:['清淡收尾','零浪费'],nutrition:'用耐储食材完成一周收尾，晚餐轻负担',ingredients:[ing('紫菜',5,'克','蔬菜'),ing('番茄',1,'个','蔬菜'),ing('嫩豆腐',120,'克','蛋白质'),ing('粉丝',1,'把','主食')],steps:['粉丝泡软，番茄和豆腐切块','番茄煮出汤后放豆腐和粉丝','最后撒紫菜，滴少许香油']},
]

function shopping(list: Meal[]): Shop[] {
  const map = new Map<string, Shop>()
  list.forEach(meal => meal.ingredients.forEach(item => {
    const key = `${item.category}-${item.name}-${item.unit}`
    const old = map.get(key)
    if (old) { old.quantity += item.quantity; if (!old.meals.includes(meal.id)) old.meals.push(meal.id) }
    else map.set(key, { ...item, meals:[meal.id] })
  }))
  return [...map.values()]
}

export const mockPlan = {
  summary:'先吃绿叶菜，再用耐储食材收尾；9顿尽量复用原料，一个人也不浪费。',
  weekStart:'2026-09-07',estimatedCostMin:78,estimatedCostMax:96,budgetWarning:false,
  meals,shoppingList:shopping(meals),pantryUsed:['粉丝 2把','鸡蛋 2个'],
  tips:['绿叶菜集中在周一至周三，洗净沥干后用厨房纸包好冷藏','蛋白质按单顿分装冷冻，前一晚移到冷藏解冻','周五后优先使用胡萝卜、紫菜、菌菇和冷冻食材'],lastShoppingDelta:null,
}

export function demoSwap(plan: any, mealId: string) {
  const next = JSON.parse(JSON.stringify(plan))
  const target = next.meals.find((m: Meal) => m.id === mealId)
  const before = next.shoppingList as Shop[]
  if (!target) return next
  const oldTitle = target.title
  target.title = '番茄金针菇豆腐荞麦面'
  target.emoji = '🍲'
  target.tags = ['复用库存','清爽鲜香']
  target.nutrition = '菌菇和豆腐提供纤维与植物蛋白'
  target.ingredients = [ing('番茄',1,'个','蔬菜'),ing('金针菇',100,'克','蔬菜'),ing('嫩豆腐',120,'克','蛋白质'),ing('荞麦面',100,'克','主食')]
  target.steps = ['番茄切块，金针菇去根，豆腐切块','番茄炒软后加水，放豆腐和金针菇','下荞麦面煮熟，少量盐调味']
  next.shoppingList = shopping(next.meals)
  const oldNames = new Set(before.map(x => x.name)), newNames = new Set(next.shoppingList.map((x: Shop) => x.name))
  next.lastShoppingDelta = { added:[...newNames].filter(x => !oldNames.has(x)).map(x => `${x} +1份`), removed:[...oldNames].filter(x => !newNames.has(x)).map(x => `${x} -1份`) }
  next.summary = `已将「${oldTitle}」换成更适合现有库存的快手餐。`
  return next
}
