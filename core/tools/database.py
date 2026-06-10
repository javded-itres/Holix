from pathlib import Path

import aiosqlite

from core.tools.base import BaseTool


class SQLQueryTool(BaseTool):
    """Tool for executing SQL queries on SQLite databases."""

    def __init__(self):
        super().__init__()
        self.name = "sql_query"
        self.description = "Execute a SQL query on a SQLite database. Supports SELECT, INSERT, UPDATE, DELETE. Use for data analysis and database operations."
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "db_path": {
                    "type": "string",
                    "description": "Path to SQLite database file"
                },
                "query": {
                    "type": "string",
                    "description": "SQL query to execute"
                },
                "params": {
                    "type": "array",
                    "description": "Optional parameters for parameterized queries",
                    "items": {"type": "string"},
                    "default": []
                }
            },
            "required": ["db_path", "query"]
        }

    async def execute(self, db_path: str, query: str, params: list | None = None) -> str:
        """Execute SQL query on SQLite database.

        Args:
            db_path: Path to database file
            query: SQL query
            params: Optional query parameters

        Returns:
            Query results or error message
        """
        params = params or []

        try:
            db_file = Path(db_path).expanduser()

            if not db_file.exists():
                return f"Error: Database '{db_path}' does not exist"

            # Detect query type
            query_type = query.strip().split()[0].upper()

            async with aiosqlite.connect(db_file) as db:
                db.row_factory = aiosqlite.Row

                if query_type == "SELECT":
                    # SELECT query
                    cursor = await db.execute(query, params)
                    rows = await cursor.fetchall()

                    if not rows:
                        return "Query executed successfully. No rows returned."

                    # Format results as table
                    columns = rows[0].keys()
                    result_lines = [" | ".join(columns)]
                    result_lines.append("-" * len(result_lines[0]))

                    for row in rows[:100]:  # Limit to 100 rows
                        result_lines.append(" | ".join(str(row[col]) for col in columns))

                    if len(rows) > 100:
                        result_lines.append(f"\n... ({len(rows) - 100} more rows)")

                    return f"Found {len(rows)} rows:\n\n" + "\n".join(result_lines)

                else:
                    # INSERT, UPDATE, DELETE
                    cursor = await db.execute(query, params)
                    await db.commit()

                    return f"Query executed successfully. {cursor.rowcount} row(s) affected."

        except aiosqlite.Error as e:
            return f"SQL Error: {str(e)}"
        except Exception as e:
            return f"Error executing query: {str(e)}"


class SQLSchemaTool(BaseTool):
    """Tool for inspecting SQLite database schema."""

    def __init__(self):
        super().__init__()
        self.name = "sql_schema"
        self.description = "Get the schema information of a SQLite database. Shows tables, columns, and their types."
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "db_path": {
                    "type": "string",
                    "description": "Path to SQLite database file"
                }
            },
            "required": ["db_path"]
        }

    async def execute(self, db_path: str) -> str:
        """Get database schema information.

        Args:
            db_path: Path to database file

        Returns:
            Schema information
        """
        try:
            db_file = Path(db_path).expanduser()

            if not db_file.exists():
                return f"Error: Database '{db_path}' does not exist"

            async with aiosqlite.connect(db_file) as db:
                # Get all tables
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = await cursor.fetchall()

                if not tables:
                    return "Database is empty (no tables found)"

                result = [f"Database: {db_path}\n"]

                for (table_name,) in tables:
                    result.append(f"\nTable: {table_name}")

                    # Get table info
                    cursor = await db.execute(f"PRAGMA table_info({table_name})")
                    columns = await cursor.fetchall()

                    result.append("Columns:")
                    for col in columns:
                        col_id, name, col_type, not_null, default, pk = col
                        flags = []
                        if pk:
                            flags.append("PRIMARY KEY")
                        if not_null:
                            flags.append("NOT NULL")
                        if default is not None:
                            flags.append(f"DEFAULT {default}")

                        flags_str = f" ({', '.join(flags)})" if flags else ""
                        result.append(f"  - {name}: {col_type}{flags_str}")

                return "\n".join(result)

        except aiosqlite.Error as e:
            return f"SQL Error: {str(e)}"
        except Exception as e:
            return f"Error inspecting schema: {str(e)}"
