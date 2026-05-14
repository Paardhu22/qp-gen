import * as React from "react"
import { Field as FieldPrimitive } from "@base-ui/react/field"

import { cn } from "@/lib/utils"

/** Wraps an individual label + input pair */
function Field({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <FieldPrimitive.Root
      data-slot="field"
      className={cn("flex flex-col gap-1.5", className)}
      {...props}
    />
  )
}

/** Groups multiple Field components with consistent vertical spacing */
function FieldGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="field-group"
      className={cn("flex flex-col gap-4", className)}
      {...props}
    />
  )
}

/** Label for a Field — wired to the Field context for accessibility */
function FieldLabel({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <FieldPrimitive.Label
      data-slot="field-label"
      className={cn(
        "text-sm font-medium leading-none text-foreground select-none",
        className
      )}
      {...props}
    />
  )
}

/** Helper / description text rendered below a Field */
function FieldDescription({
  className,
  ...props
}: React.ComponentProps<"p">) {
  return (
    <FieldPrimitive.Description
      data-slot="field-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

/** Inline validation error for a Field */
function FieldError({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <FieldPrimitive.Error
      data-slot="field-error"
      className={cn("text-sm font-medium text-destructive", className)}
      {...props}
    />
  )
}

export { Field, FieldGroup, FieldLabel, FieldDescription, FieldError }
