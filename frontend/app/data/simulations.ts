// Work simulations: three short, realistic moments from each role.
// Scenarios are written from the role's core tasks; all names, companies and figures are fictional.

type TaskBase = {
  /** what this moment exercises, shown on the result screen */
  skill: string;
  /** roadmap skill gap this moment maps to, if any */
  gap?: string;
};

export type DataTask = TaskBase & {
  kind: "data";
  from: string;
  fromRole: string;
  subject: string;
  body: string;
  file: { name: string; columns: string[]; rows: string[][] };
  question: string;
  options: { text: string; correct: boolean; feedback: string }[];
};

export type WriteTask = TaskBase & {
  kind: "write";
  from: string;
  fromRole: string;
  subject: string;
  body: string;
  prompt: string;
  checklist: { label: string; keywords: string[] }[];
  sample: string;
};

export type ChoiceTask = TaskBase & {
  kind: "choice";
  from: string;
  fromRole: string;
  message: string;
  options: { text: string; score: 0 | 1 | 2; feedback: string }[];
};

export type SimTask = DataTask | WriteTask | ChoiceTask;

export type Simulation = {
  roleId: string;
  title: string;
  setting: string;
  minutes: number;
  welcome: { from: string; text: string };
  tasks: [SimTask, SimTask, SimTask];
};

export type SimResult = {
  can: number;
  want: number;
  quadrant: Quadrant;
  weakest?: { skill: string; gap?: string };
  at: string;
};

export type Quadrant = "Strong fit" | "Capable, may burn out" | "Learnable" | "Probably not for you";

export const FIT_THRESHOLD = 60;

export function quadrantOf(can: number, want: number): Quadrant {
  if (can >= FIT_THRESHOLD) return want >= FIT_THRESHOLD ? "Strong fit" : "Capable, may burn out";
  return want >= FIT_THRESHOLD ? "Learnable" : "Probably not for you";
}

export function checkWriting(task: WriteTask, text: string) {
  const t = text.toLowerCase();
  return task.checklist.map((c) => c.keywords.some((k) => t.includes(k)));
}

/** 0–1 score for one task */
export function scoreTask(task: SimTask, answer: { choice: number | null; text: string }) {
  if (task.kind === "write") {
    const hits = checkWriting(task, answer.text);
    return hits.filter(Boolean).length / hits.length;
  }
  if (answer.choice === null) return 0;
  if (task.kind === "data") return task.options[answer.choice].correct ? 1 : 0;
  return task.options[answer.choice].score / 2;
}

