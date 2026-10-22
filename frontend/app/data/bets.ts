export type Signal = "Act now" | "Emerging" | "Stable" | "Watch" | "Declining" | "Stalled";

export type Step = {
  skill: string;
  title: string;
  provider: string;
  url: string;
  hours: number;
  cost: "Free" | "Free to audit" | "Low-cost";
  why: string;
  signal: Signal;
};

export type Role = {
  id: string;
  title: string;
  summary: string;
  match: number;
  /** the role's demand on the Signal Ladder; null when no snapshot has measured it */
  signal: Signal | null;
  sdg?: { goal: string; reason: string };
  have: string[];
  gaps: string[];
  steps: Step[];
};

export type Opening = {
  title: string;
  employer: string;
  location: string;
  mode: "On-site" | "Hybrid" | "Remote";
  salary: string;
  posted: string;
  matched: string[];
};

export type Bet = Role & {
  sdg: { goal: string; reason: string };
  kind: "Stay and strengthen" | "Safest switch" | "Fastest-growing" | "Biggest impact";
  note: string;
  /** share of the role's tasks AI could take over within 5 years */
  aiRisk: number;
  /** year-on-year change in Malaysian job postings */
  growth: number;
  /** postings index for the last six quarters, oldest first */
  trend: number[];
  /** sample openings for the demo; the live product fills these from ingested postings */
  openings: Opening[];
  /** what `growth` and `trend` measure (default: postings year on year) */
  trendNote?: string;
};

// Demo data for the synthetic persona (Aisyah). Resource links checked 20 Oct 2026.

/** Best fit from the user's CV alone. */
export const cvMatch: Role = {
  id: "fpa-analyst",
  title: "FP&A Analyst",
  summary: "Plan budgets, build forecasts and explain the numbers behind business decisions.",
  match: 78,
  signal: "Stable",
  sdg: { goal: "SDG 8", reason: "Decent work and economic growth through sound financial planning." },
  have: ["Excel", "Month-end close", "Reconciliation", "SAP"],
  gaps: ["Financial modelling", "Forecasting", "Power BI"],
  steps: [
    {
      skill: "Financial modelling",
      title: "Excel Skills for Business",
      provider: "Macquarie University · Coursera",
      url: "https://www.coursera.org/specializations/excel",
      hours: 24,
      cost: "Free to audit",
      why: "Builds on your reconciliation work; modelling is essential for 9 in 10 FP&A postings.",
      signal: "Stable",
    },
    {
      skill: "Forecasting",
      title: "Forecasting: Principles and Practice",
      provider: "Hyndman & Athanasopoulos · OTexts",
      url: "https://otexts.com/fpp3/",
      hours: 20,
      cost: "Free",
      why: "Rolling forecasts are replacing static annual budgets in shared-services finance teams.",
      signal: "Emerging",
    },
    {
      skill: "Power BI",
      title: "Power BI learning paths",
      provider: "Microsoft Learn",
      url: "https://learn.microsoft.com/en-us/training/powerplatform/power-bi",
      hours: 12,
      cost: "Free",
      why: "Most-requested reporting tool in Malaysian finance job postings this quarter.",
      signal: "Act now",
    },
    {
      skill: "Portfolio",
      title: "Build a rolling forecast dashboard",
      provider: "Kaggle Datasets",
      url: "https://www.kaggle.com/datasets",
      hours: 8,
      cost: "Free",
      why: "Turns claimed skills into demonstrated ones that employers can see.",
      signal: "Stable",
    },
  ],
};

