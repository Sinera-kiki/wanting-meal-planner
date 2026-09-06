import React from 'react'

type Props = {
  emoji?: string
  title?: string
  size?: number
  className?: string
}

export function FoodIcon({ emoji = '🍲', title = '', size = 26, className = '' }: Props) {
  const text = `${emoji} ${title}`
  // Rice / 盖饭 / 炒饭 / 饭
  if (text.includes('🍚') || /盖饭|炒饭|拌饭|焖饭|米饭|汤饭/.test(text)) {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
        <path d="M6 16c0 6.627 4.477 11 10 11s10-4.373 10-11H6Z" fill="#F4EFE3" stroke="#345C43" strokeWidth="2" strokeLinejoin="round"/>
        <path d="M8 16c0-4.418 3.582-7 8-7s8 2.582 8 7H8Z" fill="#FFFDF8" stroke="#345C43" strokeWidth="2"/>
        <path d="M12 11c1-1 2.5-1.5 4-1.5s3 .5 4 1.5" stroke="#E58A4C" strokeWidth="2" strokeLinecap="round"/>
        <circle cx="16" cy="13" r="1.5" fill="#52775D"/>
        <circle cx="13" cy="14" r="1" fill="#DC7C43"/>
        <circle cx="19" cy="14" r="1" fill="#7C9A72"/>
      </svg>
    )
  }
  // Salad / 轻食 / 杂粮碗 / 卷
  if (text.includes('🥗') || text.includes('🌯') || /轻食|沙拉|全麦卷|杂粮碗|藜麦/.test(text)) {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
        <path d="M5 16c0 6.627 4.925 11 11 11s11-4.373 11-11H5Z" fill="#EBF2E6" stroke="#345C43" strokeWidth="2" strokeLinejoin="round"/>
        <path d="M11 12c-2-3 1-5 4-3 1-3 5-2 4 2 3-1 4 3 1 4" fill="#84A876" stroke="#345C43" strokeWidth="1.5"/>
        <circle cx="18" cy="14" r="2" fill="#E26D5C"/>
        <circle cx="14" cy="15" r="1.5" fill="#E58A4C"/>
        <path d="M15 10c0-2 2-3 3-2" stroke="#486D53" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    )
  }
  // Breakfast / 燕麦 / 吐司 / 阳光
  if (text.includes('☀️') || /早餐|燕麦|酸奶|吐司|豆浆|粥/.test(text)) {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
        <rect x="7" y="9" width="18" height="17" rx="5" fill="#FFFDF8" stroke="#345C43" strokeWidth="2"/>
        <circle cx="16" cy="17.5" r="4.5" fill="#E58A4C"/>
        <circle cx="16" cy="17.5" r="2.5" fill="#F4B266"/>
        <path d="M12 6l1 2M16 5v2M20 6l-1 2" stroke="#E58A4C" strokeWidth="2" strokeLinecap="round"/>
      </svg>
    )
  }
  // Noodles / 粉 / 面 / 土豆粉 / 乌冬 / 米线
  if (text.includes('🍜') || /面|粉|米线|乌冬|粉丝/.test(text)) {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
        <path d="M6 15c0 6.627 4.477 11 10 11s10-4.373 10-11H6Z" fill="#F6F1E5" stroke="#345C43" strokeWidth="2" strokeLinejoin="round"/>
        <path d="M8 15c0-2 2-4 5-4s5 2 7 2 4-2 4-2" stroke="#E58A4C" strokeWidth="2.5" strokeLinecap="round"/>
        <path d="M11 9c1 2 0 4-1 6M16 8c1 2 0 4-1 7M21 9c1 2 0 4-1 6" stroke="#F4B266" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M13 5l12-2" stroke="#7C9A72" strokeWidth="2" strokeLinecap="round"/>
      </svg>
    )
  }
  // Hot pot / 汤 / 煲 / 默认
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <path d="M5 14c0 7 4.925 12 11 12s11-5 11-12H5Z" fill="#F4EFE3" stroke="#345C43" strokeWidth="2" strokeLinejoin="round"/>
      <path d="M3 14h26" stroke="#345C43" strokeWidth="2" strokeLinecap="round"/>
      <path d="M11 9c0-2 2-3 2-5M16 8c0-2 2-3 2-5M21 9c0-2 2-3 2-5" stroke="#E58A4C" strokeWidth="2" strokeLinecap="round"/>
      <circle cx="12" cy="18" r="2" fill="#E26D5C"/>
      <circle cx="17" cy="19" r="2" fill="#7C9A72"/>
      <circle cx="21" cy="17" r="1.5" fill="#E58A4C"/>
    </svg>
  )
}
