"use client";

import CvFlow, { EmptyFlow } from "./CvFlow";
import { useProfile } from "./Profile";

/** Section 01: the reading flow for an uploaded resume (live, or finished when restored), else the same stages, empty. */
export default function ProfilePanel() {
  const { source, cv, scan, lines } = useProfile();

  if (scan) return <CvFlow key={scan.name} fileName={scan.name} lines={scan.lines} read={scan.read} cv={scan.result} animate />;

  if (source === "cv" && cv) return <CvFlow fileName={cv.file ?? "Your resume"} lines={lines ?? null} read={null} cv={cv} animate={false} />;

  return <EmptyFlow />;
}
