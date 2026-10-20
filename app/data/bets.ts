export type Signal = "Act now" | "Emerging" | "Stable" | "Watch";

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

export type Bet = {
  id: string;
  kind: "Safe Bet" | "Rising Bet" | "Impact Bet";
  title: string;
  note: string;
  summary: string;
  match: number;
  signal: Signal;
  sdg: { goal: string; reason: string };
  have: string[];
  gaps: string[];
  steps: Step[];
};

// Demo data for the synthetic persona (Aisyah). Resource links checked 20 Oct 2026.
export const bets: Bet[] = [
  {
    id: "fpa-analyst",
    kind: "Safe Bet",
    title: "FP&A Analyst",
    note: "Key skills hold up under both scenarios",
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
  },
  {
    id: "finance-automation",
    kind: "Rising Bet",
    title: "Finance Automation Specialist",
    note: "Fastest-growing demand in Malaysian postings",
    summary: "Automate month-end close, reconciliation and reporting with scripts and workflow tools.",
    match: 61,
    signal: "Act now",
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
    kind: "Impact Bet",
    title: "ESG Reporting Analyst",
    note: "Best fit with the goals you selected",
    summary: "Measure and report a company's emissions and sustainability performance.",
    match: 54,
    signal: "Emerging",
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
