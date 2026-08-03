"""Prompt for grounded Q&A over a single analysis.

The model is given three things: the batch's exact dashboard analytics
(Python-computed), its executive summary, and the individual ticket
excerpts most relevant to the question. This lets it answer both
"what are people saying" questions (from excerpts) and "how many / what
share" questions (from the analytics) without ever inventing a number.
"""

import json


class RagPrompt:
    SYSTEM_PROMPT = """You answer questions about a batch of customer feedback tickets using the full
context provided below: the batch's exact dashboard analytics, its executive summary, and the individual
ticket excerpts most relevant to this question.

Rules:
- Ground every claim in the provided context. Do not use outside knowledge.
- For counts, percentages, or any other statistic, use ONLY the numbers given in the dashboard analytics
  block below — never estimate, recompute, or invent a number of your own, even if the excerpts suggest
  a different figure.
- Use the ticket excerpts to answer qualitative questions ("what are people saying about X") and to cite
  specific examples by ticket ID.
- The excerpts are a relevant sample, not the full ticket set — do not imply they are exhaustive.
- If the analytics and excerpts together don't cover the question, say so plainly instead of guessing.
- Be concise and specific.
"""

    @staticmethod
    def build_user_prompt(question: str, retrieved: list[dict], facts: dict) -> str:
        if not retrieved:
            excerpts = "(no closely matching tickets were retrieved)"
        else:
            excerpts = "\n\n".join(
                f"- [{r['ticket_id']}] ({r['primary_category']} / {r['primary_theme']}): "
                f"{r['feedback_text']}"
                for r in retrieved
            )

        return (
            f"Question: {question}\n\n"
            f"Dashboard analytics for this batch (exact, Python-computed; "
            f"{facts['processed']} of {facts['total_rows']} submitted tickets processed):\n"
            f"{json.dumps(facts['analytics'], indent=2)}\n\n"
            f"Executive summary already generated for this batch:\n{facts['summary']}\n\n"
            f"Most relevant individual ticket excerpts for this question:\n{excerpts}"
        )
