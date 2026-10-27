/**
 * Pure fuzzy scoring algorithm for file path search.
 * Supports multi-term queries (e.g. "compo btn" matching "src/components/Button.tsx").
 */

export interface FuzzyMatchResult {
  path: string;
  score: number;
  indices: number[];
}

/**
 * Score a single target against a single query term.
 * Returns { score, indices } or null if no match.
 */
function matchTerm(term: string, target: string): { score: number; indices: number[] } | null {
  const tLower = target.toLowerCase();
  const qLower = term.toLowerCase();

  let tIdx = 0;
  let qIdx = 0;
  const indices: number[] = [];
  let score = 0;
  let consecutive = 0;

  while (qIdx < qLower.length && tIdx < tLower.length) {
    if (qLower[qIdx] === tLower[tIdx]) {
      indices.push(tIdx);
      consecutive += 1;

      // Base character match score
      let charScore = 10 + consecutive * 5;

      // Bonus for match at start of string or after separator (/ . _ -)
      if (tIdx === 0 || "/._- ".includes(target[tIdx - 1])) {
        charScore += 25;
      }
      // Bonus for camelCase uppercase
      else if (target[tIdx] !== tLower[tIdx]) {
        charScore += 15;
      }

      score += charScore;
      qIdx += 1;
    } else {
      consecutive = 0;
    }
    tIdx += 1;
  }

  // Term was not fully matched
  if (qIdx < qLower.length) {
    return null;
  }

  // Bonus for shorter target (less noise)
  score += Math.max(0, 50 - target.length);

  // Bonus if match is in the filename segment (after last /)
  const lastSlash = target.lastIndexOf("/");
  const filename = lastSlash >= 0 ? target.slice(lastSlash + 1) : target;
  if (filename.toLowerCase().includes(qLower)) {
    score += 40;
  }

  return { score, indices };
}

/**
 * Perform fuzzy search across a list of file paths.
 * All whitespace-delimited terms in query must match.
 */
export function fuzzySearch(query: string, paths: string[]): FuzzyMatchResult[] {
  const trimmed = query.trim();
  if (!trimmed) {
    return paths.map((path) => ({ path, score: 0, indices: [] }));
  }

  const terms = trimmed.split(/\s+/).filter(Boolean);
  const results: FuzzyMatchResult[] = [];

  for (const path of paths) {
    let totalScore = 0;
    const allIndices: number[] = [];
    let allMatched = true;

    for (const term of terms) {
      const match = matchTerm(term, path);
      if (!match) {
        allMatched = false;
        break;
      }
      totalScore += match.score;
      allIndices.push(...match.indices);
    }

    if (allMatched) {
      // Deduplicate indices
      const uniqueIndices = Array.from(new Set(allIndices)).sort((a, b) => a - b);
      results.push({
        path,
        score: totalScore,
        indices: uniqueIndices,
      });
    }
  }

  // Sort by score descending, then path ascending
  return results.sort((a, b) => {
    if (b.score !== a.score) {
      return b.score - a.score;
    }
    return a.path.localeCompare(b.path);
  });
}
