"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

GENERATE_SQL_SYSTEM = """ \
You are an expert SQL assistant. Given a database schema and a question, \
write a single valid SQLite query that answers the question.

Rules:
- Return ONLY the SQL query, wrapped in ```sql ... ``` fences.
- Do not include any explanation or commentary.
- Use only tables and columns that exist in the schema.
- Use correct SQLite syntax (e.g. STRFTIME for dates).
- If the question requires a JOIN, use the foreign keys shown in the schema.
"""

# Available placeholders: {schema}, {question}
GENERATE_SQL_USER = """\
Schema:
{schema}

Question: {question}

SQL:
"""


VERIFY_SYSTEM = ""

VERIFY_USER = ""


REVISE_SYSTEM = ""

REVISE_USER = ""
