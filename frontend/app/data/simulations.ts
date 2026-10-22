// Hands-on work simulations: four tasks per role, done in a mini workspace.
// Tasks 1–2 are the job's core work; tasks 3–4 use the AI tools now arriving in that field (replies are scripted).
// All names, companies and figures are fictional.

import type { SheetSpec } from "../lib/sheet";

/** manager's comment on the work, picked by score: ≥0.9 high, ≥0.5 mid, else low */
export type Review = { high: string; mid: string; low: string };

type TaskBase = {
  id: string;
  title: string;
  /** competency shown on the performance report */
  competency: string;
  /** roadmap skill gap this task builds, if any */
  gap?: string;
  /** expected time, for the report */
  minutes: number;
  from: string;
  fromRole: string;
  subject: string;
  brief: string;
  requirements: string[];
  review: Review;
};

export type SheetTask = TaskBase & { tool: "sheet"; sheet: SheetSpec };

export type CodeTask = TaskBase & {
  tool: "code";
  fn: string;
  /** helper functions available to the user's code */
  helpers: { signature: string; source: string }[];
  starter: string;
  tests: { label: string; args: unknown[]; expected: unknown }[];
};

export type DocTask = TaskBase & {
  tool: "doc";
  docName: string;
  template: string;
  checklist: { label: string; keywords: string[] }[];
  words: [number, number];
};

export type CalEvent = {
  id: string;
  title: string;
  people: string[];
  /** must finish by this day index and hour */
  deadline?: { day: number; hour: number; label: string };
  /** must start after this event ends */
  after?: string;
};

export type CalendarTask = TaskBase & {
  tool: "calendar";
  days: string[];
  hours: number[];
  /** per person, the busy start hours for each day */
  busy: Record<string, number[][]>;
  events: CalEvent[];
};

type AiTaskBase = TaskBase & {
  /** the simulated AI tool's name */
  aiName: string;
  /** why this AI skill matters now, shown in the inbox */
  why: string;
};

export type AiReply = { text: string; table?: { columns: string[]; rows: string[][] }; steps?: string[]; note?: string };

/** "Direct the AI": the user briefs an AI tool; the reply depends on how complete the brief is */
export type PromptTask = AiTaskBase & {
  tool: "prompt";
  rubric: { label: string; keywords: string[] }[];
  replies: { weak: AiReply; partial: AiReply; strong: AiReply };
};

/** "Check the AI's work": an AI draft with planted mistakes to catch */
export type ReviewTask = AiTaskBase & {
  tool: "review";
  artifactName: string;
  format: "prose" | "code";
  source: { title: string; columns: string[]; rows: string[][] };
  segments: { text: string; issue?: string }[];
  verdict: "approve" | "send back";
};

export type SimTask = SheetTask | CodeTask | DocTask | CalendarTask | PromptTask | ReviewTask;

export const isAiTask = (t: SimTask): t is PromptTask | ReviewTask => t.tool === "prompt" || t.tool === "review";

export type Simulation = {
  roleId: string;
  title: string;
  setting: string;
  welcome: { from: string; text: string };
  tasks: SimTask[];
};

/** what a finished task reports back */
export type Outcome = { score: number; evidence: string[]; seconds: number; enjoy: number };

export type Quadrant = "Strong fit" | "Capable, may burn out" | "Learnable" | "Probably not for you";

export type SimResult = {
  can: number;
  want: number;
  quadrant: Quadrant;
  weakest?: { skill: string; gap?: string };
  at: string;
};

export const FIT_THRESHOLD = 60;

export function quadrantOf(can: number, want: number): Quadrant {
  if (can >= FIT_THRESHOLD) return want >= FIT_THRESHOLD ? "Strong fit" : "Capable, may burn out";
  return want >= FIT_THRESHOLD ? "Learnable" : "Probably not for you";
}

export function reviewFor(task: SimTask, score: number) {
  return score >= 0.9 ? task.review.high : score >= 0.5 ? task.review.mid : task.review.low;
}

export function checkDoc(task: DocTask, text: string) {
  const t = text.toLowerCase();
  const plain = t.replace(/,/g, "");
  return task.checklist.map((c) => c.keywords.some((k) => t.includes(k) || plain.includes(k)));
}

/** which rubric items a brief covers; numbers are matched with or without thousands separators */
export function checkBrief(task: PromptTask, text: string) {
  const t = text.toLowerCase();
  const plain = t.replace(/,/g, "");
  return task.rubric.map((c) => c.keywords.some((k) => t.includes(k) || plain.includes(k)));
}

export function replyFor(task: PromptTask, hits: boolean[]) {
  const n = hits.filter(Boolean).length;
  return n === hits.length ? task.replies.strong : n >= 2 ? task.replies.partial : task.replies.weak;
}

export const wordCount = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const HOURS = [9, 10, 11, 12, 13, 14, 15, 16];

