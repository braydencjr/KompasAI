/** Ranks catalogue jobs against what someone typed ("PR exec", "java engineer", "bookkeeper"). Each job has several
 * names: its title, its official occupation name, and the ESCO names people use for it (aliases). A job scores as
 * its best-matching name. Per word typed: exact word 3, a word starting with it 2, containing it 1; words of two
 * letters or fewer only count when exact. Words that match many jobs ("manager", "executive") count for less, so a
 * generic word alone can't decide the match. A name that covers every word typed beats one that covers some; a
 * name that is exactly what was typed ("software engineer") or contains it as a phrase goes first, and the job's
 * own title counts a little more than its aliases. `complete` says whether every word was found. */

export type JobOption = { isco: string; title: string; occupation: string; aliases?: string[] };
export type JobMatch<T> = { job: T; via: string | null; complete: boolean };

const words = (s: string) => s.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);

function wordScore(q: string, w: string) {
  if (w === q) return 3;
  if (q.length <= 2) return 0;
  if (w.startsWith(q)) return 2;
  return w.includes(q) ? 1 : 0;
}

const nameScore = (q: string, name: string[]) => Math.max(0, ...name.map((w) => wordScore(q, w)));

export function matchJobs<T extends JobOption>(query: string, jobs: T[], limit = 6): JobMatch<T>[] {
  const q = words(query);
  if (!q.length) return [];
  const names = jobs.map((job) => [job.title, job.occupation, ...(job.aliases ?? [])].map((n) => ({ text: n, words: words(n) })));
  // how many jobs each typed word reaches: the rarer, the more it says
  const reach = q.map((w) => names.filter((ns) => ns.some((n) => nameScore(w, n.words) > 0)).length);
  const weight = reach.map((k) => (k ? 1 + Math.log(jobs.length / k) : 0));

  return jobs
    .map((job, i) => {
      let best = { covered: 0, score: 0, via: null as string | null };
      names[i].forEach((n, j) => {
        const covered = q.filter((w) => nameScore(w, n.words) > 0).length;
        const name = ` ${n.words.join(" ")} `, phrase = ` ${q.join(" ")} `;
        const phraseBonus = name === phrase ? 9 : name.includes(phrase) ? 8 : 0;
        const score = phraseBonus + q.reduce((sum, w, k) => sum + weight[k] * nameScore(w, n.words), 0) + (j === 0 ? 1.5 : 0);
        if (covered > best.covered || (covered === best.covered && score > best.score + 1e-9)) {
          best = { covered, score, via: j === 0 ? null : n.text };
        }
      });
      return { job, ...best };
    })
    .filter((x) => x.covered > 0)
    .sort((a, b) => b.covered - a.covered || b.score - a.score || a.job.title.localeCompare(b.job.title))
    .slice(0, limit)
    .map(({ job, via, covered }) => ({
      job,
      via: via && via.toLowerCase() !== job.title.toLowerCase() ? via : null,
      complete: covered === q.length,
    }));
}
