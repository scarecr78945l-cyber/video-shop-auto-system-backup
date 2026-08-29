import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** className 合并工具（clsx + tailwind-merge，覆盖冲突类）。 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
