const ACRONYM_MAP = {
  "\\bAI\\b": "AI artificial intelligence machine learning neural network",
  "\\bLLM\\b": "LLM large language model",
  "\\bML\\b": "ML machine learning",
  "\\bNLP\\b": "NLP natural language processing",
  "\\bRAG\\b": "RAG retrieval augmented generation",
  "\\bRLHF\\b": "RLHF reinforcement learning from human feedback",
  "\\bGNN\\b": "GNN graph neural network",
  "\\bCNN\\b": "CNN convolutional neural network",
  "\\bGAN\\b": "GAN generative adversarial network",
  "\\bAPI\\b": "API application programming interface",
  "\\bGPU\\b": "GPU graphics processing unit",
  "\\bAGI\\b": "AGI artificial general intelligence",
};

const TEMPORAL_WORDS = [
  "today", "yesterday", "latest", "recent", "this week",
  "this month", "this year", "нові", "останні", "сьогодні",
  "вчора", "новин", "актуальн",
];

export function preprocessQuery(query) {
  let q = query.trim();
  q = q.replace(/^(коротко|стисло|брифінг|briefly|short|summarize|tell me about|what is|what are|who is|explain|describe)\s+/i, "");
  q = q.replace(/^(що|хто|як|де|коли|чому|який|яка|які|what|who|how|where|when|why)\s+/i, "");
  for (const [pattern, replacement] of Object.entries(ACRONYM_MAP)) {
    q = q.replace(new RegExp(pattern, "gi"), replacement);
  }
  const hasTemporal = TEMPORAL_WORDS.some(w => query.toLowerCase().includes(w));
  if (hasTemporal && !q.includes("(date:")) {
    const today = new Date().toISOString().slice(0, 10);
    q += ` (date: ${today})`;
  }
  return q;
}

export function extractKeywords(text, maxWords = 10) {
  const words = text.toLowerCase().match(/[a-zа-я]{3,}/gi) || [];
  const stopWords = new Set([
    "this","that","and","the","for","are","but","not","you","all","can",
    "had","her","was","one","our","out","has","have","been","its","than",
    "what","from","they","with","та","і","в","на","не","що","як","до",
    "за","але","або","чи","з","про","по","це","його","її","який","такий",
    "will","нові","останні",
  ]);
  return [...new Set(words)].filter(w => !stopWords.has(w)).slice(0, maxWords);
}

export function deduplicateSources(sources) {
  const seenUrls = new Set();
  const seenTitles = new Set();
  return sources.filter(s => {
    const url = (s.url || "").trim().toLowerCase();
    const title = (s.title || "").trim().toLowerCase();
    if (url && seenUrls.has(url)) return false;
    if (title && seenTitles.has(title)) return false;
    if (url) seenUrls.add(url);
    if (title) seenTitles.add(title);
    return true;
  });
}

export function rerankSources(sources, keywords) {
  const kw = keywords.map(k => k.toLowerCase());
  return [...sources].map(s => {
    let score = s.relevance_score || 5.0;
    const text = `${s.title || ""} ${s.snippet || ""}`.toLowerCase();
    for (const k of kw) {
      if (text.includes(k)) score += 2.0;
    }
    if ((s.url || "").startsWith("http")) score += 1.0;
    return { ...s, relevance_score: score };
  }).sort((a, b) => b.relevance_score - a.relevance_score);
}

export function truncateAnswer(answer, maxChars = 5000) {
  if (!answer || answer.length <= maxChars) return answer;
  return answer.slice(0, maxChars) + "\n\n[...truncated]";
}

export function generateMarkdown(query, answer, sources) {
  let md = `# ${query}\n\n_Generated: ${new Date().toISOString()}_\n\n## Answer\n\n${answer}\n\n## Sources\n\n`;
  sources.forEach((s, i) => {
    md += `### [${i + 1}] ${s.title || "Untitled"}\n- **URL:** ${s.url || ""}\n- **Relevance:** ${s.relevance_score || "N/A"}\n`;
    if (s.snippet) md += `- **Snippet:** ${s.snippet}\n`;
    md += "\n";
  });
  return md;
}

export function generateJSON(data) {
  return JSON.stringify({ exportedAt: new Date().toISOString(), ...data }, null, 2);
}