/** Careers ranked by market trend and AI replacement risk. */
export const bets: Bet[] = [
  {
    id: "ai-risk-controls",
    kind: "Safest switch",
    title: "AI Risk & Controls Analyst",
    note: "Low AI replacement risk; your audit trail habits transfer",
    summary: "Check that AI systems used in finance are accurate, fair and properly controlled.",
    match: 58,
    signal: "Emerging",
    aiRisk: 12,
    growth: 46,
    trend: [18, 22, 27, 31, 38, 44],
    openings: [
      { title: "AI Governance Analyst", employer: "Regional bank", location: "Kuala Lumpur", mode: "Hybrid", salary: "RM 6,500 – 9,000", posted: "2 days ago", matched: ["Reconciliation", "SAP"] },
      { title: "Model Risk & Controls Associate", employer: "Insurance group", location: "Petaling Jaya", mode: "On-site", salary: "RM 5,500 – 7,500", posted: "5 days ago", matched: ["Month-end close"] },
      { title: "Technology Risk Analyst (AI)", employer: "Big Four advisory firm", location: "Kuala Lumpur", mode: "Hybrid", salary: "RM 5,000 – 7,000", posted: "1 week ago", matched: ["Reconciliation"] },
      { title: "Internal Audit Associate, Data & AI", employer: "Listed conglomerate", location: "Cyberjaya", mode: "On-site", salary: "RM 4,800 – 6,500", posted: "2 weeks ago", matched: ["SAP", "Month-end close"] },
    ],
    sdg: { goal: "SDG 16", reason: "Strong institutions through accountable, well-governed AI." },
    have: ["Reconciliation", "Month-end close", "SAP"],
    gaps: ["AI fundamentals", "AI risk frameworks", "Responsible AI"],
    steps: [
      {
        skill: "AI fundamentals",
        title: "Elements of AI",
        provider: "University of Helsinki · MinnaLearn",
        url: "https://www.elementsofai.com/",
        hours: 30,
        cost: "Free",
        why: "Understand what AI can and cannot do before you assess it.",
        signal: "Stable",
      },
      {
        skill: "AI fundamentals",
        title: "AI For Everyone",
        provider: "DeepLearning.AI · Coursera",
        url: "https://www.coursera.org/learn/ai-for-everyone",
        hours: 6,
        cost: "Free to audit",
        why: "Short, non-technical view of how companies adopt AI.",
        signal: "Stable",
      },
      {
        skill: "AI risk frameworks",
        title: "AI Risk Management Framework",
        provider: "NIST",
        url: "https://www.nist.gov/itl/ai-risk-management-framework",
        hours: 8,
        cost: "Free",
        why: "The framework most AI governance job postings ask for by name.",
        signal: "Act now",
      },
      {
        skill: "Responsible AI",
        title: "Responsible AI business principles",
        provider: "Microsoft Learn",
        url: "https://learn.microsoft.com/en-us/training/paths/responsible-ai-business-principles/",
        hours: 4,
        cost: "Free",
        why: "Turns fairness and transparency principles into checks you can run.",
        signal: "Emerging",
      },
      {
        skill: "AI risk frameworks",
        title: "AI resources for auditors",
        provider: "ISACA",
        url: "https://www.isaca.org/resources/artificial-intelligence",
        hours: 6,
        cost: "Free",
        why: "Connects AI risk to the audit and controls language you already use.",
        signal: "Emerging",
      },
    ],
  },
  {
    id: "finance-automation",
    kind: "Fastest-growing",
    title: "Finance Automation Specialist",
    note: "Fastest-growing demand in Malaysian postings",
    summary: "Automate month-end close, reconciliation and reporting with scripts and workflow tools.",
    match: 61,
    signal: "Act now",
    aiRisk: 24,
    growth: 68,
    trend: [12, 15, 21, 29, 37, 48],
    openings: [
      { title: "Finance Automation Analyst", employer: "Shared-services centre", location: "Kuala Lumpur", mode: "Hybrid", salary: "RM 5,500 – 8,000", posted: "1 day ago", matched: ["Reconciliation", "Accounts payable", "SAP"] },
      { title: "RPA Developer, Finance", employer: "Global business services hub", location: "Cyberjaya", mode: "On-site", salary: "RM 6,000 – 9,000", posted: "3 days ago", matched: ["Accounts payable"] },
      { title: "Finance Systems & Automation Associate", employer: "Manufacturing MNC", location: "Penang", mode: "On-site", salary: "RM 4,500 – 6,500", posted: "6 days ago", matched: ["SAP", "Excel"] },
      { title: "Process Automation Specialist (Power Platform)", employer: "Fintech startup", location: "Remote, Malaysia", mode: "Remote", salary: "RM 7,000 – 10,000", posted: "2 weeks ago", matched: ["Excel"] },
    ],
    sdg: { goal: "SDG 9", reason: "Industry, innovation and infrastructure through process modernisation." },
    have: ["Reconciliation", "Accounts payable", "Excel", "SAP"],
    gaps: ["SQL", "Python", "Process automation"],
    steps: [
      {
        skill: "SQL",
        title: "Interactive SQL lessons",
        provider: "SQLBolt",
        url: "https://sqlbolt.com/",
        hours: 6,
        cost: "Free",
        why: "Pull ledger data yourself instead of waiting for exports.",
        signal: "Act now",
      },
      {
        skill: "Python",
        title: "Python",
        provider: "Kaggle Learn",
        url: "https://www.kaggle.com/learn/python",
        hours: 5,
        cost: "Free",
        why: "The base layer for every automation tool on this route.",
        signal: "Act now",
      },
      {
        skill: "Python",
        title: "Pandas",
        provider: "Kaggle Learn",
        url: "https://www.kaggle.com/learn/pandas",
        hours: 4,
        cost: "Free",
        why: "Reconcile thousands of rows in seconds, the core of your current role, automated.",
        signal: "Act now",
      },
      {
        skill: "Process automation",
        title: "Power Automate learning paths",
        provider: "Microsoft Learn",
        url: "https://learn.microsoft.com/en-us/training/powerplatform/power-automate",
        hours: 10,
        cost: "Free",
        why: "Low-code automation already used in most shared-services centres.",
        signal: "Emerging",
      },
      {
        skill: "Process automation",
        title: "RPA developer foundations",
        provider: "UiPath Academy",
        url: "https://academy.uipath.com/",
        hours: 15,
        cost: "Free",
        why: "RPA roles are climbing the Signal Ladder from global to local demand.",
        signal: "Emerging",
      },
    ],
  },
  {
    id: "esg-reporting",
    kind: "Biggest impact",
    title: "ESG Reporting Analyst",
    note: "Best fit with the goals you selected",
    summary: "Measure and report a company's emissions and sustainability performance.",
    match: 54,
    signal: "Emerging",
    aiRisk: 18,
    growth: 39,
    trend: [20, 23, 25, 30, 34, 39],
    openings: [
      { title: "ESG Reporting Analyst", employer: "Listed property developer", location: "Kuala Lumpur", mode: "Hybrid", salary: "RM 5,000 – 7,500", posted: "3 days ago", matched: ["Reconciliation", "Excel"] },
      { title: "Sustainability Data Associate", employer: "Palm oil plantation group", location: "Shah Alam", mode: "On-site", salary: "RM 4,500 – 6,000", posted: "4 days ago", matched: ["Excel"] },
      { title: "Carbon Accounting Analyst", employer: "Energy company", location: "Kuala Lumpur", mode: "Hybrid", salary: "RM 6,000 – 8,500", posted: "1 week ago", matched: ["Reconciliation", "Month-end close"] },
      { title: "Sustainability Reporting Executive", employer: "Logistics group", location: "Port Klang", mode: "On-site", salary: "RM 4,000 – 5,500", posted: "3 weeks ago", matched: ["Month-end close"] },
    ],
    sdg: { goal: "SDG 13", reason: "Climate action through accurate emissions disclosure." },
    have: ["Reconciliation", "Excel", "Month-end close"],
    gaps: ["GHG accounting", "Sustainability standards", "Data visualisation"],
    steps: [
      {
        skill: "GHG accounting",
        title: "GHG Protocol Corporate Standard",
        provider: "GHG Protocol",
        url: "https://ghgprotocol.org/corporate-standard",
        hours: 10,
        cost: "Free",
        why: "The method behind almost every corporate emissions report.",
        signal: "Emerging",
      },
      {
        skill: "Sustainability standards",
        title: "GRI Academy",
        provider: "Global Reporting Initiative",
        url: "https://www.globalreporting.org/reporting-support/education/gri-academy/",
        hours: 12,
        cost: "Low-cost",
        why: "GRI is the most widely used sustainability reporting framework.",
        signal: "Emerging",
      },
      {
        skill: "Sustainability standards",
        title: "ISSB knowledge hub",
        provider: "IFRS Foundation",
        url: "https://www.ifrs.org/sustainability/knowledge-hub/",
        hours: 6,
        cost: "Free",
        why: "ISSB disclosure is being phased in for listed companies; your accounting base transfers directly.",
        signal: "Act now",
      },
      {
        skill: "Data visualisation",
        title: "Data Visualization",
        provider: "Kaggle Learn",
        url: "https://www.kaggle.com/learn/data-visualization",
        hours: 4,
        cost: "Free",
        why: "Sustainability reports live or die by clear charts.",
        signal: "Stable",
      },
    ],
  },
];

