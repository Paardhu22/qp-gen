import { ThemeToggle } from "@/components/ui/curtain-theme-toggle";

export default function Demo() {
  return (
    <div className="flex flex-col items-center justify-center w-full min-h-[400px] gap-4">
       <p className="text-sm opacity-60">Click the button to see the animation.</p>
       
       <div className="bg-white dark:bg-black p-4 rounded-2xl shadow-xl border border-black/5 dark:border-white/10">
          <ThemeToggle variant="icon" defaultTheme="light" duration={600} />
       </div>
    </div>
  );
}
