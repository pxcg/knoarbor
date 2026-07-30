import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

export const markdownRemarkPlugins = [remarkGfm, remarkMath];
export const markdownRehypePlugins = [rehypeKatex];
