import { Sidebar } from "@/components/app-shell/sidebar";
import { Topbar } from "@/components/app-shell/topbar";
import { CommandPalette } from "@/components/ui/command-palette";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <CommandPalette />
      <div className="pl-[240px] transition-[padding] duration-200 ease-out">
        <Topbar />
        <main className="px-8 py-8">{children}</main>
      </div>
    </div>
  );
}
