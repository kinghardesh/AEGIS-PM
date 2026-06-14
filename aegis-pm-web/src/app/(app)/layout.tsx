import { Sidebar } from "@/components/app-shell/sidebar";
import { Topbar } from "@/components/app-shell/topbar";
import { CommandPalette } from "@/components/ui/command-palette";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen bg-background overflow-hidden">
      <div className="absolute top-0 right-0 -z-10 h-[600px] w-[600px] rounded-full bg-primary/5 blur-[140px] pointer-events-none dark:bg-primary/10" />
      <div className="absolute bottom-0 left-[240px] -z-10 h-[600px] w-[600px] rounded-full bg-violet-500/5 blur-[140px] pointer-events-none dark:bg-violet-500/10" />
      <Sidebar />
      <CommandPalette />
      <div className="pl-[240px] transition-[padding] duration-200 ease-out relative z-10">
        <Topbar />
        <main className="px-8 py-8">{children}</main>
      </div>
    </div>
  );
}