export const simulations: Simulation[] = [
  {
    roleId: "fpa-analyst",
    title: "FP&A Analyst",
    setting: "Monday 09:00 · Week 1 · Group finance",
    minutes: 15,
    welcome: { from: "Farid Hassan", text: "Welcome aboard! 👋 Could you look at my email about Marketing first? I need it before my 11am." },
    tasks: [
      {
        kind: "data",
        skill: "Variance analysis",
        gap: "Financial modelling",
        from: "Farid Hassan",
        fromRole: "CFO",
        subject: "Marketing 18% over budget?",
        body: "Hi, Marketing is showing roughly 18% over budget for Q3. Before I raise it with the CEO, can you check whether any of it looks like a booking error rather than real spend?",
        file: {
          name: "marketing_budget_Q3.xlsx",
          columns: ["Month", "Line item", "Budget (RM)", "Actual (RM)", "Variance"],
          rows: [
            ["Jul", "Digital ads", "40,000", "39,200", "−800"],
            ["Jul", "Events", "30,000", "28,500", "−1,500"],
            ["Jul", "Agency fees", "25,000", "25,000", "0"],
            ["Aug", "Digital ads", "40,000", "41,100", "+1,100"],
            ["Aug", "Events", "30,000", "31,800", "+1,800"],
            ["Aug", "Agency fees", "25,000", "50,000", "+25,000"],
            ["Sep", "Digital ads", "40,000", "64,000", "+24,000"],
            ["Sep", "Events", "30,000", "31,400", "+1,400"],
            ["Sep", "Agency fees", "25,000", "25,000", "0"],
          ],
        },
        question: "Which line should you flag as a likely booking error, not real spend?",
        options: [
          {
            text: "September digital ads (+RM24,000)",
            correct: false,
            feedback: "It's big, but campaign spend genuinely varies month to month. That's a question for Marketing, not an error.",
          },
          {
            text: "August agency fees (+RM25,000)",
            correct: true,
            feedback: "Exactly double a fee that's flat every other month: the classic sign of one invoice posted twice.",
          },
          {
            text: "August events (+RM1,800)",
            correct: false,
            feedback: "Too small to explain the gap, and within normal month-to-month noise.",
          },
        ],
      },
      {
        kind: "write",
        skill: "Explaining numbers to leaders",
        from: "Farid Hassan",
        fromRole: "CFO",
        subject: "Re: Marketing 18% over budget?",
        body: "Good catch. Can you send me 2–3 lines I can forward straight to the CEO?",
        prompt: "Write your reply to Farid",
        checklist: [
          { label: "States the size of the overspend", keywords: ["51", "18%", "18 %", "18 per"] },
          { label: "Flags the duplicate invoice", keywords: ["duplicate", "twice", "double", "two times"] },
          { label: "Mentions the real campaign spend", keywords: ["campaign", "digital", "ads", "september", "sep "] },
          { label: "Says what happens next", keywords: ["revers", "correct", "fix", "credit", "confirm", "follow", "will "] },
        ],
        sample:
          "Marketing is about RM51k (18%) over budget for Q3. RM25k of that is an August agency invoice booked twice, which we're reversing this week. The rest is September's digital campaign (+RM24k); I'm confirming with Marketing that it was approved.",
      },
      {
        kind: "choice",
        skill: "Forecasting judgement",
        gap: "Forecasting",
        from: "Mei Ling",
        fromRole: "Sales Director",
        message: "Q4 is going to be huge 🚀 can you bump the revenue forecast up 30%? Leadership meeting at 2pm.",
        options: [
          {
            text: "Done, I've updated it to +30%.",
            score: 0,
            feedback: "Fast and friendly, but a forecast nobody can back up costs you trust when it misses. FP&A owns the numbers.",
          },
          {
            text: "Love the optimism! Can you share the deals behind it? I'll include what the pipeline supports and show the rest as an upside scenario.",
            score: 2,
            feedback: "This is the job: keep Sales on side, ask for evidence, and use scenarios instead of a single guess.",
          },
          {
            text: "Sorry, forecasts aren't changed on request.",
            score: 1,
            feedback: "Right instinct, but shutting Sales out means losing information they genuinely have.",
          },
        ],
      },
    ],
  },
  {
    roleId: "ai-risk-controls",
    title: "AI Risk & Controls Analyst",
    setting: "Tuesday 10:00 · Week 1 · Model risk team",
    minutes: 15,
    welcome: { from: "Ahmad Razak", text: "Hi, welcome to the team! The loan model review in my email is today's priority." },
    tasks: [
      {
        kind: "data",
        skill: "Model review",
        gap: "AI risk frameworks",
        from: "Ahmad Razak",
        fromRole: "Head of Risk",
        subject: "Loan approval model: ready to sign off?",
        body: "The new loan approval model passed accuracy testing (91%). Before we sign off, have a look at the approval-rate breakdown from the pilot.",
        file: {
          name: "pilot_approvals_by_group.csv",
          columns: ["Applicant group", "Applications", "Approved", "Approval rate"],
          rows: [
            ["Salaried", "4,200", "2,940", "70%"],
            ["Government", "900", "720", "80%"],
            ["Self-employed", "1,100", "330", "30%"],
            ["Gig workers", "600", "90", "15%"],
          ],
        },
        question: "What should you raise before sign-off?",
        options: [
          {
            text: "Nothing: 91% accuracy is well above the threshold, so sign off.",
            correct: false,
            feedback: "High overall accuracy can hide very different outcomes for different groups. That's exactly what a review is for.",
          },
          {
            text: "Gig and self-employed approval rates are far lower. Check whether the model penalises income type rather than ability to repay.",
            correct: true,
            feedback: "Right. A gap this large needs explaining before launch: it may be real risk, or the model may be learning a proxy.",
          },
          {
            text: "Government approvals are too high; tighten them to match the others.",
            correct: false,
            feedback: "Lowering one group's rate to even things out doesn't fix the cause, and could reject good applicants.",
          },
        ],
      },
      {
        kind: "write",
        skill: "Writing for a risk committee",
        from: "Ahmad Razak",
        fromRole: "Head of Risk",
        subject: "Re: Loan approval model",
        body: "Agreed. Draft 2–3 lines for the model risk committee, please.",
        prompt: "Write your note to the committee",
        checklist: [
          { label: "Names the affected groups", keywords: ["gig", "self-employed", "self employed"] },
          { label: "Gives the numbers", keywords: ["15%", "30%", "70%", "80%", "15 %", "30 %"] },
          { label: "Explains the risk", keywords: ["fair", "bias", "discriminat", "penalis", "penaliz", "proxy"] },
          { label: "Recommends an action", keywords: ["test", "review", "investigat", "hold", "before", "check"] },
        ],
        sample:
          "The model is 91% accurate overall, but approves 15% of gig workers and 30% of self-employed applicants vs 70% of salaried. We recommend holding sign-off until we test whether income type is acting as a proxy for repayment ability.",
      },
      {
        kind: "choice",
        skill: "Holding a line under pressure",
        gap: "Responsible AI",
        from: "Kevin Lim",
        fromRole: "Product Owner",
        message: "We launch Friday and marketing's already booked. Can we sign off now and fix fairness in v2?",
        options: [
          { text: "OK, let's launch and fix it in v2.", score: 0, feedback: "Every declined applicant before v2 is affected. Risk's job is to make that cost visible." },
          {
            text: "We can launch Friday if declined gig and self-employed applications go to human review, and we retest in 30 days.",
            score: 2,
            feedback: "A control that lets the business move while protecting people. This is what good risk work looks like.",
          },
          { text: "No launch until it's fully fixed.", score: 1, feedback: "Safe, but with no path forward the business may route around you next time." },
        ],
      },
    ],
  },
  {
    roleId: "finance-automation",
    title: "Finance Automation Specialist",
    setting: "Wednesday 09:30 · Week 1 · Shared-services centre",
    minutes: 15,
    welcome: { from: "Jason Tan", text: "Morning! Bank recon is eating the team's whole Wednesday again. Can you take a look?" },
    tasks: [
      {
        kind: "data",
        skill: "Matching logic",
        gap: "SQL",
        from: "Jason Tan",
        fromRole: "AP Lead",
        subject: "Recon is off again",
        body: "These items didn't auto-match last night. We want a matching rule that clears as many as possible without creating false matches.",
        file: {
          name: "unmatched_items.csv",
          columns: ["Ref", "Ledger date", "Ledger (RM)", "Bank date", "Bank (RM)"],
          rows: [
            ["INV-1042", "02 Oct", "12,500.00", "04 Oct", "12,500.00"],
            ["INV-1043", "02 Oct", "8,320.50", "05 Oct", "8,320.50"],
            ["INV-1051", "03 Oct", "4,100.00", "04 Oct", "4,085.00"],
            ["INV-1060", "06 Oct", "2,250.00", "—", "—"],
          ],
        },
        question: "Which rule clears the most items safely?",
        options: [
          { text: "Exact amount and exact date", correct: false, feedback: "Bank dates lag the ledger by a few days, so this clears none of them." },
          {
            text: "Exact amount, date within ±3 days",
            correct: true,
            feedback: "Clears INV-1042 and INV-1043 safely. INV-1051 (bank fee) and INV-1060 (not yet paid) should go to a person.",
          },
          {
            text: "Amount within RM50, any date",
            correct: false,
            feedback: "Clears more today, but loose rules create false matches that are far harder to find later.",
          },
        ],
      },
      {
        kind: "write",
        skill: "Explaining automation",
        from: "Jason Tan",
        fromRole: "AP Lead",
        subject: "Re: Recon is off again",
        body: "Nice. Can you explain to the team in 2–3 lines what the script will and won't do? Some are nervous about it.",
        prompt: "Write your message to the AP team",
        checklist: [
          { label: "Says it matches on amount", keywords: ["amount"] },
          { label: "Mentions the date window", keywords: ["day", "±3", "window", "date"] },
          { label: "Exceptions still go to a person", keywords: ["review", "manual", "human", "you", "team", "exception", "flag"] },
          { label: "Names an exception (fee / unpaid)", keywords: ["fee", "unpaid", "not paid", "outstanding", "partial"] },
        ],
        sample:
          "The script only matches items where the amount is exact and the dates are within 3 days. Anything else, like bank fees or invoices not yet paid, is flagged for you to review, so nothing gets cleared without a person checking it.",
      },
      {
        kind: "choice",
        skill: "Automation with controls",
        gap: "Process automation",
        from: "Priya Nair",
        fromRole: "Finance Manager",
        message: "Can the bot just auto-approve every invoice under RM5k? We'd close two days faster.",
        options: [
          { text: "Sure, I'll set that up today.", score: 0, feedback: "Splitting a fraudulent invoice into RM4.9k pieces is one of the oldest tricks. Speed without controls is a risk." },
          {
            text: "Yes for known vendors with a matching PO, and we sample-check 5% each week.",
            score: 2,
            feedback: "You get most of the speed and keep a control. That balance is the core of this job.",
          },
          { text: "No, bots shouldn't approve anything.", score: 1, feedback: "Careful, but it leaves a real efficiency win on the table." },
        ],
      },
    ],
  },
  {
    roleId: "esg-reporting",
    title: "ESG Reporting Analyst",
    setting: "Thursday 14:00 · Week 1 · Sustainability office",
    minutes: 15,
    welcome: { from: "Nurul Aina", text: "Hi! The board pack closes tomorrow and our Scope 2 number looks odd. Email incoming 🙏" },
    tasks: [
      {
        kind: "data",
        skill: "Emissions data checks",
        gap: "GHG accounting",
        from: "Nurul Aina",
        fromRole: "Head of Sustainability",
        subject: "Scope 2 more than doubled?",
        body: "Our electricity emissions more than doubled this year, but usage barely changed. Can you find out why before this goes to the board?",
        file: {
          name: "scope2_electricity_2026.xlsx",
          columns: ["Site", "kWh 2025", "kWh 2026", "Factor used (kgCO₂e/kWh)"],
          rows: [
            ["Shah Alam plant", "1,200,000", "1,230,000", "0.585"],
            ["Penang plant", "800,000", "790,000", "0.585"],
            ["KL headquarters", "400,000", "410,000", "5.85"],
          ],
        },
        question: "What's causing the jump?",
        options: [
          { text: "Shah Alam used more electricity", correct: false, feedback: "Up only 2.5%, which can't double total emissions." },
          {
            text: "KL HQ's emission factor is 10× too high, a decimal error",
            correct: true,
            feedback: "5.85 instead of 0.585. One misplaced decimal multiplies that site's emissions tenfold.",
          },
          { text: "Malaysia's grid got dirtier this year", correct: false, feedback: "Then every site's factor would change, not just one." },
        ],
      },
      {
        kind: "write",
        skill: "Board reporting",
        gap: "Sustainability standards",
        from: "Nurul Aina",
        fromRole: "Head of Sustainability",
        subject: "Re: Scope 2 more than doubled?",
        body: "Phew. Write 2–3 lines for the board pack explaining the correction, please.",
        prompt: "Write the note for the board pack",
        checklist: [
          { label: "Names the cause", keywords: ["factor", "decimal", "typo", "error", "input"] },
          { label: "Names the site", keywords: ["kl", "hq", "headquarters", "kuala lumpur"] },
          { label: "Gives the corrected picture", keywords: ["flat", "stable", "unchanged", "similar", "in line", "roughly", "corrected"] },
          { label: "Adds a control", keywords: ["check", "review", "control", "prevent", "verify", "validation"] },
        ],
        sample:
          "The reported jump in Scope 2 emissions was caused by an emission-factor input error at KL headquarters (5.85 instead of 0.585). Corrected, Scope 2 is roughly flat year on year. We've added a factor check to the data review to prevent this recurring.",
      },
      {
        kind: "choice",
        skill: "Avoiding greenwashing",
        gap: "Sustainability standards",
        from: "Daniel Ong",
        fromRole: "Marketing",
        message: "We bought some carbon offsets this year. Can we say we're 'carbon neutral' in the annual report? 🌱",
        options: [
          { text: "Sure, offsets count.", score: 0, feedback: "Unverified neutrality claims are greenwashing and a growing legal and reputational risk." },
          {
            text: "Not yet. Let's state what we cut and what we offset, with numbers. 'Carbon neutral' needs a recognised standard and verification.",
            score: 2,
            feedback: "Honest, specific, and still gives Marketing a story to tell.",
          },
          { text: "No, we shouldn't mention offsets at all.", score: 1, feedback: "Too cautious: offsets can be disclosed transparently." },
        ],
      },
    ],
  },
];
