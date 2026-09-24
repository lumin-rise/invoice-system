export interface Invoice {
  id: string
  filename: string
  file_type: string            // pdf / ofd / image / manual
  stored_name: string | null
  thumb_name: string | null
  invoice_no: string
  title: string
  date: string                 // yyyy-mm-dd
  time: string                 // HH:MM
  amount: number | null
  tax: number | null
  seller: string
  category: 'travel' | 'other'
  item: string
  location: string
  hkd: string
  no_bill: boolean
  note: string
  source: string               // upload / manual
  parse_ok: boolean
  parse_msg: string
  raw_text: string
  created_at: number
}

export const fmtAmount = (v: number | null): string =>
  v === null || v === undefined ? '' : v.toFixed(2)

export const thumbUrl = (inv: Invoice): string | null =>
  inv.thumb_name ? `/api/files/thumbs/${inv.thumb_name}` : null

export const fileUrl = (inv: Invoice): string | null =>
  inv.stored_name ? `/api/files/uploads/${inv.stored_name}` : null

/** 与后端 sorted_invoices 完全一致的排序 */
export const sortKey = (i: Invoice): [string, number] => [
  i.date ? `${i.date} ${i.time || '00:00'}` : '9999-12-31 23:59',
  i.created_at,
]

export const sorted = (list: Invoice[]): Invoice[] =>
  [...list].sort((a, b) => {
    const ka = sortKey(a); const kb = sortKey(b)
    return ka[0] < kb[0] ? -1 : ka[0] > kb[0] ? 1 : ka[1] - kb[1]
  })

/** 有图、占编号的发票（Bills 模块），编号 = 时间顺序 1#、2#… */
export const billNumbered = (list: Invoice[]): Invoice[] =>
  sorted(list).filter(i => !i.no_bill && i.stored_name)

/** 某张发票在 Bills 里的编号（1 起），无编号返回 null */
export const billNoOf = (list: Invoice[], inv: Invoice): number | null => {
  const bills = billNumbered(list)
  const idx = bills.findIndex(i => i.id === inv.id)
  return idx === -1 ? null : idx + 1
}
