# ai-pr-review

A GitHub Action that posts an AI code review on pull requests using **any OpenAI-compatible API** — bring your own provider and model.

No vendor lock-in. No hardcoded model names. Just point it at an endpoint.

This is a proof-of-concept and exploration as an attempt to utilize API keys of different providers to do code reviews.

---

## Quick start

```yaml
# .github/workflows/ai-review.yml
name: AI PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read
    steps:
      - uses: hilleer/ai-pr-review@v1
        with:
          api_key: ${{ secrets.AI_API_KEY }}
          base_url: https://api.moonshot.cn/v1
          model: kimi-k2-0711-preview
```

Add your API key as a repository secret named `AI_API_KEY` (Settings → Secrets and variables → Actions), and you're done.

---

## Provider examples

Any provider that exposes an OpenAI-compatible `/chat/completions` endpoint works:

| Provider | `base_url` | Example `model` |
|---|---|---|
| [Moonshot (Kimi)](https://platform.moonshot.cn) | `https://api.moonshot.cn/v1` | `kimi-k2-0711-preview` |
| [Zhipu (GLM)](https://open.bigmodel.cn) | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-plus` |
| [OpenAI](https://platform.openai.com) | `https://api.openai.com/v1` | `gpt-4o` |
| [Mistral](https://console.mistral.ai) | `https://api.mistral.ai/v1` | `mistral-large-latest` |
| [Groq](https://console.groq.com) | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| [Together AI](https://api.together.xyz) | `https://api.together.xyz/v1` | `meta-llama/Llama-3-70b-chat-hf` |
| [DeepSeek](https://platform.deepseek.com) | `https://api.deepseek.com/v1` | `deepseek-chat` |
| [Ollama (local)](https://ollama.com) | `http://localhost:11434/v1` | `llama3.2` |

---

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `api_key` | ✅ | — | API key for your provider |
| `base_url` | ✅ | — | Base URL of the OpenAI-compatible API |
| `model` | ✅ | — | Model name to use |
| `system_prompt` | | built-in | Custom system prompt |
| `language` | | `english` | Language for the review response |
| `post_mode` | | `comment` | `comment` (PR comment) or `review` (Reviews tab) |
| `max_tokens` | | `2048` | Max tokens in the model response |
| `max_diff_chars` | | `80000` | Max diff size sent to the model |
| `file_patterns` | | `*.ts,*.tsx,...` | Glob patterns of files to include |
| `exclude_patterns` | | `*.lock,dist/*,...` | Glob patterns of files to exclude |
| `github_token` | | `github.token` | Token for posting comments |

## Outputs

| Output | Description |
|---|---|
| `review_body` | First 1000 chars of the review text |
| `model_used` | The model that performed the review |

---

## Custom system prompt

You can fully replace the built-in prompt — useful if you want domain-specific review focus:

```yaml
- uses: hilleer/ai-pr-review@v1
  with:
    api_key: ${{ secrets.AI_API_KEY }}
    base_url: https://api.moonshot.cn/v1
    model: kimi-k2-0711-preview
    system_prompt: |
      You are a senior engineer specialising in financial software and Danish regulatory compliance.
      Review the diff for:
      - Correctness of monetary calculations (DKK precision, rounding)
      - Agentic loop safety (infinite loops, unhandled tool failures)
      - Missing input validation and error handling
      - Danish-specific data handling (CPR/CVR numbers, Danish FSA rules)
      Group findings by severity: 🔴 Critical, 🟡 Warning, 🟢 Suggestion.
```

---

## Dual-provider review

Run two models in parallel to get independent perspectives:

```yaml
jobs:
  review-kimi:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read
    steps:
      - uses: hilleer/ai-pr-review@v1
        with:
          api_key: ${{ secrets.MOONSHOT_API_KEY }}
          base_url: https://api.moonshot.cn/v1
          model: kimi-k2-0711-preview

  review-glm:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read
    steps:
      - uses: hilleer/ai-pr-review@v1
        with:
          api_key: ${{ secrets.ZHIPU_API_KEY }}
          base_url: https://open.bigmodel.cn/api/paas/v4
          model: glm-4-plus
```

---

## How it works

1. Checks out the repository with full history
2. Generates a `git diff` between the PR branch and base, filtered to relevant files
3. Sends the diff to the model with a structured code review prompt
4. Posts the response as a PR comment or GitHub Review

The action uses only Python stdlib and shell builtins — no npm install, no Docker, fast startup.

---

## License

MIT