/** Skill names used on screen -> concept ids in pipeline/curated/concepts.csv. */
export const conceptIds: Record<string, string> = {
  Excel: "excel",
  "Month-end close": "month-end-close",
  Reconciliation: "reconciliation",
  "Accounts payable": "accounts-payable",
  SAP: "sap-erp",
  "Financial modelling": "financial-modelling",
  Forecasting: "forecasting",
  "Power BI": "power-bi",
  "Data visualisation": "data-visualisation",
  SQL: "sql",
  Python: "python",
  "Process automation": "process-automation",
  "AI fundamentals": "ai-fundamentals",
  "AI risk frameworks": "ai-risk-frameworks",
  "Responsible AI": "responsible-ai",
  "GHG accounting": "ghg-accounting",
  "Sustainability standards": "sustainability-standards",
};

const ids = (names: string[]) => [...new Set(names.map((n) => conceptIds[n]).filter(Boolean))];

/** Aisyah's profile as the live feed sees it. */
export const profile = {
  skills: ids(["Excel", "Month-end close", "Reconciliation", "Accounts payable", "SAP"]).map((id) => ({ id })),
  route: ids([cvMatch, ...bets].flatMap((r) => r.gaps)),
  // AI capabilities that reach her tasks; the Mirror will supply these once it exists
  exposed: ["document-ai", "reconciliation-automation", "report-generation", "tabular-forecasting"],
};

/** Verified courses by concept id, gathered from the sample roles' roadmaps. */
export const resources: Record<string, Step[]> = {};
for (const step of [cvMatch, ...bets].flatMap((r) => r.steps)) {
  const id = conceptIds[step.skill];
  if (id && !(resources[id] ?? []).some((s) => s.url === step.url)) (resources[id] ??= []).push(step);
}

export function riskLabel(risk: number) {
  return risk < 20 ? "Low" : risk < 35 ? "Low – Moderate" : risk < 55 ? "Moderate" : "High";
}

export function jobSearchLinks(role: string) {
  const q = encodeURIComponent(role);
  return [
    { name: "LinkedIn", url: `https://www.linkedin.com/jobs/search/?keywords=${q}&location=Malaysia` },
    { name: "JobStreet", url: `https://my.jobstreet.com/${role.replace(/[^A-Za-z0-9]+/g, "-")}-jobs` },
    { name: "Hiredly", url: `https://www.hiredly.com/jobs?keyword=${q}` },
    { name: "MYFutureJobs", url: "https://myfuturejobs.gov.my/" },
  ];
}
