import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

import graphical from "../../graphical/generated/tailwind-merge.cjs"

/** Graphical's text styles, weights, corners and strokes are told apart as Tailwind's are. */
const merge = extendTailwindMerge(graphical)

/** Class names joined, a later utility winning over an earlier one of its kind. */
export function cn(...inputs: ClassValue[]) {
  return merge(clsx(inputs))
}
