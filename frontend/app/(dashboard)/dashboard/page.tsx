"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, Plus, FolderOpen, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchPapers, fetchProjects } from "@/lib/api-client";


type Paper = {
  id: string;
  title: string;
  projectName?: string;
  created_at?: string;
  updated_at?: string;
};

export default function DashboardPage() {
  const [stats, setStats] = useState({
    totalPapers: 0,
    activeProjects: 0,
    generations: 0,
  });
  const [recentPapers, setRecentPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const loadDashboardData = async () => {
      try {
        const [papers, projects] = await Promise.all([
          fetchPapers<Paper[]>({ timeoutMs: 30000 }),
          fetchProjects<any[]>({ timeoutMs: 30000 }),
        ]);

        if (active) {
          setStats({
            totalPapers: papers?.length || 0,
            activeProjects: projects?.length || 0,
            generations: (projects?.length || 0) + (papers?.length || 0),
          });
          setRecentPapers((papers || []).slice(0, 3));
        }
      } catch (err) {
        console.error("Failed to load dashboard statistics:", err);
      } finally {
        if (active) setLoading(false);
      }
    };

    loadDashboardData();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="p-8 space-y-10 max-w-7xl mx-auto">
      {/* Quick Start Actions */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Quick Start</h3>
        <div className="grid gap-6 md:grid-cols-2">
          {/* Create New Paper card */}
          <Link
            href="/editor?new=true"
            className="group relative block overflow-hidden rounded-xl border border-indigo-200 dark:border-indigo-900/60 bg-gradient-to-br from-indigo-50/50 to-white dark:from-indigo-950/20 dark:to-zinc-950 p-6 shadow-sm hover:shadow-md transition-all duration-300 hover:border-indigo-400 dark:hover:border-indigo-500"
          >
            <div className="flex items-start justify-between">
              <div className="p-3 rounded-lg bg-indigo-600 text-white shadow-md shadow-indigo-600/20 group-hover:scale-110 transition-transform">
                <Plus className="h-6 w-6" />
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground group-hover:text-indigo-600 group-hover:translate-x-1 transition-all" />
            </div>
            <div className="mt-6 space-y-2">
              <h4 className="text-xl font-bold text-foreground">Create New Exam Paper</h4>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Initialize a blank paper from standard formats (CBSE, ICSE, custom templates), detach autosaves, and start fresh.
              </p>
            </div>
          </Link>

          {/* Open Saved Paper card */}
          <Link
            href="/question-bank"
            className="group relative block overflow-hidden rounded-xl border border-amber-200 dark:border-amber-900/60 bg-gradient-to-br from-amber-50/30 to-white dark:from-amber-950/10 dark:to-zinc-950 p-6 shadow-sm hover:shadow-md transition-all duration-300 hover:border-amber-400 dark:hover:border-amber-500"
          >
            <div className="flex items-start justify-between">
              <div className="p-3 rounded-lg bg-amber-500 text-white shadow-md shadow-amber-500/20 group-hover:scale-110 transition-transform">
                <FolderOpen className="h-6 w-6" />
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground group-hover:text-amber-500 group-hover:translate-x-1 transition-all" />
            </div>
            <div className="mt-6 space-y-2">
              <h4 className="text-xl font-bold text-foreground">Browse Saved Papers</h4>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Access your paper library, safely reopen previous sessions, edit existing documents, or manage your question bank.
              </p>
            </div>
          </Link>
        </div>
      </div>

      {/* Metrics & Performance */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Overview & Stats</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="bg-card border-border/80 relative overflow-hidden group hover:border-indigo-500/30 transition-all duration-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Total Papers</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="h-8 w-12 bg-muted animate-pulse rounded" />
              ) : (
                <div className="text-3xl font-extrabold text-foreground tracking-tight">{stats.totalPapers}</div>
              )}
              <p className="text-xs text-muted-foreground mt-1">Successfully compiled & saved</p>
            </CardContent>
          </Card>

          <Card className="bg-card border-border/80 relative overflow-hidden group hover:border-indigo-500/30 transition-all duration-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Active Projects</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="h-8 w-12 bg-muted animate-pulse rounded" />
              ) : (
                <div className="text-3xl font-extrabold text-foreground tracking-tight">{stats.activeProjects}</div>
              )}
              <p className="text-xs text-muted-foreground mt-1">Temporary AI context stores</p>
            </CardContent>
          </Card>

          <Card className="bg-card border-border/80 relative overflow-hidden group hover:border-indigo-500/30 transition-all duration-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Generations</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="h-8 w-12 bg-muted animate-pulse rounded" />
              ) : (
                <div className="text-3xl font-extrabold text-foreground tracking-tight">{stats.generations}</div>
              )}
              <p className="text-xs text-muted-foreground mt-1">RAG optimizations processed</p>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Recent Papers */}
      {!loading && recentPapers.length > 0 && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Recent Papers</h3>
            <Link href="/question-bank" className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
              View All
            </Link>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {recentPapers.map((paper) => {
              const parts = (paper.projectName || "").split(" — ");
              const className = parts[0]?.trim() || "Class —";
              const subjectName = parts[1]?.trim() || "Subject —";
              
              return (
                <Link
                  key={paper.id}
                  href={`/editor?paperId=${paper.id}`}
                  className="block bg-card hover:bg-muted/30 border border-border/80 rounded-xl p-5 hover:border-indigo-500/30 hover:shadow-sm transition-all duration-300 space-y-3"
                >
                  <div className="p-2 rounded-lg bg-indigo-500/10 w-fit">
                    <FileText className="h-4 w-4 text-indigo-500" />
                  </div>
                  <div className="space-y-1">
                    <h4 className="font-bold text-foreground text-sm line-clamp-1">{paper.title}</h4>
                    <p className="text-xs text-muted-foreground">
                      {className} · {subjectName}
                    </p>
                  </div>
                  <div className="text-[10px] text-indigo-500 font-semibold group-hover:underline">
                    Edit Paper →
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
