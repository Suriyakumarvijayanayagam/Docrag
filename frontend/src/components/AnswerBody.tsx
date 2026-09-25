import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Confidence } from '../types'

// Heading lines the model writes for each part, tolerating the markdown
// decoration a small model adds: "## From the documents", "**ADDITIONAL INSIGHT:**", "2. Additional insight".
const GROUNDED_HEADING = /^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?[ \t]*(?:\d\.[ \t]*)?from the documents?[ \t]*:?[ \t]*(?:\*\*|__)?[ \t]*:?[ \t]*$/im
const INSIGHT_HEADING = /^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?[ \t]*(?:\d\.[ \t]*)?additional insights?[ \t]*:?[ \t]*(?:\*\*|__)?[ \t]*:?/im

/**
 * The split between what the documents say and what the model added is the
 * product's core claim, so it is rendered structurally rather than trusted to
 * the model's formatting. While streaming, everything before the insight
 * heading shows as the answer, and it re-splits the moment that heading arrives.
 */
export function splitAnswer(text: string): { grounded: string; insight: string } {
  const match = INSIGHT_HEADING.exec(text)
  let grounded = (match ? text.slice(0, match.index) : text).replace(GROUNDED_HEADING, '').trim()
  // a small model sometimes drops the headings but still writes the insight's
  // "None." on its own last line; that's an empty insight, not part of the answer
  if (!match) grounded = grounded.replace(/\n\s*none\.?\s*$/i, '').trim()
  let insight = match ? text.slice(match.index + match[0].length).trim() : ''
  if (/^none\.?$/i.test(insight)) insight = ''
  return { grounded, insight }
}

const CONFIDENCE: Record<Confidence, { label: string; hint: string }> = {
  high: { label: 'Strong grounding', hint: 'At least one retrieved passage scored 7 or more out of 10 for this question.' },
  medium: { label: 'Partial grounding', hint: 'The best passage scored 4-7, or the answer rests on an exact table value.' },
  low: { label: 'Weak grounding', hint: 'Nothing retrieved scored above 4. Check the cited pages before relying on this.' },
  none: { label: 'No sources found', hint: 'Nothing in the selected library matched this question.' },
}

export function ConfidenceBadge({ level }: { level: Confidence }) {
  const spec = CONFIDENCE[level]
  return <span className={`grounding grounding-${level}`} title={spec.hint}><i />{spec.label}</span>
}

/** Turns the model's [n] citation markers into buttons that open that source. */
function withCitationLinks(markdown: string, count: number): string {
  if (!count) return markdown
  return markdown.replace(/\[(\d{1,2})\](?!\()/g, (whole, n) => Number(n) >= 1 && Number(n) <= count ? `[${n}](#cite-${n})` : whole)
}

function Markdown({ text, citationCount, onCite }: { text: string; citationCount: number; onCite: (index: number) => void }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    a: ({ href, children }) => {
      const cite = href?.match(/^#cite-(\d+)$/)
      if (cite) return <button type="button" className="cite" onClick={() => onCite(Number(cite[1]))} title={`Source ${cite[1]}`}>{children}</button>
      return <a href={href} target="_blank" rel="noreferrer">{children}</a>
    },
  }}>{withCitationLinks(text, citationCount)}</ReactMarkdown>
}

export function AnswerBody({ content, streaming, citationCount, onCite }: {
  content: string; streaming: boolean; citationCount: number; onCite: (index: number) => void
}) {
  const { grounded, insight } = splitAnswer(content)
  return <div className="answer-body">
    <div className="prose"><Markdown text={grounded} citationCount={citationCount} onCite={onCite} />{streaming && !insight && <span className="caret" />}</div>
    {insight && <aside className="model-note">
      <div className="model-note-label">Model's own reasoning · not from your documents</div>
      <div className="prose"><Markdown text={insight} citationCount={0} onCite={onCite} />{streaming && <span className="caret" />}</div>
    </aside>}
  </div>
}
