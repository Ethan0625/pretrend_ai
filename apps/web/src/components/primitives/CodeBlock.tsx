export interface CodeBlockProps {
  children: string;
}

export function CodeBlock({ children }: CodeBlockProps) {
  return <pre className="codeblock">{children}</pre>;
}
