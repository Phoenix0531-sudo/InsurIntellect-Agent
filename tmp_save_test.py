import asyncio
from app.core.database import db_manager
from app.services.query_service import QueryService
s = db_manager.create_session()
qs = QueryService()
async def t():
    rid = await qs._save_query_history(s, 'auto test', 'ok', 'general', 0.2, 1, rewritten_query=None, rewriting_metadata_json=None, retrieved_chunks_json=None)
    print('returned id:', rid)
asyncio.run(t())
s.close()
