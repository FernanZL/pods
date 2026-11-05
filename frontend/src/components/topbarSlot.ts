import { createContext, useContext } from 'react'

/** The app shell's top-bar slot element, where a page can portal its own actions. */
export const TopbarSlotContext = createContext<HTMLElement | null>(null)

export function useTopbarSlot(): HTMLElement | null {
  return useContext(TopbarSlotContext)
}
