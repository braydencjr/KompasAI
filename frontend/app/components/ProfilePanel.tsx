"use client";

import { cvMatch } from "../data/bets";
import CvFlow from "./CvFlow";
import CvMatch from "./CvMatch";
import { useProfile } from "./Profile";

/** Section 01: the reading flow for an uploaded CV (live, or finished when restored), else the sample profile. */
export default function ProfilePanel() {
  const { source, cv, scan, lines } = useProfile();

  if (scan) return <CvFlow key={scan.name} fileName={scan.name} lines={scan.lines} cv={scan.result} animate />;

  if (source === "cv" && cv) return <CvFlow fileName={cv.file ?? "Your CV"} lines={lines ?? null} cv={cv} animate={false} />;

  return <CvMatch role={cvMatch} origin={<span className="chip chip-origin">Sample profile · Aisyah</span>} />;
}
