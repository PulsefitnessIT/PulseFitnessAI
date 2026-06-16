import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

/*
 * Shadcn Button — re-skinned to match BOTH brand systems.
 * The default variant uses `--color-brand-cyan` which the global brand-attr
 * sync (App.js) overrides per route:
 *   • data-brand="pulse"   → #19CDFF (Pulse cyan, legacy)
 *   • data-brand="gymaxis" → #2563EB (Pulse Fitness blue, premium SaaS)
 * That single CSS variable swap is what stops Pulse cyan leaking into the
 * Pulse Fitness portal. Never reintroduce the hardcoded #19CDFF hex here.
 */
const buttonVariants = cva(
 "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-[13px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
 {
 variants: {
 variant: {
 default:
 "bg-[var(--color-brand-cyan)] text-white hover:bg-[var(--color-brand-cyan-hover)]",
 destructive:
 "bg-red-500 text-white hover:bg-red-600",
 outline:
 "border border-[color:var(--theme-border)] bg-transparent text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface)]",
 secondary:
 "bg-[color:var(--theme-surface)] text-[color:var(--theme-text)] border border-[color:var(--theme-border)] hover:bg-[color:var(--theme-surface)]/80",
 ghost: "text-[color:var(--theme-text-muted)] hover:bg-[color:var(--theme-surface)] hover:text-[color:var(--theme-text)]",
 link: "text-[var(--color-brand-cyan)] underline-offset-4 hover:underline rounded-none",
 },
 size: {
 default: "h-9 px-3.5",
 sm: "h-8 px-3 text-xs",
 lg: "h-10 px-6",
 icon: "h-9 w-9",
 },
 },
 defaultVariants: {
 variant: "default",
 size: "default",
 },
 }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
 const Comp = asChild ? Slot : "button"
 return (
 <Comp
 className={cn(buttonVariants({ variant, size, className }))}
 ref={ref}
 {...props} />
 );
})
Button.displayName = "Button"

export { Button, buttonVariants }
