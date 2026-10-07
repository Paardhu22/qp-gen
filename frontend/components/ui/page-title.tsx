import { cn } from "@/lib/utils";

interface PageTitleProps extends React.ComponentProps<"h1"> {
  as?: "h1" | "h2";
}

export function PageTitle({ as: Tag = "h1", className, children, ...props }: PageTitleProps) {
  return (
    <Tag
      className={cn(
        "font-heading text-xl font-semibold leading-tight tracking-[-0.04em] text-foreground sm:text-2xl",
        Tag === "h2" && "text-lg tracking-[-0.025em] sm:text-lg",
        className,
      )}
      {...props}
    >
      {children}{Tag === "h1" && <span aria-hidden="true" className="text-primary">.</span>}
    </Tag>
  );
}
