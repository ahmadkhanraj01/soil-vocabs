# Mistral estimate: mistral-small-latest, 4 workers

Sample: 500 random records without subjects. Prices: 2026-10-22, from the model cards on docs.mistral.ai (USD per million tokens). Check https://mistral.ai/pricing before a large run.

| Records | Time | Per record | Input tokens | Output tokens | Cost (USD) | Avg terms | No term |
|---|---|---|---|---|---|---|---|
| 10 | 0 min 4 s | 0.4 s | 4,261 | 306 | 0.0011 | 4.7 | 0 |
| 50 | 0 min 17 s | 0.36 s | 22,401 | 1,608 | 0.0058 | 4.82 | 0 |
| 100 | 0 min 33 s | 0.33 s | 44,291 | 3,176 | 0.0115 | 4.77 | 2 |
| 500 | 7 min 19 s | 0.88 s | 220,392 | 15,825 | 0.0571 | 4.78 | 11 |

## All 23,319 records (from the 500-record sample)

- Cost: about **$2.66** (range $2.59 to $2.72)
- Time: about **5 h 42 min** with 4 workers
- Rate-limit replies (429) during the sample: 40; errors: 0

Same tokens with other models (cost only; time and quality differ):

- ministral-3b-latest: $1.78
- ministral-8b-latest: $2.33
- ministral-14b-latest: $2.88
- mistral-small-latest: $2.66
