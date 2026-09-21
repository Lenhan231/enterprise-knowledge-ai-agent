INTENT_CLASSIFIER_PROMPT = """
Classify the user's enterprise request.

Available capabilities:

knowledge:
Retrieve factual information from enterprise documents.

analytics:
Query structured business data using SQL and calculate metrics.

hybrid:
Requires both document knowledge and structured business data.

dashboard:
User explicitly requests charts, dashboard, visualization, or KPI view.

Return valid JSON only:

{{
  "intent": "knowledge | analytics | dashboard | hybrid",
  "needs_knowledge": true,
  "needs_sql": false,
  "output_mode": "answer | dashboard",
  "confidence": 0.0
}}

User request:
{question}
"""