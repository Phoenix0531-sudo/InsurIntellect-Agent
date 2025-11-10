"""
Text-to-SQL 执行服务（只读）
负责安全地执行由路由器生成的 SELECT 语句，并返回字典列表。
"""

from __future__ import annotations

import re
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.app_logging import get_logger

logger = get_logger(__name__)


class SQLSecurityError(Exception):
    pass


class TextToSQLService:
    """只读 SQL 执行器：严格白名单，限制到 document_metadata 的 SELECT。"""

    # 禁止的关键字（大小写不敏感）
    _DENY_KEYWORDS = {
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
        "CREATE", "ATTACH", "PRAGMA", "VACUUM", "REPLACE", "MERGE",
        "GRANT", "REVOKE" , "BEGIN", "COMMIT", "ROLLBACK",
    }

    # 允许的目标表
    _ALLOWED_TABLES = {"document_metadata"}

    def _validate_sql(self, sql: str) -> str:
        if not isinstance(sql, str):
            raise SQLSecurityError("SQL 必须是字符串")
        sql = sql.strip()
        if not sql:
            raise SQLSecurityError("SQL 为空")

        # 只允许单条语句：若包含分号，则必须仅出现在末尾
        if ";" in sql:
            if not sql.endswith(";"):
                raise SQLSecurityError("仅允许末尾分号且只能一条语句")
            # 去掉末尾分号
            sql = sql[:-1].strip()

        # 起始允许 WITH 或 SELECT
        if not re.match(r"^(WITH\b|SELECT\b)", sql, flags=re.IGNORECASE):
            raise SQLSecurityError("仅允许 WITH/SELECT 开头的只读查询")

        # 禁止关键字
        upper = sql.upper()
        for kw in self._DENY_KEYWORDS:
            if kw in upper:
                raise SQLSecurityError(f"禁止关键字: {kw}")

        # 仅允许访问 document_metadata（解析 FROM/JOIN token）
        table_refs = re.findall(r"\b(FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, flags=re.IGNORECASE)
        if not table_refs:
            raise SQLSecurityError("查询必须显式包含 FROM document_metadata")
        for _, tbl in table_refs:
            if tbl.lower() not in self._ALLOWED_TABLES:
                raise SQLSecurityError(f"仅允许访问 document_metadata，检测到: {tbl}")

        return sql

    async def aexecute_sql_query(self, db: AsyncSession, sql_query: str) -> List[Dict]:
        """异步执行只读 SQL 并返回字典列表。"""
        try:
            safe_sql = self._validate_sql(sql_query)
            result = await db.execute(text(safe_sql))
            # 使用 mappings() 获取字典形式的行
            rows = result.mappings().all()  # type: ignore
            # rows 已是 Mapping 对象，可转字典
            return [dict(r) for r in rows]
        except SQLSecurityError:
            raise
        except Exception as e:
            logger.error(f"SQL 执行失败: {e}")
            raise

