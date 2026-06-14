"use client";

import * as React from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield,
  ArrowRight,
  Sparkles,
  Cpu,
  Zap,
  CheckCircle2,
  BarChart3,
  Activity,
  Plus,
  Play,
  Check,
  ExternalLink,
  Lock,
  GitBranch,
  MessageSquare,
  Calendar,
  Layers,
  ChevronRight,
  TrendingUp,
  Flame,
  Users
} from "lucide-react";
import { ThreeBg } from "@/components/ui/three-bg";
import { Accordion } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";

export default function LandingPage() {
  const [billingPeriod, setBillingPeriod] = React.useState<"monthly" | "yearly">("monthly");
  const [activeTab, setActiveTab] = React.useState<"prd" | "balancer" | "metrics">("prd");
  const [balancerDemoStep, setBalancerDemoStep] = React.useState(0);

  // Auto-cycle the balancer demo animation steps
  React.useEffect(() => {
    const timer = setInterval(() => {
      setBalancerDemoStep((prev) => (prev + 1) % 3);
    }, 4500);
    return () => clearInterval(timer);
  }, []);

  const faqItems = [
    {
      id: "faq-1",
      title: "How does the AI Balancer allocate tasks?",
      content: "Aegis evaluates incoming task descriptions or PRD requirements, extracts the requested skills (e.g., 'React', 'Database schema design'), and checks your team members' active workloads, historical speeds, and capability matches. It recommends the optimal human developer or AI worker for each task to avoid bottlenecking."
    },
    {
      id: "faq-2",
      title: "Can I customize the skill profiles of my human and AI engineers?",
      content: "Absolutely. Under the Team settings, admins can configure active tags, roles, and expertise levels. AI workers can be provisioned with specific API bindings and credentials to execute tasks in codebases automatically."
    },
    {
      id: "faq-3",
      title: "Is my source code and PRD content secure?",
      content: "Security is built into Aegis PM's architecture. Your data is isolated in your local PostgreSQL database, and external connections utilize TLS encryption. We support self-hosting options and local LLM fine-tuning to keep intellectual property completely inside your secure firewall."
    },
    {
      id: "faq-4",
      title: "How long does it take to integrate Aegis with Jira or GitHub?",
      content: "Under two minutes. Aegis connects via OAuth 2.0. Once authorized, it syncs tasks, issues, and PRD documents instantly, keeping your existing boards up to date while driving backend task dispatching automatically."
    },
    {
      id: "faq-5",
      title: "What is the difference between Pro and Enterprise tiers?",
      content: "The Pro tier supports standard automated task balancing, unlimited projects, and 5 AI workers. Enterprise offers customizable AI agents with write access to repositories, SSO/SAML integration, dedicated LLM compute nodes, and unlimited AI team capacity."
    }
  ];

  const blogPosts = [
    {
      title: "The Future of Sprint Planning: Co-existing with AI Workers",
      category: "Engineering Management",
      date: "June 12, 2026",
      desc: "How mixed squads of human developers and autonomous AI agents are increasing sprint velocities by 40% globally.",
      link: "#"
    },
    {
      title: "Eliminating Engineering Bottlenecks: Dynamic Capacity Balancers",
      category: "Operations",
      date: "June 08, 2026",
      desc: "Why manual sprint loading fails under scale, and how intelligent capacity metrics route tasks dynamically.",
      link: "#"
    },
    {
      title: "Decomposing Complex PRDs: LLM Parsing Best Practices",
      category: "AI & LLMs",
      date: "May 28, 2026",
      desc: "A deep dive into how Aegis's semantic parser splits monolithic feature requests into distinct code changes.",
      link: "#"
    }
  ];

  return (
    <div className="dark bg-[#030712] text-foreground min-h-screen overflow-x-hidden relative font-sans">
      
      {/* ── Background Blobs & Grid ── */}
      <div className="absolute top-0 right-0 -z-20 h-[800px] w-[800px] rounded-full bg-primary/5 blur-[160px] pointer-events-none" />
      <div className="absolute top-[1200px] left-[-200px] -z-20 h-[800px] w-[800px] rounded-full bg-violet-500/5 blur-[160px] pointer-events-none" />
      <div className="absolute top-[2800px] right-[-100px] -z-20 h-[900px] w-[900px] rounded-full bg-blue-500/5 blur-[160px] pointer-events-none" />
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f293708_1px,transparent_1px),linear-gradient(to_bottom,#1f293708_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] pointer-events-none -z-20" />

      {/* ── Frozen Glass Header Nav ── */}
      <header className="sticky top-0 z-50 w-full border-b border-border/20 bg-[#030712]/70 backdrop-blur-md px-6 py-3.5 transition-all duration-200">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground shadow-[0_0_20px_rgba(99,102,241,0.3)] transition-transform duration-300 group-hover:scale-105">
              <Shield className="size-5" />
            </div>
            <span className="text-base font-bold tracking-tight bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
              Aegis PM
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-muted-foreground">
            <a href="#features" className="hover:text-foreground transition-colors">Features</a>
            <a href="#integrations" className="hover:text-foreground transition-colors">Integrations</a>
            <a href="#pricing" className="hover:text-foreground transition-colors">Pricing</a>
            <a href="#faqs" className="hover:text-foreground transition-colors">FAQs</a>
            <a href="#blog" className="hover:text-foreground transition-colors">Blog</a>
          </nav>

          <div className="flex items-center gap-3">
            <Link href="/dashboard">
              <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground">
                Sign in
              </Button>
            </Link>
            <Link href="/dashboard">
              <Button size="sm" className="bg-primary hover:bg-primary/90 text-white font-medium shadow-[0_0_20px_rgba(99,102,241,0.25)] hover:shadow-[0_0_25px_rgba(99,102,241,0.4)] transition-all">
                Get started
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* ── HERO SECTION ── */}
      <section className="relative pt-20 pb-28 px-6 overflow-hidden">
        {/* Three.js Particle layer constrained to Hero */}
        <div className="absolute inset-0 -z-10 w-full h-full pointer-events-none opacity-80">
          <ThreeBg />
        </div>

        <div className="max-w-5xl mx-auto text-center relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold mb-6 shadow-[0_0_15px_rgba(99,102,241,0.1)]"
          >
            <Sparkles className="size-3.5" />
            <span>Introducing Aegis Balancer 2.0</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight mb-6 leading-[1.1] max-w-4xl mx-auto"
          >
            From <span className="bg-gradient-to-r from-violet-400 via-indigo-400 to-blue-400 bg-clip-text text-transparent">PRD to Assigned Tasks</span> in under 60 seconds
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="text-base sm:text-lg md:text-xl text-muted-foreground/90 max-w-2xl mx-auto mb-10 leading-relaxed"
          >
            Aegis automatically decomposes product requirements, generates structured tasks, and intelligently balances capacity across both human and autonomous AI engineers.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-20"
          >
            <Link href="/dashboard">
              <Button size="lg" className="w-full sm:w-auto bg-primary hover:bg-primary/90 text-white font-semibold text-base px-8 h-12 shadow-[0_0_25px_rgba(99,102,241,0.3)] hover:scale-[1.02] active:scale-95 transition-all">
                Get Started Free
                <ArrowRight className="ml-2 size-4" />
              </Button>
            </Link>
            <a href="#features">
              <Button variant="outline" size="lg" className="w-full sm:w-auto border-border/40 hover:bg-accent/10 text-muted-foreground hover:text-foreground text-base px-8 h-12">
                Learn Features
              </Button>
            </a>
          </motion.div>

          {/* Interactive Mock Dashboard */}
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.4 }}
            className="w-full max-w-4xl mx-auto rounded-2xl border border-border/30 bg-card/40 backdrop-blur-md p-2 shadow-2xl overflow-hidden"
          >
            <div className="rounded-xl border border-border/20 bg-[#070b19]/90 overflow-hidden">
              {/* Fake UI Header */}
              <div className="flex items-center justify-between border-b border-border/20 px-4 py-3 bg-[#0d1228]/50">
                <div className="flex items-center gap-1.5">
                  <div className="size-2.5 rounded-full bg-red-500/80" />
                  <div className="size-2.5 rounded-full bg-yellow-500/80" />
                  <div className="size-2.5 rounded-full bg-green-500/80" />
                </div>
                <div className="text-[11px] font-mono tracking-wider text-muted-foreground uppercase flex items-center gap-1">
                  <Activity className="size-3 animate-pulse text-green-500" />
                  <span>Aegis Balancer Core — Local Sandbox</span>
                </div>
                <div className="size-4" />
              </div>

              {/* Demo Tabs */}
              <div className="flex border-b border-border/10">
                {[
                  { id: "prd", label: "1. Parse PRD", icon: Layers },
                  { id: "balancer", label: "2. Assign & Balance", icon: Cpu },
                  { id: "metrics", label: "3. Real-time Capacity", icon: BarChart3 }
                ].map((tab) => {
                  const Icon = tab.icon;
                  const active = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id as any)}
                      className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs md:text-sm font-medium border-r border-border/10 last:border-r-0 transition-colors ${
                        active ? "bg-accent/30 text-primary border-b-2 border-b-primary" : "text-muted-foreground hover:bg-accent/10"
                      }`}
                    >
                      <Icon className="size-3.5" />
                      <span>{tab.label}</span>
                    </button>
                  );
                })}
              </div>

              {/* Demo Content */}
              <div className="p-6 min-h-[300px] flex flex-col justify-center bg-radial from-[#0d1228]/80 to-transparent">
                <AnimatePresence mode="wait">
                  
                  {activeTab === "prd" && (
                    <motion.div
                      key="prd-tab"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="space-y-4 text-left max-w-2xl mx-auto"
                    >
                      <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 relative overflow-hidden">
                        <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-primary uppercase tracking-wide">
                          <Sparkles className="size-3.5" />
                          <span>Input PRD Text</span>
                        </div>
                        <p className="text-xs md:text-sm font-mono text-muted-foreground leading-relaxed">
                          "We need to create a secure login endpoint that authenticates team members. It must parse email structures, hash passwords with bcrypt, verify sessions using Redis, and trigger an alert in Slack on failure."
                        </p>
                      </div>

                      <div className="flex justify-center my-2">
                        <motion.div
                          animate={{ y: [0, 4, 0] }}
                          transition={{ repeat: Infinity, duration: 1.5 }}
                          className="size-6 rounded-full bg-primary/20 border border-primary/40 flex items-center justify-center text-primary"
                        >
                          <ChevronRight className="size-4 rotate-90" />
                        </motion.div>
                      </div>

                      <div className="space-y-2.5">
                        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Generated Task Queue</div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                          <div className="p-3 rounded-lg border border-border/40 bg-card/60 flex items-center justify-between">
                            <div className="min-w-0">
                              <div className="text-xs font-medium text-foreground truncate">Build authentication endpoint</div>
                              <div className="text-[10px] text-muted-foreground">Required: Python, Auth, security</div>
                            </div>
                            <span className="shrink-0 text-[10px] bg-red-500/10 text-red-400 border border-red-500/20 px-1.5 py-0.5 rounded">High</span>
                          </div>
                          <div className="p-3 rounded-lg border border-border/40 bg-card/60 flex items-center justify-between">
                            <div className="min-w-0">
                              <div className="text-xs font-medium text-foreground truncate">Redis session tokens store</div>
                              <div className="text-[10px] text-muted-foreground">Required: Redis, caching, backend</div>
                            </div>
                            <span className="shrink-0 text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1.5 py-0.5 rounded">Medium</span>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  )}

                  {activeTab === "balancer" && (
                    <motion.div
                      key="balancer-tab"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="space-y-6 text-left max-w-xl mx-auto"
                    >
                      <div className="text-center text-xs text-muted-foreground mb-2">
                        Demonstrating Aegis Dynamic Balancer logic (Auto-cycles)
                      </div>
                      
                      {/* Step visualizer */}
                      <div className="flex items-center justify-center gap-10">
                        {/* Task node */}
                        <div className="flex flex-col items-center gap-2">
                          <motion.div
                            animate={{ scale: balancerDemoStep === 0 ? 1.08 : 1 }}
                            className={`size-12 rounded-xl border flex items-center justify-center text-sm font-semibold transition-colors ${
                              balancerDemoStep === 0 ? "border-primary bg-primary/10 shadow-[0_0_15px_rgba(99,102,241,0.25)]" : "border-border/40 bg-card/40 text-muted-foreground"
                            }`}
                          >
                            Task
                          </motion.div>
                          <span className="text-[10px] text-muted-foreground font-mono">auth_api.py</span>
                        </div>

                        {/* Connection arrow */}
                        <div className="relative w-20 h-1 bg-border/20 rounded-full overflow-hidden">
                          <motion.div
                            animate={{
                              left: balancerDemoStep === 0 ? "-100%" : balancerDemoStep === 1 ? "0%" : "100%"
                            }}
                            transition={{ duration: 1.5, ease: "easeInOut" }}
                            className="absolute inset-y-0 w-10 bg-gradient-to-r from-transparent via-primary to-transparent"
                          />
                        </div>

                        {/* Resource destination */}
                        <div className="flex flex-col items-center gap-2">
                          <motion.div
                            animate={{ scale: balancerDemoStep === 2 ? 1.08 : 1 }}
                            className={`size-12 rounded-xl border flex items-center justify-center text-sm font-semibold transition-all ${
                              balancerDemoStep === 2
                                ? "border-violet-500 bg-violet-500/10 shadow-[0_0_15px_rgba(139,92,246,0.3)] text-violet-400"
                                : "border-border/40 bg-card/40 text-muted-foreground"
                            }`}
                          >
                            {balancerDemoStep === 2 ? "🤖 AI" : "👤 Dev"}
                          </motion.div>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {balancerDemoStep === 2 ? "aegis-worker-1" : "pending"}
                          </span>
                        </div>
                      </div>

                      {/* Detail log card */}
                      <div className="p-4 rounded-xl border border-border/20 bg-[#0d1228]/50 font-mono text-[11px] leading-relaxed space-y-1">
                        <div className="text-primary">&gt; analyzing task skills: ["python", "endpoint", "security"]</div>
                        <div className="text-muted-foreground">&gt; scanning human developer load profiles...</div>
                        <div className="text-muted-foreground">&gt; alex_k: load 94% (over capacity limit)</div>
                        <div className="text-violet-400">&gt; routing to AI worker 'aegis-worker-1' (capability match: 98.4%)</div>
                        <div className="text-green-500 font-bold">&gt; action: Auto-balanced successfully.</div>
                      </div>
                    </motion.div>
                  )}

                  {activeTab === "metrics" && (
                    <motion.div
                      key="metrics-tab"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="space-y-4 max-w-xl mx-auto text-left"
                    >
                      <div className="grid grid-cols-3 gap-3">
                        <div className="p-3.5 rounded-lg border border-border/20 bg-card/40">
                          <div className="text-[10px] uppercase text-muted-foreground tracking-wider font-semibold">Workspace Load</div>
                          <div className="text-xl font-bold mt-1 text-primary">64%</div>
                          <div className="text-[9px] text-green-400 flex items-center gap-0.5 mt-0.5">
                            <TrendingUp className="size-2.5" /> Optimal allocation
                          </div>
                        </div>
                        <div className="p-3.5 rounded-lg border border-border/20 bg-card/40">
                          <div className="text-[10px] uppercase text-muted-foreground tracking-wider font-semibold">Triage Speed</div>
                          <div className="text-xl font-bold mt-1 text-primary">&lt; 1 min</div>
                          <div className="text-[9px] text-green-400 flex items-center gap-0.5 mt-0.5">
                            <TrendingUp className="size-2.5" /> 10x speed lift
                          </div>
                        </div>
                        <div className="p-3.5 rounded-lg border border-border/20 bg-card/40">
                          <div className="text-[10px] uppercase text-muted-foreground tracking-wider font-semibold">AI Hand-off</div>
                          <div className="text-xl font-bold mt-1 text-primary">42%</div>
                          <div className="text-[9px] text-muted-foreground mt-0.5">Assigned to agents</div>
                        </div>
                      </div>

                      {/* Bar charts representation */}
                      <div className="p-4 rounded-lg border border-border/20 bg-[#0d1228]/30 space-y-3">
                        <div className="space-y-1.5">
                          <div className="flex justify-between text-xs font-mono text-muted-foreground">
                            <span>Human Engineers Capacity</span>
                            <span>82% capacity used</span>
                          </div>
                          <div className="h-2 w-full bg-border/20 rounded-full overflow-hidden">
                            <div className="h-full w-[82%] bg-primary rounded-full" />
                          </div>
                        </div>
                        <div className="space-y-1.5">
                          <div className="flex justify-between text-xs font-mono text-muted-foreground">
                            <span>AI Workers Capacity</span>
                            <span>45% capacity used</span>
                          </div>
                          <div className="h-2 w-full bg-border/20 rounded-full overflow-hidden">
                            <div className="h-full w-[45%] bg-violet-500 rounded-full" />
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  )}
                  
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ── LOGO CLOUD ── */}
      <section className="border-y border-border/20 bg-card/10 py-10 px-6 overflow-hidden">
        <div className="max-w-7xl mx-auto flex flex-col items-center gap-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
            Trusted by engineering squads at scaling startups
          </p>
          <div className="flex flex-wrap items-center justify-center gap-12 md:gap-20 opacity-40">
            <span className="font-bold tracking-tight text-lg sm:text-xl">Framer</span>
            <span className="font-bold tracking-tight text-lg sm:text-xl">Vercel</span>
            <span className="font-bold tracking-tight text-lg sm:text-xl">Linear</span>
            <span className="font-bold tracking-tight text-lg sm:text-xl">Supabase</span>
            <span className="font-bold tracking-tight text-lg sm:text-xl">PostgreSQL</span>
          </div>
        </div>
      </section>

      {/* ── FEATURES GRID ── */}
      <section id="features" className="py-24 px-6 max-w-7xl mx-auto">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold mb-4 uppercase tracking-wider">
            <Layers className="size-3" />
            <span>Core capabilities</span>
          </div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
            Supercharge your engineering velocity
          </h2>
          <p className="text-muted-foreground">
            Aegis combines automated task generation, resource allocation, and team capacity tracking in a unified workspace.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          
          {/* Card 1 */}
          <div className="rounded-xl border border-border/40 bg-card/40 backdrop-blur-md p-6 hover:shadow-lg hover:border-border/80 transition-all group">
            <div className="size-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mb-5 group-hover:scale-105 transition-transform">
              <Cpu className="size-5" />
            </div>
            <h3 className="text-lg font-bold mb-2 text-foreground">Intelligent AI Balancer</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Scan team loading parameters automatically. Route tasks to human developers or active AI agents based on skill tags, queue backlogs, and speed metrics.
            </p>
          </div>

          {/* Card 2 */}
          <div className="rounded-xl border border-border/40 bg-card/40 backdrop-blur-md p-6 hover:shadow-lg hover:border-border/80 transition-all group">
            <div className="size-10 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-violet-400 mb-5 group-hover:scale-105 transition-transform">
              <Sparkles className="size-5" />
            </div>
            <h3 className="text-lg font-bold mb-2 text-foreground">One-Click PRD Decomposer</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Upload plain text or markdown PRDs. Aegis parses them in seconds, extracts implementation steps, identifies required skills, and schedules distinct task entries.
            </p>
          </div>

          {/* Card 3 */}
          <div className="rounded-xl border border-border/40 bg-card/40 backdrop-blur-md p-6 hover:shadow-lg hover:border-border/80 transition-all group">
            <div className="size-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 mb-5 group-hover:scale-105 transition-transform">
              <BarChart3 className="size-5" />
            </div>
            <h3 className="text-lg font-bold mb-2 text-foreground">Team Capacity Analytics</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Monitor project velocities, pending triage loads, active sessions, and historical completion statistics in a unified, beautiful real-time admin view.
            </p>
          </div>

        </div>
      </section>

      {/* ── INTEGRATIONS SECTION ── */}
      <section id="integrations" className="py-20 bg-card/5 border-y border-border/20 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold uppercase tracking-wider">
              <Zap className="size-3" />
              <span>SaaS Integrations</span>
            </div>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
              Connects with your engineering stack
            </h2>
            <p className="text-muted-foreground leading-relaxed">
              Keep your existing tools in sync. Aegis binds seamlessly to GitHub repositories, Jira issues, Slack alerts, and Google Calendar. It automatically fetches documentation, dispatches tasks, and updates team calendars without context switching.
            </p>
            <div className="space-y-3.5">
              {[
                "Full OAuth 2.0 security protocols",
                "Instant bilateral issue syncing",
                "Real-time event hooks and push integrations"
              ].map((text) => (
                <div key={text} className="flex items-center gap-2.5 text-sm font-medium text-muted-foreground">
                  <CheckCircle2 className="size-4.5 text-primary shrink-0" />
                  <span>{text}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Graphical Integration Web */}
          <div className="relative h-[340px] md:h-[400px] border border-border/20 rounded-2xl bg-[#060814]/80 overflow-hidden flex items-center justify-center">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.06)_0%,transparent_60%)] pointer-events-none" />
            
            {/* Center Aegis logo node */}
            <div className="z-10 size-16 rounded-2xl bg-primary border-2 border-white/10 shadow-[0_0_35px_rgba(99,102,241,0.5)] flex items-center justify-center text-white font-bold text-xl">
              <Shield className="size-8" />
            </div>

            {/* Connecting lines SVG background */}
            <svg className="absolute inset-0 w-full h-full pointer-events-none" xmlns="http://www.w3.org/2000/svg">
              <line x1="15%" y1="20%" x2="50%" y2="50%" stroke="rgba(99,102,241,0.15)" strokeWidth="1.5" strokeDasharray="4" />
              <line x1="85%" y1="20%" x2="50%" y2="50%" stroke="rgba(99,102,241,0.15)" strokeWidth="1.5" strokeDasharray="4" />
              <line x1="15%" y1="80%" x2="50%" y2="50%" stroke="rgba(99,102,241,0.15)" strokeWidth="1.5" strokeDasharray="4" />
              <line x1="85%" y1="80%" x2="50%" y2="50%" stroke="rgba(99,102,241,0.15)" strokeWidth="1.5" strokeDasharray="4" />
            </svg>

            {/* Node 1: GitHub */}
            <div className="absolute top-[12%] left-[8%] size-12 rounded-xl border border-border/30 bg-card/60 shadow-lg flex items-center justify-center text-foreground hover:scale-105 transition-transform duration-200">
              <GitBranch className="size-6" />
            </div>

            {/* Node 2: Slack */}
            <div className="absolute top-[12%] right-[8%] size-12 rounded-xl border border-border/30 bg-card/60 shadow-lg flex items-center justify-center text-foreground hover:scale-105 transition-transform duration-200">
              <MessageSquare className="size-6 text-green-400" />
            </div>

            {/* Node 3: Jira */}
            <div className="absolute bottom-[12%] left-[8%] size-12 rounded-xl border border-border/30 bg-card/60 shadow-lg flex items-center justify-center text-foreground hover:scale-105 transition-transform duration-200">
              <Layers className="size-6 text-blue-400" />
            </div>

            {/* Node 4: Google Calendar */}
            <div className="absolute bottom-[12%] right-[8%] size-12 rounded-xl border border-border/30 bg-card/60 shadow-lg flex items-center justify-center text-foreground hover:scale-105 transition-transform duration-200">
              <Calendar className="size-6 text-violet-400" />
            </div>
          </div>
        </div>
      </section>

      {/* ── CASE STUDY / SUCCESS METRICS ── */}
      <section className="py-24 px-6 max-w-7xl mx-auto">
        <div className="rounded-2xl border border-border/20 bg-card/25 backdrop-blur-md p-8 md:p-12 grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-5 space-y-6">
            <div className="text-xs font-semibold uppercase tracking-wider text-primary">Case Study</div>
            <h3 className="text-2xl md:text-3xl font-bold tracking-tight text-foreground">
              How Fetch Optimized Sprint Triage by 10x
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              "By feeding product specs directly into Aegis PM, we bypassed manual ticket creation and allocated resources using the auto-balancer. We completed 42% more tasks per sprint without hiring backlog dispatchers."
            </p>
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold text-sm">
                F
              </div>
              <div>
                <div className="text-sm font-semibold text-foreground">Marcus Sterling</div>
                <div className="text-xs text-muted-foreground">VP of Product, Fetch Inc.</div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { val: "42%", label: "Sprint velocity lift", icon: TrendingUp },
              { val: "10x", label: "Triage processing speed", icon: Zap },
              { val: "98.4%", label: "Balancer match accuracy", icon: CheckCircle2 }
            ].map((metric) => {
              const Icon = metric.icon;
              return (
                <div key={metric.label} className="p-5 rounded-xl border border-border/20 bg-[#060814]/75 text-center flex flex-col items-center">
                  <div className="size-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary mb-3">
                    <Icon className="size-4" />
                  </div>
                  <div className="text-3xl font-extrabold text-foreground tracking-tight">{metric.val}</div>
                  <div className="text-[11px] text-muted-foreground mt-1.5 leading-snug">{metric.label}</div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── TESTIMONIALS SECTION ── */}
      <section className="py-24 px-6 border-t border-border/20 bg-card/5">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold mb-4 uppercase tracking-wider">
              <Users className="size-3" />
              <span>Social Proof</span>
            </div>
            <h2 className="text-3xl font-bold tracking-tight mb-4">Loved by engineering managers</h2>
            <p className="text-muted-foreground">See how tech leaders are shipping faster with Aegis PM.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                quote: "Aegis completely redesigned our planning cycle. Uploading a PRD and seeing accurate task distributions in a minute felt like magic.",
                name: "Sarah Chen",
                role: "Director of Engineering, Velo",
                initials: "SC"
              },
              {
                quote: "The dynamic balancer helps prevent burnouts. It flags immediately when human engineers are oversubscribed and delegates backend tasks to AI workers.",
                name: "David K.",
                role: "Tech Lead, Supabase App",
                initials: "DK"
              },
              {
                quote: "Setting up AI workers with direct access to our sandbox enabled us to ship minor bug fixes and feature updates 3x faster than traditional pipelines.",
                name: "Elena Rostova",
                role: "CTO, CloudScale",
                initials: "ER"
              }
            ].map((t) => (
              <div key={t.name} className="p-6 rounded-xl border border-border/40 bg-card/40 backdrop-blur-md flex flex-col justify-between hover:shadow-lg transition-all">
                <p className="text-sm text-muted-foreground/90 leading-relaxed italic mb-6">
                  "{t.quote}"
                </p>
                <div className="flex items-center gap-3">
                  <div className="size-9 rounded-full bg-violet-500/20 text-violet-400 font-bold text-xs flex items-center justify-center">
                    {t.initials}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-foreground">{t.name}</div>
                    <div className="text-xs text-muted-foreground">{t.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING SECTION ── */}
      <section id="pricing" className="py-24 px-6 max-w-7xl mx-auto">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold mb-4 uppercase tracking-wider">
            <Flame className="size-3" />
            <span>Pricing plans</span>
          </div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">Pricing built to scale with your team</h2>
          <p className="text-muted-foreground">Start free, upgrade when you onboard more workers.</p>

          {/* Billing Switcher */}
          <div className="flex items-center justify-center gap-3 mt-8">
            <span className={`text-sm ${billingPeriod === "monthly" ? "text-foreground font-semibold" : "text-muted-foreground"}`}>Monthly</span>
            <button
              onClick={() => setBillingPeriod((p) => (p === "monthly" ? "yearly" : "monthly"))}
              className="w-12 h-6.5 rounded-full bg-primary/25 border border-primary/30 p-0.5 relative transition-colors duration-200"
            >
              <motion.div
                animate={{ x: billingPeriod === "monthly" ? 0 : 22 }}
                transition={{ duration: 0.2 }}
                className="size-5 rounded-full bg-primary shadow-md"
              />
            </button>
            <span className={`text-sm ${billingPeriod === "yearly" ? "text-foreground font-semibold" : "text-muted-foreground"}`}>
              Yearly <span className="text-xs text-green-400 font-bold border border-green-500/20 bg-green-500/10 px-1.5 py-0.5 rounded ml-1">Save 20%</span>
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
          {/* Tier 1 */}
          <div className="rounded-xl border border-border/40 bg-card/40 backdrop-blur-md p-6 flex flex-col justify-between hover:shadow-lg transition-all">
            <div>
              <div className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Free</div>
              <div className="text-3xl font-bold text-foreground mt-4">$0</div>
              <div className="text-xs text-muted-foreground mt-1">Free forever for individuals</div>
              <div className="h-px bg-border/20 my-6" />
              <ul className="space-y-3 text-xs md:text-sm text-muted-foreground">
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> Basic balancer scheduling</li>
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> Up to 3 active projects</li>
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> 1 AI Worker profile</li>
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> Local database access</li>
              </ul>
            </div>
            <Link href="/dashboard" className="mt-8">
              <Button variant="outline" className="w-full">Get Started</Button>
            </Link>
          </div>

          {/* Tier 2 (Featured) */}
          <div className="rounded-xl border-2 border-primary bg-[#090e22]/90 p-6 flex flex-col justify-between shadow-xl shadow-primary/10 hover:shadow-primary/20 hover:scale-[1.01] transition-all relative">
            <div className="absolute top-0 right-6 -translate-y-1/2 bg-primary text-white text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-full shadow-[0_0_15px_rgba(99,102,241,0.5)]">
              Most Popular
            </div>
            <div>
              <div className="text-sm font-semibold text-primary uppercase tracking-wider">Pro Plan</div>
              <div className="flex items-baseline mt-4">
                <span className="text-4xl font-extrabold text-foreground">
                  ${billingPeriod === "monthly" ? "380" : "304"}
                </span>
                <span className="text-xs text-muted-foreground ml-1">/month</span>
              </div>
              <div className="text-xs text-muted-foreground mt-1">Best for active product teams</div>
              <div className="h-px bg-border/20 my-6" />
              <ul className="space-y-3 text-xs md:text-sm text-muted-foreground">
                <li className="flex items-center gap-2.5 text-foreground"><Check className="size-4 text-primary shrink-0" /> Advanced skill-based balancing</li>
                <li className="flex items-center gap-2.5 text-foreground"><Check className="size-4 text-primary shrink-0" /> Unlimited active projects</li>
                <li className="flex items-center gap-2.5 text-foreground"><Check className="size-4 text-primary shrink-0" /> 5 active AI Worker profiles</li>
                <li className="flex items-center gap-2.5 text-foreground"><Check className="size-4 text-primary shrink-0" /> Full GitHub & Slack integrations</li>
                <li className="flex items-center gap-2.5 text-foreground"><Check className="size-4 text-primary shrink-0" /> Priority support</li>
              </ul>
            </div>
            <Link href="/dashboard" className="mt-8">
              <Button className="w-full bg-primary hover:bg-primary/90 text-white shadow-[0_0_20px_rgba(99,102,241,0.2)]">Upgrade to Pro</Button>
            </Link>
          </div>

          {/* Tier 3 */}
          <div className="rounded-xl border border-border/40 bg-card/40 backdrop-blur-md p-6 flex flex-col justify-between hover:shadow-lg transition-all">
            <div>
              <div className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Enterprise</div>
              <div className="flex items-baseline mt-4">
                <span className="text-4xl font-extrabold text-foreground">
                  ${billingPeriod === "monthly" ? "680" : "544"}
                </span>
                <span className="text-xs text-muted-foreground ml-1">/month</span>
              </div>
              <div className="text-xs text-muted-foreground mt-1">For secure, scale operations</div>
              <div className="h-px bg-border/20 my-6" />
              <ul className="space-y-3 text-xs md:text-sm text-muted-foreground">
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> Custom AI agent capabilities</li>
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> Write access to repos for auto-fixes</li>
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> Dedicated LLM compute allocation</li>
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> SSO / SAML & role isolation</li>
                <li className="flex items-center gap-2.5"><Check className="size-4 text-primary shrink-0" /> 24/7 dedicated support representative</li>
              </ul>
            </div>
            <Link href="/dashboard" className="mt-8">
              <Button variant="outline" className="w-full">Contact Sales</Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ── FAQS SECTION ── */}
      <section id="faqs" className="py-24 px-6 border-t border-border/20 bg-card/5">
        <div className="max-w-4xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold mb-4 uppercase tracking-wider">
              <CheckCircle2 className="size-3" />
              <span>FAQ</span>
            </div>
            <h2 className="text-3xl font-bold tracking-tight mb-4">Frequently Asked Questions</h2>
            <p className="text-muted-foreground">Have details you want to resolve? Check our quick references below.</p>
          </div>

          <Accordion items={faqItems} />
        </div>
      </section>

      {/* ── INSIGHTS / BLOG ── */}
      <section id="blog" className="py-24 px-6 max-w-7xl mx-auto">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold mb-4 uppercase tracking-wider">
            <Layers className="size-3" />
            <span>Insights</span>
          </div>
          <h2 className="text-3xl font-bold tracking-tight mb-4">Latest from Aegis Insights</h2>
          <p className="text-muted-foreground">Read about capacity balancing, AI co-piloting, and project management engineering.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {blogPosts.map((post) => (
            <div key={post.title} className="rounded-xl border border-border/40 bg-card/40 backdrop-blur-md p-6 flex flex-col justify-between hover:shadow-lg transition-all group">
              <div>
                <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
                  <span className="font-semibold text-primary">{post.category}</span>
                  <span>{post.date}</span>
                </div>
                <h3 className="text-base font-bold text-foreground mb-2 group-hover:text-primary transition-colors">
                  {post.title}
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {post.desc}
                </p>
              </div>
              <a href={post.link} className="inline-flex items-center gap-1.5 text-xs text-primary font-semibold hover:underline mt-6">
                Read article <ArrowRight className="size-3.5" />
              </a>
            </div>
          ))}
        </div>
      </section>

      {/* ── CONVERSION BANNER ── */}
      <section className="py-20 px-6 max-w-7xl mx-auto">
        <div className="relative rounded-3xl border border-border/30 bg-radial from-[#1e1b4b]/60 to-[#030712] p-8 md:p-16 text-center overflow-hidden shadow-2xl">
          <div className="absolute top-[-100px] left-1/2 -translate-x-1/2 -z-10 h-[300px] w-[500px] rounded-full bg-primary/10 blur-[100px] pointer-events-none" />
          
          <h2 className="text-3xl md:text-5xl font-extrabold tracking-tight mb-6 max-w-3xl mx-auto leading-tight">
            Transform your workflow with intelligent AI project management
          </h2>
          <p className="text-sm md:text-base text-muted-foreground/90 max-w-xl mx-auto mb-10 leading-relaxed">
            Eliminate task dispatch bottlenecks. Parse specs, route allocations automatically, and ship software with high velocity today.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/dashboard">
              <Button size="lg" className="bg-primary hover:bg-primary/90 text-white font-semibold shadow-[0_0_20px_rgba(99,102,241,0.3)]">
                Get Started Now
              </Button>
            </Link>
            <Link href="/dashboard">
              <Button variant="ghost" size="lg" className="text-muted-foreground hover:text-foreground">
                Sign In Instead
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="border-t border-border/20 bg-card/5 py-12 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-8">
          <div className="space-y-4">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
                <Shield className="size-4.5" />
              </div>
              <span className="text-sm font-bold tracking-tight text-foreground">
                Aegis PM
              </span>
            </Link>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Assigned, balanced sprint tasks generated automatically in under 60 seconds from PRDs.
            </p>
          </div>

          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-4">Product</h4>
            <ul className="space-y-2 text-xs text-muted-foreground">
              <li><a href="#features" className="hover:text-foreground">Features</a></li>
              <li><a href="#integrations" className="hover:text-foreground">Integrations</a></li>
              <li><a href="#pricing" className="hover:text-foreground">Pricing Plans</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-4">Resources</h4>
            <ul className="space-y-2 text-xs text-muted-foreground">
              <li><a href="#blog" className="hover:text-foreground">Blog</a></li>
              <li><a href="#faqs" className="hover:text-foreground">FAQs</a></li>
              <li><a href="#" className="hover:text-foreground">Documentation</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-4">Company</h4>
            <ul className="space-y-2 text-xs text-muted-foreground">
              <li><a href="#" className="hover:text-foreground">About Us</a></li>
              <li><a href="#" className="hover:text-foreground">Security</a></li>
              <li><a href="#" className="hover:text-foreground">Contact</a></li>
            </ul>
          </div>
        </div>

        <div className="max-w-7xl mx-auto border-t border-border/10 mt-10 pt-6 flex flex-col sm:flex-row items-center justify-between text-xs text-muted-foreground gap-4">
          <div>© {new Date().getFullYear()} Aegis PM Inc. All rights reserved.</div>
          <div className="flex gap-4">
            <a href="#" className="hover:text-foreground">Privacy Policy</a>
            <a href="#" className="hover:text-foreground">Terms of Service</a>
          </div>
        </div>
      </footer>

    </div>
  );
}