export const simulations: Simulation[] = [
  {
    roleId: "fpa-analyst",
    title: "FP&A Analyst",
    setting: "Monday 09:00 · Week 1 · Group finance",
    welcome: { from: "Farid Hassan", text: "Welcome aboard! 👋 The Q4 forecast is due this week, and you get to try our new AI assistant too." },
    tasks: [
      {
        id: "forecast",
        tool: "sheet",
        title: "Build the Q4 forecast",
        competency: "Financial modelling",
        gap: "Financial modelling",
        minutes: 6,
        from: "Farid Hassan",
        fromRole: "CFO",
        subject: "Q4 forecast model",
        brief: "Hi, can you finish the Q4 forecast in the attached sheet? Q3 actuals and growth assumptions are already in. Use formulas so I can change the assumptions later.",
        requirements: [
          "Q4 forecast = Q3 actual × (1 + growth)",
          "Operating profit = revenue − cost of sales − operating expenses",
          "Variance = Q4 forecast − Q4 budget",
          "Tip: start a cell with = to write a formula, e.g. =B2*(1+C2)",
        ],
        sheet: {
          name: "Q4_forecast.xlsx",
          columns: [
            { label: "Line item", fmt: "text" },
            { label: "Q3 actual (RM)", fmt: "rm" },
            { label: "Growth", fmt: "pct" },
            { label: "Q4 forecast (RM)", fmt: "rm" },
            { label: "Q4 budget (RM)", fmt: "rm" },
            { label: "Variance (RM)", fmt: "rm" },
          ],
          rows: [
            ["Revenue", "1,200,000", "8%", { expect: 1296000 }, "1,250,000", { expect: 46000 }],
            ["Cost of sales", "720,000", "6%", { expect: 763200 }, "750,000", { expect: 13200 }],
            ["Operating expenses", "300,000", "2%", { expect: 306000 }, "310,000", { expect: -4000 }],
            ["Operating profit", "180,000", "", { expect: 226800 }, "190,000", { expect: 36800 }],
          ],
        },
        review: {
          high: "Clean model, and it's formula-driven so I can flex the assumptions in the meeting. Exactly what I needed.",
          mid: "Most of it is right, but a few cells don't tie out. I'd have caught that in review, but the CEO wouldn't have.",
          low: "The numbers don't hold together yet. Let's sit down and walk through how the forecast links up.",
        },
      },
      {
        id: "schedule",
        tool: "calendar",
        title: "Book the budget review",
        competency: "Planning & coordination",
        minutes: 4,
        from: "Farid Hassan",
        fromRole: "CFO",
        subject: "Budget review meeting",
        brief: "Please book the Q4 budget review with me, Mei Ling (Sales) and Ravi (Ops). I also need a 1-hour prep with you beforehand. Everything has to be done before Thursday noon.",
        requirements: [
          "Book a 1-hour prep with Farid",
          "Book the 1-hour review with Farid, Mei Ling and Ravi, after the prep",
          "Both must finish before Thursday 12:00",
          "Shaded slots show when attendees are busy",
        ],
        days: WEEK,
        hours: HOURS,
        busy: {
          Farid: [[9, 10, 11, 14], [9, 10, 11, 12, 13, 14, 15, 16], [10, 15], [9, 10], []],
          "Mei Ling": [[13, 14, 15, 16], [], [9, 10, 14], [11], []],
          Ravi: [[9, 10, 15, 16], [], [13, 16], [9, 10], []],
        },
        events: [
          { id: "prep", title: "Prep with Farid", people: ["Farid"], deadline: { day: 3, hour: 12, label: "Thu 12:00" } },
          {
            id: "review",
            title: "Q4 budget review",
            people: ["Farid", "Mei Ling", "Ravi"],
            deadline: { day: 3, hour: 12, label: "Thu 12:00" },
            after: "prep",
          },
        ],
        review: {
          high: "Booked, no clashes, and the prep is before the review. Thanks for sorting that without a single email chain.",
          mid: "One of these doesn't work: check the deadline and who's free.",
          low: "These slots don't work for the people involved. Check everyone's calendar before sending invites.",
        },
      },
      {
        id: "ai-scenario",
        tool: "prompt",
        title: "Brief the forecasting AI",
        competency: "Directing AI tools",
        minutes: 5,
        aiName: "Forecast Assistant",
        why: "Finance teams are starting to use AI assistants to draft scenarios in minutes. The skill is no longer building every number by hand; it's briefing the AI well and knowing what to give it.",
        from: "Farid Hassan",
        fromRole: "CFO",
        subject: "Try the new forecasting assistant",
        brief: "We're piloting an AI forecasting assistant. Use it to build a downside scenario for Q4: what happens to operating profit if revenue only grows 2% instead of 8%? It only knows what you tell it.",
        requirements: [
          "Give it context: what forecast, which quarter",
          "Give it the numbers it needs (it can't see your sheet)",
          "State the assumption to change, and what to keep the same",
          "Ask for a clear output, e.g. a table comparing base vs downside",
        ],
        rubric: [
          { label: "Context", keywords: ["q4", "forecast", "quarter"] },
          { label: "Base numbers", keywords: ["1200000", "1.2m", "1.2 m", "720000", "763200", "300000", "306000", "1296000"] },
          { label: "Assumption", keywords: ["2%", "2 %", "two percent", "2 percent"] },
          { label: "What stays fixed", keywords: ["keep", "same", "constant", "unchanged", "hold", "flat", "fixed"] },
          { label: "Output format", keywords: ["table", "compare", "comparison", " vs", "versus", "side by side", "column"] },
        ],
        replies: {
          weak: {
            text: "Sure! A downside scenario usually assumes lower revenue than planned. A common approach is to cut revenue by 5–10% and see what happens to profit. Would you like some general tips on scenario planning?",
          },
          partial: {
            text: "Here's a downside scenario with 2% revenue growth. I don't have your actual figures, so I've used illustrative numbers:",
            table: {
              columns: ["", "Base", "Downside"],
              rows: [
                ["Revenue", "1,000,000", "1,020,000"],
                ["Costs", "800,000", "800,000"],
                ["Profit", "200,000", "220,000"],
              ],
            },
            note: "⚠ These numbers are made up because the brief didn't include yours. This is how AI tools quietly invent figures.",
          },
          strong: {
            text: "Downside scenario for Q4, with revenue growth cut from 8% to 2% and costs held at the base forecast:",
            table: {
              columns: ["RM", "Base (8%)", "Downside (2%)", "Change"],
              rows: [
                ["Revenue", "1,296,000", "1,224,000", "−72,000"],
                ["Cost of sales", "763,200", "763,200", "0"],
                ["Operating expenses", "306,000", "306,000", "0"],
                ["Operating profit", "226,800", "154,800", "−72,000 (−31.7%)"],
              ],
            },
            note: "Holding cost of sales flat is conservative. If it scales with volume, downside profit would be about RM197k. Want me to add that as a third scenario?",
          },
        },
        review: {
          high: "That's exactly what I needed for the board. Good brief: the assistant had everything it needed.",
          mid: "Useful, but I had to fill in gaps. Give it the numbers and the format, and it does the rest.",
          low: "The assistant was guessing. With AI tools, the quality of the brief is the quality of the answer.",
        },
      },
      {
        id: "ai-commentary",
        tool: "review",
        title: "Check the AI's commentary",
        competency: "Verifying AI output",
        minutes: 5,
        aiName: "Forecast Assistant",
        why: "AI can draft board commentary in seconds, but it can misread numbers or invent explanations that sound plausible. A person still signs it off.",
        from: "Farid Hassan",
        fromRole: "CFO",
        subject: "AI draft: variance commentary",
        brief: "The assistant drafted the variance commentary for the board pack. Check every sentence against the model before it goes anywhere. Flag anything that's wrong, then approve it or send it back.",
        requirements: [
          "Click a sentence to flag it as wrong",
          "Check numbers against the source data",
          "Watch for explanations or facts the AI couldn't know",
          "Then approve it or send it back",
        ],
        artifactName: "Q4 variance commentary (AI draft)",
        format: "prose",
        source: {
          title: "Your Q4 model",
          columns: ["RM", "Q4 forecast", "Q4 budget", "Variance"],
          rows: [
            ["Revenue", "1,296,000", "1,250,000", "+46,000"],
            ["Cost of sales", "763,200", "750,000", "+13,200"],
            ["Operating expenses", "306,000", "310,000", "−4,000"],
            ["Operating profit", "226,800", "190,000", "+36,800"],
          ],
        },
        segments: [
          { text: "Q4 revenue is forecast at RM1,296,000, RM46,000 ahead of budget." },
          {
            text: "Cost of sales is RM13,200 under budget, reflecting strong supplier negotiations.",
            issue: "Cost of sales is over budget, not under. And nothing in the model mentions supplier negotiations; the AI made up a reason.",
          },
          { text: "Operating expenses are RM4,000 below budget." },
          {
            text: "As a result, operating profit is forecast at RM262,800, 38% above budget.",
            issue: "Wrong number: operating profit is RM226,800, about 19% above budget.",
          },
          {
            text: "This is in line with the wider Malaysian market, which grew 8% this quarter.",
            issue: "An unsourced market statistic. The 8% is your growth assumption, not a market figure.",
          },
          { text: "We recommend reviewing cost of sales with Operations before year end." },
        ],
        verdict: "send back",
        review: {
          high: "Good catch. That would have gone to the board with two wrong numbers. This is why we check AI drafts.",
          mid: "You caught some of it, but a mistake still slipped through. Every number gets checked, every time.",
          low: "This would have embarrassed us at the board. AI drafts are a starting point, not a final answer.",
        },
      },
    ],
  },
  {
    roleId: "ai-risk-controls",
    title: "AI Risk & Controls Analyst",
    setting: "Monday 10:00 · Week 1 · Model risk team",
    welcome: { from: "Ahmad Razak", text: "Hi, welcome to the team! The loan approval model launches Friday. We need to review it first." },
    tasks: [
      {
        id: "fairness",
        tool: "sheet",
        title: "Test the model for fairness",
        competency: "Model testing",
        gap: "AI risk frameworks",
        minutes: 6,
        from: "Ahmad Razak",
        fromRole: "Head of Risk",
        subject: "Loan model: fairness check",
        brief: "The model passed accuracy testing at 91%. Before sign-off, run the four-fifths check on the pilot approvals: any group approved at less than 0.8× the salaried rate needs explaining.",
        requirements: [
          "Approval rate = approved ÷ applications",
          "Ratio vs salaried = group's rate ÷ salaried rate",
          "Below 0.8? → type Yes or No",
          "Tip: start a cell with = to write a formula, e.g. =C2/B2",
        ],
        sheet: {
          name: "pilot_approvals.xlsx",
          columns: [
            { label: "Applicant group", fmt: "text" },
            { label: "Applications", fmt: "num" },
            { label: "Approved", fmt: "num" },
            { label: "Approval rate", fmt: "pct" },
            { label: "Ratio vs salaried", fmt: "dec" },
            { label: "Below 0.8?", fmt: "text" },
          ],
          rows: [
            ["Salaried", "4,200", "2,940", { expect: 0.7 }, "1.00", "No"],
            ["Government", "900", "720", { expect: 0.8 }, { expect: 1.1429, tol: 0.01 }, { expect: "No" }],
            ["Self-employed", "1,100", "330", { expect: 0.3 }, { expect: 0.4286, tol: 0.01 }, { expect: "Yes" }],
            ["Gig workers", "600", "90", { expect: 0.15 }, { expect: 0.2143, tol: 0.01 }, { expect: "Yes" }],
          ],
        },
        review: {
          high: "Spot on. Two groups fail the four-fifths test, and you've shown it clearly. That's our finding.",
          mid: "You're close, but some of the ratios are off. In risk work, one wrong number undermines the whole finding.",
          low: "The test isn't right yet. Let's go through how the ratios work together.",
        },
      },
      {
        id: "committee",
        tool: "calendar",
        title: "Get it reviewed before launch",
        competency: "Planning under a deadline",
        minutes: 4,
        from: "Kevin Lim",
        fromRole: "Product Owner",
        subject: "Launch is Friday 9am!",
        brief: "If the committee needs to see this, it has to happen before we launch on Friday morning. After they decide, I need a session to train the loan officers on the human-review step before Friday noon.",
        requirements: [
          "Committee review: Ahmad, Kevin and Siti (Legal), finished before Fri 09:00",
          "Loan officer training with Kevin, after the committee, finished by Fri 12:00",
          "Shaded slots show when attendees are busy",
        ],
        days: WEEK,
        hours: HOURS,
        busy: {
          Ahmad: [[9, 10, 11, 12, 13, 14, 16], [9, 10, 11, 12], [13, 14, 15, 16], [9, 10, 11, 14, 15, 16], []],
          Kevin: [[15], [13, 14, 15, 16], [9, 10, 11], [12, 13], [9, 10]],
          Siti: [[], [9, 10, 11, 12, 13, 14], [], [9, 10, 11, 12, 13, 16], []],
        },
        events: [
          { id: "committee", title: "Model risk committee", people: ["Ahmad", "Kevin", "Siti"], deadline: { day: 4, hour: 9, label: "Fri 09:00" } },
          { id: "training", title: "Train loan officers", people: ["Kevin"], deadline: { day: 4, hour: 12, label: "Fri 12:00" }, after: "committee" },
        ],
        review: {
          high: "Committee before launch, training straight after. The launch stays on track and the control is in place.",
          mid: "One of these doesn't work. Check the order and the launch deadline.",
          low: "These don't fit people's calendars or the launch date. Check availability before booking.",
        },
      },
      {
        id: "ai-explainer",
        tool: "prompt",
        title: "Question the model explainer",
        competency: "Directing AI tools",
        gap: "AI fundamentals",
        minutes: 5,
        aiName: "Model Explainer",
        why: "Explainability tools show which inputs drive an AI model's decisions. Risk teams use them to find hidden bias, but only if they ask the right question.",
        from: "Ahmad Razak",
        fromRole: "Head of Risk",
        subject: "Why are gig workers rejected?",
        brief: "Our explainability tool can break down what drives the loan model's decisions. Use it to find out why gig workers are rejected so much more often. Ask it precisely.",
        requirements: [
          "Name the model and the group you're investigating",
          "Ask which inputs (features) drive the decision",
          "Ask it to compare against salaried applicants",
          "Ask for a clear output, e.g. a ranked table",
        ],
        rubric: [
          { label: "Names the model", keywords: ["loan", "approval model", "credit model", "the model"] },
          { label: "Names the group", keywords: ["gig", "self-employed", "self employed"] },
          { label: "Asks for drivers", keywords: ["feature", "factor", "driver", "input", "variable", "why"] },
          { label: "Asks to compare", keywords: ["compare", "salaried", "versus", " vs", "difference"] },
          { label: "Output format", keywords: ["table", "rank", "list", "top"] },
        ],
        replies: {
          weak: {
            text: "Credit models typically consider many factors, such as income, credit history and existing debt. Is there a specific model you'd like me to look at?",
          },
          partial: {
            text: "Top factors lowering approval for gig workers in the loan approval model:",
            table: {
              columns: ["Feature", "Effect on gig applicants"],
              rows: [
                ["Employment type = gig", "−0.31"],
                ["Income variability", "−0.22"],
                ["Postcode cluster", "−0.12"],
              ],
            },
            note: "Without a comparison you can't tell which of these treat gig workers differently from everyone else.",
          },
          strong: {
            text: "Feature contributions to the approval score, gig workers vs salaried applicants (loan approval model, pilot data):",
            table: {
              columns: ["Feature", "Gig workers", "Salaried", "Gap"],
              rows: [
                ["Employment type", "−0.31", "+0.05", "Large"],
                ["Income variability", "−0.22", "−0.04", "Large"],
                ["Postcode cluster", "−0.12", "+0.02", "Medium"],
                ["Credit history length", "−0.05", "−0.03", "Small"],
                ["Debt-to-income", "−0.04", "−0.06", "None"],
              ],
            },
            note: "Employment type is used directly, and postcode may be acting as a proxy for it. Both should be reviewed against your fairness policy. (Illustrative output for a fictional model.)",
          },
        },
        review: {
          high: "That's the finding: employment type and a postcode proxy. Exactly what the committee needs to see.",
          mid: "We're getting somewhere, but without the comparison the committee will ask 'compared to what?'",
          low: "The tool couldn't help with a question that vague. Be specific about model, group and output.",
        },
      },
      {
        id: "ai-audit",
        tool: "review",
        title: "Check the AI's audit summary",
        competency: "Verifying AI output",
        gap: "Responsible AI",
        minutes: 5,
        aiName: "Audit Copilot",
        why: "AI tools now draft audit and compliance summaries. They tend to sound confident even when they gloss over a failed test, which is exactly what a reviewer has to catch.",
        from: "Ahmad Razak",
        fromRole: "Head of Risk",
        subject: "AI draft: validation summary",
        brief: "The audit copilot drafted the model validation summary from our test log. Check it against the log before I sign it. Flag anything wrong, then approve or send it back.",
        requirements: [
          "Click a sentence to flag it as wrong",
          "Check each claim against the test log",
          "Watch for overconfident conclusions",
          "Then approve it or send it back",
        ],
        artifactName: "Model validation summary (AI draft)",
        format: "prose",
        source: {
          title: "Test log: loan approval model",
          columns: ["Test", "Result", "Detail"],
          rows: [
            ["Accuracy (hold-out)", "PASS", "91% vs 85% threshold"],
            ["Fairness: four-fifths", "FAIL", "Gig 0.21, self-employed 0.43"],
            ["Data drift", "NOT RUN", "Scheduled after launch"],
            ["Explainability", "PASS", "Employment type top driver for gig"],
          ],
        },
        segments: [
          { text: "The loan approval model achieved 91% accuracy on the hold-out set, above the 85% threshold." },
          {
            text: "Fairness testing found no material differences between applicant groups.",
            issue: "The fairness test failed: gig (0.21) and self-employed (0.43) are well below 0.8.",
          },
          {
            text: "Data drift monitoring was completed and showed stable inputs.",
            issue: "The drift test was never run. The AI filled the gap with something plausible.",
          },
          { text: "Explainability analysis shows employment type is the top driver for gig applicants." },
          {
            text: "The model is therefore ready for production without further controls.",
            issue: "An overconfident conclusion. With a failed fairness test, it needs controls (e.g. human review) before launch.",
          },
          { text: "Ongoing performance will be reviewed quarterly by the model risk team." },
        ],
        verdict: "send back",
        review: {
          high: "If I'd signed that, we'd have certified a model that failed fairness testing. Great review.",
          mid: "You found some issues, but one still made it through. In audit, one is enough to fail.",
          low: "This summary would have passed a failed model. Always check AI drafts against the evidence.",
        },
      },
    ],
  },
  {
    roleId: "finance-automation",
    title: "Finance Automation Specialist",
    setting: "Wednesday 09:30 · Week 1 · Shared-services centre",
    welcome: { from: "Jason Tan", text: "Morning! Bank reconciliation eats the team's whole Wednesday. Let's automate it." },
    tasks: [
      {
        id: "matcher",
        tool: "code",
        title: "Build the matching rule",
        competency: "Automation logic",
        gap: "Python",
        minutes: 8,
        from: "Jason Tan",
        fromRole: "AP Lead",
        subject: "Auto-match rule for bank recon",
        brief: "Can you write the rule that decides when a bank line matches a ledger line? Banks post a few days late, and anything with a fee deducted must go to a person, not get auto-matched.",
        requirements: [
          "Match only when the amount is exactly the same",
          "…and the dates are at most 3 days apart (either way)",
          "Click Run tests to check your rule against real cases",
        ],
        fn: "isMatch",
        helpers: [
          {
            signature: "daysBetween(a, b)",
            source: "function daysBetween(a, b) { return Math.round(Math.abs(new Date(b) - new Date(a)) / 86400000); }",
          },
        ],
        starter: `// ledger: { ref: "INV-1042", date: "2026-10-02", amount: 12500 }
// bank:   { date: "2026-10-04", amount: 12500 }
// Return true when the bank line should auto-match the ledger line.

function isMatch(ledger, bank) {
  const days = daysBetween(ledger.date, bank.date);

  return false;
}
`,
        tests: [
          { label: "Bank posts 2 days later", args: [{ ref: "INV-1042", date: "2026-10-02", amount: 12500 }, { date: "2026-10-04", amount: 12500 }], expected: true },
          { label: "Bank posts 3 days later", args: [{ ref: "INV-1043", date: "2026-10-02", amount: 8320.5 }, { date: "2026-10-05", amount: 8320.5 }], expected: true },
          { label: "Bank fee deducted", args: [{ ref: "INV-1051", date: "2026-10-03", amount: 4100 }, { date: "2026-10-04", amount: 4085 }], expected: false },
          { label: "9 days apart", args: [{ ref: "INV-1060", date: "2026-10-06", amount: 2250 }, { date: "2026-10-15", amount: 2250 }], expected: false },
          { label: "Across month end", args: [{ ref: "INV-0998", date: "2026-09-30", amount: 5600 }, { date: "2026-10-02", amount: 5600 }], expected: true },
          { label: "Bank posts a day early", args: [{ ref: "INV-1071", date: "2026-10-08", amount: 990 }, { date: "2026-10-07", amount: 990 }], expected: true },
        ],
        review: {
          high: "All cases pass, including the month-end one. I'll schedule it for tonight's run.",
          mid: "It handles the easy cases, but a few would get mismatched. Those are what auditors find.",
          low: "This rule isn't safe to run yet. Let's pair on it this afternoon.",
        },
      },
      {
        id: "business-case",
        tool: "sheet",
        title: "Make the business case",
        competency: "Measuring impact",
        gap: "Process automation",
        minutes: 5,
        from: "Priya Nair",
        fromRole: "Finance Manager",
        subject: "Is this worth it?",
        brief: "Before I approve rolling this out, show me what it saves. Fill in the pilot numbers and a year-2 scenario.",
        requirements: [
          "Auto-matched lines = bank lines × match rate",
          "Hours saved = auto-matched × minutes per line ÷ 60",
          "Saving = hours saved × cost per hour",
          "Tip: start a cell with = to write a formula, e.g. =B2*C2",
        ],
        sheet: {
          name: "recon_business_case.xlsx",
          columns: [
            { label: "Scenario", fmt: "text" },
            { label: "Bank lines / mo", fmt: "num" },
            { label: "Match rate", fmt: "pct" },
            { label: "Auto-matched", fmt: "num" },
            { label: "Mins per line", fmt: "num" },
            { label: "Hours saved / mo", fmt: "num" },
            { label: "Cost / hour (RM)", fmt: "rm" },
            { label: "Saving / mo (RM)", fmt: "rm" },
          ],
          rows: [
            ["Pilot", "2,400", "78%", { expect: 1872 }, "4", { expect: 124.8 }, "45", { expect: 5616 }],
            ["Year 2", "2,600", "90%", { expect: 2340 }, "4", { expect: 156 }, "47", { expect: 7332 }],
          ],
        },
        review: {
          high: "RM5.6k a month in the pilot, more in year 2. Approved. Good work making the case in numbers.",
          mid: "The direction is right, but some figures don't add up. I can't take this to the director yet.",
          low: "I can't follow how these numbers were built. Let's redo it together.",
        },
      },
      {
        id: "ai-agent",
        tool: "prompt",
        title: "Brief the workflow agent",
        competency: "Directing AI tools",
        gap: "Process automation",
        minutes: 5,
        aiName: "Workflow Agent",
        why: "AI agents can now build automations from a plain-language description. The specialist's job shifts from writing every step to describing the process precisely, including what should never be automated.",
        from: "Jason Tan",
        fromRole: "AP Lead",
        subject: "Let the agent build it",
        brief: "IT gave us access to an AI workflow agent. Describe the nightly bank reconciliation so it can build the automation. If you leave something out, it'll guess.",
        requirements: [
          "When it should run",
          "Where the data comes from (bank feed, ledger)",
          "The matching rule",
          "What happens to items that don't match",
        ],
        rubric: [
          { label: "When it runs", keywords: ["night", "daily", "every day", "schedule", "each day", "2am", "evening"] },
          { label: "Data sources", keywords: ["bank feed", "bank statement", "ledger", "sap", "erp"] },
          { label: "Matching rule", keywords: ["amount", "3 days", "three days", "date"] },
          { label: "Exceptions", keywords: ["exception", "flag", "unmatched", "manual", "review", "notify", "email"] },
        ],
        replies: {
          weak: {
            text: "I can build automations for you! What process would you like to automate, and which systems does it use?",
          },
          partial: {
            text: "Here's the workflow I've built:",
            steps: ["Download the bank statement", "Match each bank line to a ledger item", "Mark all matched items as cleared", "Done ✓"],
            note: "⚠ Nothing says what to do with unmatched items or how to match, so the agent chose for you. This version would clear items no one has checked.",
          },
          strong: {
            text: "Here's the workflow I've built from your description:",
            steps: [
              "Trigger: every night at 02:00",
              "Pull new lines from the bank feed and open items from the SAP ledger",
              "Match when the amount is identical and dates are within 3 days",
              "Clear matched pairs and write each match to the audit log",
              "Send unmatched items to the exception queue",
              "Email the AP team a summary at 08:00 with the exceptions to review",
            ],
            note: "Ready to run in test mode. Should I run it against last month's data first?",
          },
        },
        review: {
          high: "That's a workflow I'd trust in production: clear rule, audit log, and exceptions go to people.",
          mid: "It works, but the gaps would hurt us. Agents fill gaps with guesses.",
          low: "The agent had nothing to work with. Describe the process like you'd train a new joiner.",
        },
      },
      {
        id: "ai-code-review",
        tool: "review",
        title: "Review the AI's script",
        competency: "Verifying AI output",
        gap: "Python",
        minutes: 5,
        aiName: "Code Assistant",
        why: "AI now writes a lot of automation code. It usually runs, which makes its mistakes harder to spot. Reviewing AI code is becoming as important as writing it.",
        from: "Jason Tan",
        fromRole: "AP Lead",
        subject: "AI wrote a version, is it safe?",
        brief: "Someone asked the code assistant for a reconciliation script and wants to run it tonight. Review it line by line against our matching rule. Flag the risky lines, then approve or send it back.",
        requirements: [
          "Our rule: exact amount, dates within 3 days",
          "Unmatched items must go to a person",
          "Click a line to flag it",
          "Then approve it or send it back",
        ],
        artifactName: "reconcile.js (AI generated)",
        format: "code",
        source: {
          title: "Team matching policy",
          columns: ["Rule", "Requirement"],
          rows: [
            ["Amount", "Must match exactly"],
            ["Date", "Within 3 days either way"],
            ["Unmatched", "Go to the exception queue for review"],
          ],
        },
        segments: [
          { text: "function reconcile(ledgerItems, bankLines) {" },
          { text: "  const matched = [];" },
          { text: "  for (const item of ledgerItems) {" },
          {
            text: "    const line = bankLines.find((b) => Math.abs(b.amount - item.amount) < 50);",
            issue: "A RM50 tolerance auto-matches lines with fees deducted. The rule says amounts must match exactly.",
          },
          { text: "    if (line) {" },
          { text: "      matched.push({ ref: item.ref, bankId: line.id });" },
          {
            text: "      // date check removed to improve match rate",
            issue: "The date window was dropped on purpose, so an old payment could match a new invoice.",
          },
          { text: "    }" },
          { text: "  }" },
          {
            text: "  return matched; // unmatched items are discarded",
            issue: "Unmatched items are thrown away silently instead of going to the exception queue.",
          },
          { text: "}" },
        ],
        verdict: "send back",
        review: {
          high: "All three problems caught. That script would have 'improved' our match rate by clearing the wrong things.",
          mid: "Good start, but one risky line was missed. AI code needs a full review before it touches the ledger.",
          low: "This would have gone live and silently mismatched payments. Read AI code like you'd read a junior's.",
        },
      },
    ],
  },
  {
    roleId: "esg-reporting",
    title: "ESG Reporting Analyst",
    setting: "Monday 09:00 · Week 1 · Sustainability office",
    welcome: { from: "Nurul Aina", text: "Hi! The board pack closes Friday and our Scope 2 number looks odd. Can you dig in? 🙏" },
    tasks: [
      {
        id: "scope2",
        tool: "sheet",
        title: "Recalculate Scope 2",
        competency: "Emissions accounting",
        gap: "GHG accounting",
        minutes: 6,
        from: "Nurul Aina",
        fromRole: "Head of Sustainability",
        subject: "Scope 2 more than doubled?",
        brief: "Electricity emissions more than doubled, but usage barely changed. Recalculate what we reported, then the corrected figure using the national grid factor of 0.585 kgCO₂e/kWh.",
        requirements: [
          "tCO₂e = kWh × factor ÷ 1000",
          "Reported uses the factor in the file; corrected uses 0.585",
          "Fill in both totals",
          "Tip: start a cell with = to write a formula, e.g. =B2*C2/1000",
        ],
        sheet: {
          name: "scope2_electricity_2026.xlsx",
          columns: [
            { label: "Site", fmt: "text" },
            { label: "kWh 2026", fmt: "num" },
            { label: "Factor used", fmt: "text" },
            { label: "Reported tCO₂e", fmt: "num" },
            { label: "Correct factor", fmt: "text" },
            { label: "Corrected tCO₂e", fmt: "num" },
          ],
          rows: [
            ["Shah Alam plant", "1,230,000", "0.585", { expect: 719.55 }, "0.585", { expect: 719.55 }],
            ["Penang plant", "790,000", "0.585", { expect: 462.15 }, "0.585", { expect: 462.15 }],
            ["KL headquarters", "410,000", "5.85", { expect: 2398.5 }, "0.585", { expect: 239.85 }],
            ["Total", "", "", { expect: 3580.2 }, "", { expect: 1421.55 }],
          ],
        },
        review: {
          high: "That's it: KL HQ had the factor 10× too high. Corrected total checks out. You just saved us a public restatement.",
          mid: "You're on the right track, but some totals don't reconcile. Auditors will check every one of these.",
          low: "The recalculation isn't right yet. Let's go through the formula together.",
        },
      },
      {
        id: "validation",
        tool: "calendar",
        title: "Validate with the sites",
        competency: "Stakeholder coordination",
        minutes: 4,
        from: "Nurul Aina",
        fromRole: "Head of Sustainability",
        subject: "Sites must confirm before sign-off",
        brief: "Before I sign off, the three site managers need to confirm their meter data on one call by Thursday. Then book my sign-off, which must be done before the pack closes Friday 10:00.",
        requirements: [
          "Validation call: Hafiz, Mei Chen and Arun, finished by end of Thursday",
          "Sign-off with Nurul, after the call, finished by Fri 10:00",
          "Shaded slots show when attendees are busy",
        ],
        days: WEEK,
        hours: HOURS,
        busy: {
          Hafiz: [[9, 10, 11, 12, 13, 14, 15, 16], [9, 10, 11], [14, 15, 16], [9, 10, 11, 12], []],
          "Mei Chen": [[], [13, 14, 15, 16], [9, 10, 11], [13, 14, 15, 16], []],
          Arun: [[], [12], [13], [9, 10, 14], []],
          Nurul: [[], [], [13, 14, 15, 16], [9, 10, 11, 12, 13, 14, 15], []],
        },
        events: [
          { id: "call", title: "Site data validation", people: ["Hafiz", "Mei Chen", "Arun"], deadline: { day: 3, hour: 17, label: "Thu 17:00" } },
          { id: "signoff", title: "Sign-off with Nurul", people: ["Nurul"], deadline: { day: 4, hour: 10, label: "Fri 10:00" }, after: "call" },
        ],
        review: {
          high: "All three sites confirmed, and sign-off was done before the pack closed. Smooth.",
          mid: "One of these slots doesn't work. Check who's free and the order.",
          low: "These don't line up with people's calendars or the deadline.",
        },
      },
      {
        id: "ai-extract",
        tool: "prompt",
        title: "Extract data with document AI",
        competency: "Directing AI tools",
        minutes: 5,
        aiName: "Document AI",
        why: "Sustainability teams are using document AI to read hundreds of utility bills instead of typing them in. It's fast, but only as good as the instructions on what to extract and how.",
        from: "Nurul Aina",
        fromRole: "Head of Sustainability",
        subject: "36 utility bills to process",
        brief: "I've uploaded all 36 electricity bills for 2026 (three sites, 12 months) to the document AI. Get it to pull out what we need for Scope 2. Be specific or it'll give us a mess.",
        requirements: [
          "Say what the documents are",
          "Say exactly which field to extract (and in what unit)",
          "Say the period to cover",
          "Ask for a clear output, e.g. a table by site",
        ],
        rubric: [
          { label: "What the documents are", keywords: ["bill", "invoice", "utility", "electricity"] },
          { label: "Field and unit", keywords: ["kwh", "consumption", "usage"] },
          { label: "Period", keywords: ["2026", "month", "jan", "year", "period", "12"] },
          { label: "Output format", keywords: ["table", "by site", "per site", "each site", "column", "csv"] },
        ],
        replies: {
          weak: {
            text: "I found 36 documents. They appear to be electricity bills from three locations. What would you like me to do with them?",
          },
          partial: {
            text: "Here's what I extracted from the bills:",
            table: {
              columns: ["Site", "Value"],
              rows: [
                ["Shah Alam plant", "102,500"],
                ["Penang plant", "65.8 MWh"],
                ["KL headquarters", "RM 18,240"],
              ],
            },
            note: "⚠ Mixed units: one site gave kWh for a single month, one MWh, one the bill amount in RM. The brief didn't say which field or period.",
          },
          strong: {
            text: "Electricity consumption (kWh), Jan–Dec 2026, by site:",
            table: {
              columns: ["Site", "kWh 2026", "Bills read", "Confidence"],
              rows: [
                ["Shah Alam plant", "1,230,000", "12 / 12", "High"],
                ["Penang plant", "790,000", "12 / 12", "High"],
                ["KL headquarters", "410,000", "11 / 12", "⚠ Check"],
              ],
            },
            note: "The KL HQ December bill is missing, so I estimated it from November (33,800 kWh). Please confirm before this goes into the report.",
          },
        },
        review: {
          high: "Clean, in kWh, by site, and it flagged the missing bill. That saved us two days of typing.",
          mid: "Some of it's usable, but the mixed results mean we'd have to redo part of it by hand.",
          low: "The AI didn't know what we wanted. Spell out field, unit, period and format.",
        },
      },
      {
        id: "ai-disclosure",
        tool: "review",
        title: "Check the AI's disclosure",
        competency: "Verifying AI output",
        gap: "Sustainability standards",
        minutes: 5,
        aiName: "Report Writer",
        why: "AI can draft sustainability disclosures quickly, but it tends to reach for impressive claims. Unsupported green claims are a growing legal and reputational risk.",
        from: "Nurul Aina",
        fromRole: "Head of Sustainability",
        subject: "AI draft: Scope 2 disclosure",
        brief: "The report writer drafted our Scope 2 disclosure for the annual report. Check every claim against our data. Flag anything we can't stand behind, then approve or send it back.",
        requirements: [
          "Click a sentence to flag it",
          "Check each figure and claim against the data",
          "Watch for greenwashing: claims bigger than the evidence",
          "Then approve it or send it back",
        ],
        artifactName: "Annual report: Scope 2 disclosure (AI draft)",
        format: "prose",
        source: {
          title: "Your verified data",
          columns: ["Item", "Value"],
          rows: [
            ["Scope 2, 2025", "1,404 tCO₂e"],
            ["Scope 2, 2026 (corrected)", "1,422 tCO₂e (+1.3%)"],
            ["Renewable electricity share", "0%"],
            ["Carbon offsets bought", "500 t, not yet verified"],
          ],
        },
        segments: [
          { text: "In 2026 our Scope 2 emissions were 1,422 tCO₂e, broadly flat on 2025." },
          {
            text: "This represents a 15% reduction, driven by our energy-efficiency programme.",
            issue: "Emissions rose 1.3%; there was no 15% reduction, and no programme is in the data.",
          },
          {
            text: "All three sites are powered by 100% renewable electricity.",
            issue: "The data says 0% renewable electricity.",
          },
          {
            text: "Through verified carbon offsets, the group is now carbon neutral.",
            issue: "The offsets aren't verified, and 500 t doesn't cover 1,422 t. A textbook greenwashing claim.",
          },
          { text: "A data-validation control was introduced after an emission-factor error at KL headquarters was corrected." },
        ],
        verdict: "send back",
        review: {
          high: "Three claims we couldn't defend, all caught. You just kept us out of a greenwashing headline.",
          mid: "Good catches, but one false claim survived. In a published report, that's the one people find.",
          low: "This would have published claims we can't support. AI drafts need fact-checking line by line.",
        },
      },
    ],
  },
];
