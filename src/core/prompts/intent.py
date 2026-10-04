INTENT_CLASSIFIER_PROMPT = """
Classify the user's enterprise request.

Available capabilities:

knowledge:
Retrieve factual information from enterprise documents.

analytics:
Query structured business data using SQL and calculate metrics. This also includes
counts and group-by comparisons over document metadata, such as document counts
by business domain, year, type, or processing status; these requests do not need
document-text retrieval unless the user also asks what the documents say.

Example: "Compare document counts by business domain" is analytics, needs_sql
is true, and needs_knowledge is false.

hybrid:
Requires both document knowledge and structured business data.

dashboard:
User explicitly requests charts, dashboard, visualization, or KPI view.

report:
User asks to summarize source documents or explicitly draft/write a report. Do not
select this just because the request mentions a report as a data source or asks
for report counts; those are knowledge or analytics requests.

Return valid JSON only:

{{
  "intent": "knowledge | analytics | dashboard | hybrid | report",
  "needs_knowledge": true,
  "needs_sql": false,
  "output_mode": "answer | dashboard",
  "confidence": 0.0
}}

User request:
{question}
"""

COMMERCE_DOMAIN_CLASSIFIER_PROMPT = """
Choose which Commerce decision domain best fits the user's business objective.

Available domains:
{domains}

Return JSON only with keys `domain` and `confidence`. `domain` must be one of the
listed IDs or null. Choose from the decision requested, not just a word mentioned
in passing. If the request materially spans multiple domains or is not a Commerce
operations question, return null. Do not infer data availability or recommend an
action.

Example shape: {{"domain": "inventory_allocation", "confidence": 0.91}}

Question:
{question}
"""
