import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import './AgentMessageContent.css';
import { normalizeAgentMarkdown } from './agentMarkdown';

/** Match the reference renderer's GFM approach, without its project-ID chips.
 * Repair common agent table formatting only outside fenced code blocks.
 * Raw HTML is left escaped by ReactMarkdown; never use rehype-raw here.
 */

export function AgentMessageContent({ text }: { text: string }) {
  return <div className="agent-markdown">
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks]}
      components={{
        table: ({ children }) => <div className="markdown-table-scroll" role="region" aria-label="Answer table" tabIndex={0}><table>{children}</table></div>,
        a: ({ href, children }) => href && /^(https?:|mailto:)/i.test(href)
          ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          : <span>{children}</span>,
        img: ({ alt }) => <span>{alt}</span>,
      }}
    >{normalizeAgentMarkdown(text)}</ReactMarkdown>
  </div>;
}
