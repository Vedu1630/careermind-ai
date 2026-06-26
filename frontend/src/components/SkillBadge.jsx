import { clsx } from 'clsx'

const VARIANTS = {
  matched: 'bg-[#E8E4FF] text-[#6B5CE7]',
  missing: 'bg-[#FEF3C7] text-[#D97706]',
  gap: 'bg-[#FEF3C7] text-[#D97706]',
  neutral: 'bg-[#E8E4FF] text-[#6B5CE7]',
  accent: 'bg-[#E8E4FF] text-[#6B5CE7]',
  keyword: 'bg-[#E8E4FF] text-[#6B5CE7]',
  added: 'bg-[#DCFCE7] text-[#16A34A]',
  removed: 'bg-[#FEE2E2] text-[#DC2626]',
}

const ICONS = {
  matched: '✓',
  missing: '△',
  gap: '△',
  added: '+',
  removed: '−',
}

export default function SkillBadge({ skill, variant = 'neutral', className }) {
  const variantClass = VARIANTS[variant] || VARIANTS.neutral
  const icon = ICONS[variant]

  return (
    <span className={clsx(
      'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all duration-150 hover:scale-105',
      variantClass,
      className
    )}>
      {icon && <span className="text-xs leading-none">{icon}</span>}
      {skill}
    </span>
  )
}
