import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, FolderOpen, Activity } from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="p-8 space-y-8">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-white">Dashboard</h2>
        <p className="text-zinc-400 mt-2">Welcome to Paper Gen. Create and manage your exam papers here.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="bg-zinc-950 border-zinc-800">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-zinc-200">Total Papers</CardTitle>
            <FileText className="h-4 w-4 text-zinc-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-white">0</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-950 border-zinc-800">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-zinc-200">Active Projects</CardTitle>
            <FolderOpen className="h-4 w-4 text-zinc-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-white">0</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-950 border-zinc-800">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-zinc-200">Generations</CardTitle>
            <Activity className="h-4 w-4 text-zinc-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-white">0</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
