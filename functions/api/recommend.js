/**
 * POST /api/recommend — LLM-backed model recommendation, proxied through Groq.
 *
 * The browser never sees the API key: it lives in the GROQ_API_KEY secret bound
 * to this Pages project. The page sends the user's task plus the shortlist of
 * tracked models with their benchmark numbers; the LLM classifies the task and
 * picks a model, citing the data.
 *
 * Two things keep the LLM honest, both enforced outside it:
 *   1. Here: the pick is validated against the slugs we actually sent, so it
 *      cannot invent or hallucinate a model.
 *   2. In the page: the hard gates (non-hallucination floors for unattended and
 *      high-stakes work, the voice latency ceiling) are re-applied to the LLM's
 *      answer using the very task type and scenarios it reported. A pick that
 *      violates a gate is overridden by the deterministic one. The gates cannot
 *      be talked out of, which is the entire point of having them.
 *
 * Request:  { task, candidates: [{slug, name, ...metrics}] }
 * Response: { pick, runner_up, type, confidence, scenarios, rationale,
 *             tradeoff, multi_step, source }
 */

const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';

// Groq's free tier meters tokens per minute PER MODEL, and one recommendation
// costs ~5-6k of an 8k/min ceiling — so a single model allows roughly one pick a
// minute across the whole site. Each entry below draws on its own separate quota,
// so when the first is exhausted we fall to the next instead of failing the user.
//
// Ordered best-first. gpt-oss-120b reasons properly about the tradeoffs; the
// llama models are weaker but still read the numbers, and a slightly worse
// recommendation beats "try again in a minute". `budget` is the completion cap:
// reasoning models must be given room to think before they emit any JSON, while
// the non-reasoning ones answer directly and need far less.
const MODELS = [
  { id: 'openai/gpt-oss-120b', budget: 2500 },
  { id: 'openai/gpt-oss-20b', budget: 2500 },
  { id: 'llama-3.3-70b-versatile', budget: 900 },
];
const MODEL = MODELS[0].id;

const TASK_TYPES = [
  'coaching', 'coding', 'agentic', 'research', 'architecting',
  'advisor', 'voice', 'vision', 'creative', 'general',
];

const MAX_TASK_CHARS = 4000;
const MAX_CANDIDATES = 30;

const SYSTEM_PROMPT = `You are the recommendation engine for Model Compass, a tool that picks the right LLM for a task using Artificial Analysis benchmark data.

You are given a user's task and the full shortlist of tracked models with their benchmark numbers. Classify the task, then choose the single best model for it and justify the choice by citing specific numbers.

Rules:
- You MUST pick from the given candidates, using the exact slug. Never name a model that is not in the list.
- Cite actual numbers from the candidate data. "Higher non-hallucination (83.9% vs 64.1%)" — not "it's more reliable".
- A null/missing metric means untested, NOT zero. Never treat a missing value as a weakness; if it matters for this task, say the data is missing.
- non_halluc is the AA-Omniscience non-hallucination rate: how often a model declines to answer rather than guessing wrong. A high non_halluc with a LOW omniscience_accuracy means the model abstains a lot — good for unattended or high-stakes work, bad when you need it to actually know things. Always read those two together; never praise a high non_halluc without checking accuracy.
- Weigh cost honestly. If a much cheaper model is within a point or two, say so in "tradeoff".
- Match the metric to the task: terminalbench/scicode for coding, agentic_index and tau3_banking for tool use, context_tokens for long documents, ttft_seconds and output_speed_tps for anything interactive or real-time, mmmu_pro for images.
- If the top two are close, say so in "tradeoff" and name the deciding factor. Otherwise leave tradeoff as an empty string.

These hard gates are enforced in code AFTER you answer, based on the scenarios you report. A pick that fails one will be thrown away, so respect them:
- unattended (and not interactive): non_halluc >= 70
- high_stakes: non_halluc >= 80 AND intelligence >= 45
- voice: ttft_seconds <= 5

Return ONLY a JSON object, no prose:
{
  "type": "<one of: ${TASK_TYPES.join(', ')}>",
  "confidence": <0.0-1.0, how sure you are about the task type>,
  "scenarios": {
    "unattended": <bool: runs with no human review — cron, automation, background>,
    "long_context": <bool: >100K tokens, large codebase, multi-document>,
    "low_latency": <bool: real-time, voice, sub-second response matters>,
    "high_stakes": <bool: medical, legal, financial, customer-facing, compliance>,
    "cost_sensitive": <bool: user explicitly cares about low cost>
  },
  "pick": "<slug of the chosen model, exactly as given>",
  "runner_up": "<slug of the second choice, or empty string>",
  "rationale": "<2-3 sentences citing specific benchmark numbers for why this model wins for THIS task>",
  "tradeoff": "<one sentence if it's a close call or there's a real cost/quality tension, else empty string>",
  "multi_step": [<secondary task types if the task has clearly distinct stages, else []>]
}

Definitions:
- coaching: check-ins, journaling, briefings, conversational support
- coding: write/debug/refactor code
- agentic: multi-step automation, tool use, cron jobs, API orchestration
- research: deep investigation, multi-source synthesis, comparisons
- architecting: system design, schema, infrastructure, scalability
- advisor: an opinion or recommendation on a decision
- voice: text-to-speech, audio narration
- vision: image/screenshot/chart analysis
- creative: storytelling, brainstorming
- general: anything else

Default to unattended: false — someone typing into a picker is reading the output.`;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
    },
  });
}

