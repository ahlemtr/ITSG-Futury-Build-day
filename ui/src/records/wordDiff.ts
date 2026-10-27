// Word diff for spec passages: old and new text with removed and added words marked.

export type DiffPart = { text: string; kind: "same" | "del" | "ins" };

/** PDF text breaks words at line ends ("Begren-\nzung"); a hyphen before a lowercase letter on the next line is a
 * soft hyphen and is joined, so different line breaks in the two versions do not show up as changes. */
export const unwrap = (s: string) => s.replace(/(\p{L})-\s*\n\s*(\p{Ll})/gu, "$1$2").replace(/\s*\n\s*/g, " ");

const words = (s: string) => unwrap(s).split(/(\s+)/).filter((w) => w !== "");

/** Longest common subsequence over words; returns the parts of the old and the new text. */
export function wordDiff(oldText: string, newText: string): { old: DiffPart[]; new: DiffPart[] } {
  const a = words(oldText);
  const b = words(newText);
  const n = a.length;
  const m = b.length;
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const oldParts: DiffPart[] = [];
  const newParts: DiffPart[] = [];
  const push = (list: DiffPart[], text: string, kind: DiffPart["kind"]) => {
    const last = list[list.length - 1];
    if (last && last.kind === kind) last.text += text;
    else list.push({ text, kind });
  };
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) {
      push(oldParts, a[i], "same");
      push(newParts, b[j], "same");
      i++;
      j++;
    } else if (j < m && (i >= n || lcs[i][j + 1] >= lcs[i + 1][j])) {
      push(newParts, b[j++], "ins");
    } else {
      push(oldParts, a[i++], "del");
    }
  }
  return { old: oldParts, new: newParts };
}
