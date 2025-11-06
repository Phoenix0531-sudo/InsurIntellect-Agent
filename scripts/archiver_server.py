#!/usr/bin/env python3
"""
档案官网关服务（FastAPI）

用途：
- 作为 backfill_metadata.py 的外部“档案官”API端点
- 接收文档正文与已有元数据，调用硅基流动（OpenAI兼容）模型抽取日期
- 返回规范化 JSON：{"publish_date":"YYYY-MM-DD","last_updated_date":"YYYY-MM-DD","effective_date":"YYYY-MM-DD"}

启动：
python -m uvicorn scripts.archiver_server:app --host 127.0.0.1 --port 8001

配置：
- 使用 .env 中的 SILICONFLOW_API_KEY / SILICONFLOW_BASE_URL / SILICONFLOW_MODEL
- backfill 脚本环境变量：
  ARCHIVER_API_URL=http://127.0.0.1:8001/archiver/extract-dates
  ARCHIVER_API_KEY=<与 .env 中 SILICONFLOW_API_KEY 相同>
"""

import os
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.core.config import settings
from app.core.app_logging import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Archiver Gateway", version="1.0.0")


class ExtractDatesRequest(BaseModel):
    doc_id: str
    content: str
    existing_metadata: Dict[str, Any] = {}
    # 支持可选字段提取：expiry_date、filing_date
    request_fields: List[str] = [
        "publish_date",
        "last_updated_date",
        "effective_date",
        "expiry_date",
        "filing_date",
    ]


class ExtractDatesResponse(BaseModel):
    publish_date: str = ""
    last_updated_date: str = ""
    effective_date: str = ""
    expiry_date: str = ""
    filing_date: str = ""


def get_openai_client() -> OpenAI:
    # 配置环境变量以兼容 OpenAI 客户端（硅基流动）
    os.environ["OPENAI_API_KEY"] = settings.SILICONFLOW_API_KEY
    os.environ["OPENAI_BASE_URL"] = settings.SILICONFLOW_BASE_URL
    return OpenAI(api_key=settings.SILICONFLOW_API_KEY, base_url=settings.SILICONFLOW_BASE_URL)


SYSTEM_INSTRUCT = (
    "你是一个文档档案官，请只输出严格的JSON对象，字段为 publish_date、last_updated_date、effective_date、expiry_date、filing_date。"
    "从用户提供的文档正文中准确抽取日期，格式统一为 YYYY-MM-DD。若无法确定则设为空字符串。"
    "expiry_date 可对应有效期/到期/过期日期（valid until / expiration date），filing_date 可对应备案/报备/registration/approval 日期。"
    "允许参考 existing_metadata 中的日期作为候选，但若正文出现更晚的日期，应以正文为准。"
)


def build_user_prompt(content: str, existing_metadata: Dict[str, Any]) -> str:
    return (
        "请从以下文档正文中提取日期，并返回JSON（仅这五个字段）：\n"
        "- publish_date\n- last_updated_date\n- effective_date\n- expiry_date\n- filing_date\n\n"
        "正文：\n" + (content or "") + "\n\n"
        "已有元数据：\n" + str(existing_metadata or {}) + "\n\n"
        "要求：仅输出JSON，无多余文本，日期格式为YYYY-MM-DD。未知用空字符串。"
    )


def parse_json_safe(s: str) -> Dict[str, Any]:
    import json
    try:
        # 去除可能的代码块包裹
        content = s.strip()
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end != -1:
                content = content[start:end].strip()
        elif content.startswith("```"):
            start = content.find("```") + 3
            end = content.find("```", start)
            if end != -1:
                content = content[start:end].strip()
        return json.loads(content)
    except Exception:
        return {}


@app.post("/archiver/extract-dates", response_model=ExtractDatesResponse)
def extract_dates(req: ExtractDatesRequest):
    client = get_openai_client()
    try:
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCT},
            {"role": "user", "content": build_user_prompt(req.content, req.existing_metadata)},
        ]
        # 使用温度0与JSON输出约束，提升结构化与稳定性
        resp = client.chat.completions.create(
            model=settings.SILICONFLOW_MODEL,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=messages,
            max_tokens=400,
        )
        text = resp.choices[0].message.content or "{}"
        data = parse_json_safe(text)

        # 规范化返回字段（缺失用空字符串）
        out = {
            "publish_date": str(data.get("publish_date", ""))[:10],
            "last_updated_date": str(data.get("last_updated_date", ""))[:10],
            "effective_date": str(data.get("effective_date", ""))[:10],
            "expiry_date": str(data.get("expiry_date", ""))[:10],
            "filing_date": str(data.get("filing_date", ""))[:10],
        }

        return ExtractDatesResponse(**out)
    except Exception as e:
        logger.exception("档案官抽取失败")
        raise HTTPException(status_code=500, detail=f"档案官抽取失败: {e}")