export async function onRequestPost({ request, env }) {
  if (!env.GROQ_API_KEY) {
    return json({ error: 'Recommender not configured: GROQ_API_KEY is not set.' }, 503);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'Body must be JSON.' }, 400);
  }

  const task = typeof body.task === 'string' ? body.task.trim() : '';
  const candidates = Array.isArray(body.candidates) ? body.candidates : [];

  if (!task) return json({ error: 'Missing "task".' }, 400);
  if (task.length > MAX_TASK_CHARS) {
    return json({ error: `Task too long (max ${MAX_TASK_CHARS} characters).` }, 400);
  }
  if (!candidates.length) return json({ error: 'Missing "candidates".' }, 400);

  const shortlist = candidates.slice(0, MAX_CANDIDATES);
  const allowed = new Set(shortlist.map(c => c.slug));

  // Compact, not pretty-printed: indentation is pure token cost against the
  // per-minute budget, and the model reads it identically either way. An absent
  // key means the metric is untested.
  const userPrompt = [
    `USER TASK:\n"""${task}"""`,
    '',
    'CANDIDATE MODELS (benchmarks are percentages; a missing key means untested, not zero):',
    JSON.stringify(shortlist),
    '',
    'Classify the task and pick the best model for it. Return only the JSON object.',
  ].join('\n');

  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: userPrompt },
  ];

  // Walk the chain: a rate-limited or oversized request moves to the next model's
  // separate quota. Anything else (bad key, malformed output) is a real failure
  // and stops here — retrying it on another model would just burn the fallbacks.
  let content = null;
  let usedModel = null;
  let lastError = null;

  for (const { id, budget } of MODELS) {
    let res;
    try {
      res = await fetch(GROQ_URL, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.GROQ_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: id,
          messages,
          temperature: 0.2,
          // A reasoning model spends this budget thinking before it emits a single
          // character of JSON; starve it and Groq rejects its own truncated output
          // as invalid. Do not set reasoning_effort: on "low" gpt-oss-120b inverts
          // the non-hallucination metric and argues a 4.2% score means reliable.
          max_tokens: budget,
          response_format: { type: 'json_object' },
        }),
      });
    } catch (e) {
      lastError = `Could not reach the recommender: ${e.message}`;
      continue;
    }

    if (res.status === 429 || res.status === 413) {
      lastError = 'rate-limited';
      continue;
    }

    if (!res.ok) {
      const detail = (await res.text()).slice(0, 300);
      return json({ error: `Recommender API error ${res.status}`, detail }, 502);
    }

    const data = await res.json();
    const c = data?.choices?.[0]?.message?.content;
    if (!c) {
      lastError = 'empty response';
      continue;
    }
    content = c;
    usedModel = id;
    break;
  }

  if (!content) {
    if (lastError === 'rate-limited') {
      return json({
        error: 'The recommender is busy (free-tier token limit). Ranked by the '
             + 'formula instead — try again in a minute for the LLM’s reasoning.',
      }, 429);
    }
    return json({ error: `Recommender unavailable: ${lastError}` }, 502);
  }

  let parsed;
  try {
    parsed = JSON.parse(content);
  } catch {
    return json({ error: 'Recommender returned malformed JSON.' }, 502);
  }

  // Validate against the candidates we actually sent. A hallucinated slug is a
  // failure, not something to paper over — the page falls back to the
  // deterministic pick and tells the user the LLM step didn't work.
  if (!allowed.has(parsed.pick)) {
    return json({
      error: `Recommender chose a model that was not a candidate: ${parsed.pick}`,
    }, 502);
  }
  if (parsed.runner_up && !allowed.has(parsed.runner_up)) {
    parsed.runner_up = '';
  }
  if (!TASK_TYPES.includes(parsed.type)) {
    parsed.type = 'general';
    parsed.confidence = Math.min(parsed.confidence ?? 0.5, 0.5);
  }

  return json({
    type: parsed.type,
    confidence: typeof parsed.confidence === 'number' ? parsed.confidence : 0.7,
    scenarios: parsed.scenarios && typeof parsed.scenarios === 'object' ? parsed.scenarios : {},
    pick: parsed.pick,
    runner_up: parsed.runner_up || '',
    rationale: String(parsed.rationale || ''),
    tradeoff: String(parsed.tradeoff || ''),
    multi_step: Array.isArray(parsed.multi_step) ? parsed.multi_step : [],
    source: 'llm',
    model: usedModel,
  });
}

// Health probe. The page calls this on load to decide whether to advertise the
// LLM recommender or the keyword fallback. It answers 200 rather than 405 so a
// perfectly normal capability check doesn't log an error in every visitor's console.
export async function onRequestGet({ env }) {
  return json({ ok: true, configured: Boolean(env.GROQ_API_KEY), model: MODEL });
}
