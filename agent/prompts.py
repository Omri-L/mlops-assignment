"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

## Generate SQL prompts
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

GENERATE_SQL_USER = """\
Schema:
{schema}

Question: {question}

Write the SQLite query that answers the question.
SQL:
"""

## Verify SQL prompts
VERIFY_SYSTEM = """\
You are a strict SQL result verifier. Given a question, a SQL query, and the result \
of running it, decide whether the result plausibly answers the question.

Respond with ONLY a JSON object in this exact format:
{"ok": true, "issue": ""}

Set ok to false if any of the following apply:
- The SQL produced an error
- The result has 0 rows but the question implies rows should exist
- A COUNT or SUM aggregate returns 0 when the question asks "how many" or
  implies that matching records should exist
- The result contains only NULL values where a concrete value is expected
- The columns returned clearly do not match what the question asked for

Set "issue" according to "ok" result:
- If "ok" is false, set issue to a sentence that quotes the exact SQL fragment 
most likely responsible (e.g. a specific WHERE condition, column name, or 
aggregate) and describes why it is probably wrong.
- If "ok" is true, leave issue as an empty string.
"""

VERIFY_USER = """\
Question: {question}

SQL:
{sql}

Result:
{result}

JSON:
"""

## Revise SQL prompts
REVISE_SYSTEM = """\
You are an expert SQL assistant. A SQL query failed to correctly answer a \
question. Given the schema, the question, the failing query, its result, and \
what went wrong, write a corrected SQLite query.

Rules:
- Return ONLY the corrected SQL query, wrapped in ```sql ... ``` fences.
- Do not include any explanation or commentary.
- Use only tables and columns that exist in the schema.
- Use correct SQLite syntax (e.g. STRFTIME for dates).
- Focus your fix on the exact SQL fragment quoted in the issue. Change that 
  fragment and leave the rest of the query untouched.
"""

REVISE_USER = """\
The following SQL query produced an incorrect result and must be fixed.

Problem identified:
{issue}

Previous (incorrect) SQL:
{sql}

Result it produced:
{result}

You MUST write a new SQL query that is different from the previous one and \
directly addresses the problem described above.

Schema:
{schema}

Question: {question}

Fixed SQL:
"""
