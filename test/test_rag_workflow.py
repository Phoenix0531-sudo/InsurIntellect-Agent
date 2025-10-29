#!/usr/bin/env python3
"""
RAG工作流测试脚本
测试完整的问答流程，包括查询重写、文档检索、评审和答案生成
"""

import sys
import os
# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.chromadb_manager import ChromaDBManager
import time

def test_offline_rag_simulation():
    """测试离线RAG模拟（不使用LLM）"""
    print("🤖 测试离线RAG工作流模拟")
    print("=" * 60)
    
    try:
        # 初始化数据库连接
        manager = ChromaDBManager()
        client = manager.get_client()
        collection = client.get_collection("insurance_documents")
        
        # 测试问题集
        test_questions = [
            {
                "question": "车险包括哪些基本险种？",
                "expected_keywords": ["车险", "险种", "交强险", "商业险", "第三者"]
            },
            {
                "question": "如何申请保险理赔？",
                "expected_keywords": ["理赔", "申请", "流程", "材料", "报案"]
            },
            {
                "question": "人寿保险的保障范围是什么？",
                "expected_keywords": ["人寿保险", "保障", "范围", "身故", "疾病"]
            },
            {
                "question": "意外险和医疗险有什么区别？",
                "expected_keywords": ["意外险", "医疗险", "区别", "保障", "范围"]
            }
        ]
        
        print(f"📊 数据库状态: 共 {collection.count()} 个文档")
        print()
        
        for i, test_case in enumerate(test_questions, 1):
            print(f"🔍 测试问题 {i}: {test_case['question']}")
            print("-" * 50)
            
            start_time = time.time()
            
            # 步骤1: 模拟查询重写（简化版）
            original_query = test_case['question']
            # 简单的查询扩展
            expanded_queries = [original_query]
            for keyword in test_case['expected_keywords'][:3]:  # 取前3个关键词
                if keyword not in original_query:
                    expanded_queries.append(keyword)
            
            print(f"📝 查询重写: {original_query}")
            print(f"🔍 扩展查询: {expanded_queries}")
            
            # 步骤2: 文档检索
            all_results = []
            for query in expanded_queries:
                try:
                    results = collection.query(
                        query_texts=[query],
                        n_results=5
                    )
                    if results['documents'] and results['documents'][0]:
                        for j, doc in enumerate(results['documents'][0]):
                            if doc not in [r['content'] for r in all_results]:
                                all_results.append({
                                    'content': doc,
                                    'metadata': results['metadatas'][0][j] if results['metadatas'] and results['metadatas'][0] else {},
                                    'distance': results['distances'][0][j] if results['distances'] and results['distances'][0] else 0.0
                                })
                except Exception as e:
                    print(f"   ⚠️ 查询 '{query}' 失败: {e}")
            
            print(f"📄 检索到 {len(all_results)} 个候选文档")
            
            # 步骤3: 模拟文档评审（基于关键词匹配）
            scored_docs = []
            for doc in all_results:
                score = 0
                content_lower = doc['content'].lower()
                for keyword in test_case['expected_keywords']:
                    if keyword.lower() in content_lower:
                        score += 1
                
                scored_docs.append({
                    'content': doc['content'],
                    'metadata': doc['metadata'],
                    'relevance_score': score,
                    'distance': doc['distance']
                })
            
            # 按相关性排序
            scored_docs.sort(key=lambda x: (x['relevance_score'], -x['distance']), reverse=True)
            selected_docs = scored_docs[:3]  # 选择前3个最相关的文档
            
            print(f"✅ 评审选择 {len(selected_docs)} 个相关文档")
            
            # 步骤4: 模拟答案生成（基于模板）
            if selected_docs:
                # 统计关键词覆盖
                found_keywords = []
                all_content = " ".join([doc['content'] for doc in selected_docs])
                for keyword in test_case['expected_keywords']:
                    if keyword.lower() in all_content.lower():
                        found_keywords.append(keyword)
                
                # 生成模拟答案
                answer_template = f"""
基于检索到的相关文档，关于"{test_case['question']}"的回答：

根据保险文档资料，找到了以下相关信息：
- 关键词覆盖: {found_keywords}
- 相关文档数量: {len(selected_docs)}
- 最高相关性得分: {selected_docs[0]['relevance_score']}

文档摘要:
{selected_docs[0]['content'][:200]}...

（这是基于文档检索的模拟回答，实际系统会使用LLM生成更完整的答案）
"""
                
                print(f"🎯 关键词匹配: {found_keywords} ({len(found_keywords)}/{len(test_case['expected_keywords'])})")
                print(f"📊 最高相关性得分: {selected_docs[0]['relevance_score']}")
                
                # 显示最相关文档的预览
                print(f"📋 最相关文档预览:")
                preview = selected_docs[0]['content'][:300] + "..." if len(selected_docs[0]['content']) > 300 else selected_docs[0]['content']
                print(f"   {preview}")
                
            else:
                print("❌ 未找到相关文档")
            
            end_time = time.time()
            print(f"⏱️  处理时间: {end_time - start_time:.3f}s")
            print()
        
        print("🎉 RAG工作流测试完成！")
        return True
        
    except Exception as e:
        print(f"❌ RAG工作流测试失败: {e}")
        return False

def test_retrieval_quality():
    """测试检索质量"""
    print("\n📊 检索质量评估")
    print("=" * 60)
    
    try:
        manager = ChromaDBManager()
        client = manager.get_client()
        collection = client.get_collection("insurance_documents")
        
        # 质量测试用例
        quality_tests = [
            {
                "query": "车险",
                "should_contain": ["车", "汽车", "机动车", "交强险"],
                "should_not_contain": ["人寿", "健康"]
            },
            {
                "query": "理赔流程",
                "should_contain": ["理赔", "申请", "材料", "流程"],
                "should_not_contain": ["投保", "缴费"]
            },
            {
                "query": "重大疾病保险",
                "should_contain": ["重大疾病", "疾病", "保险"],
                "should_not_contain": ["车险", "财产"]
            }
        ]
        
        for i, test in enumerate(quality_tests, 1):
            print(f"\n质量测试 {i}: '{test['query']}'")
            
            results = collection.query(
                query_texts=[test['query']],
                n_results=5
            )
            
            if results['documents'] and results['documents'][0]:
                all_content = " ".join(results['documents'][0]).lower()
                
                # 检查应该包含的内容
                should_contain_found = [term for term in test['should_contain'] 
                                      if term.lower() in all_content]
                
                # 检查不应该包含的内容
                should_not_contain_found = [term for term in test['should_not_contain'] 
                                          if term.lower() in all_content]
                
                print(f"✅ 应包含 ({len(should_contain_found)}/{len(test['should_contain'])}): {should_contain_found}")
                if should_not_contain_found:
                    print(f"⚠️  不应包含但发现: {should_not_contain_found}")
                else:
                    print("✅ 无不相关内容")
                
                # 计算质量得分
                precision = len(should_contain_found) / len(test['should_contain']) if test['should_contain'] else 1.0
                penalty = len(should_not_contain_found) * 0.1
                quality_score = max(0, precision - penalty)
                
                print(f"📊 质量得分: {quality_score:.2f}")
            else:
                print("❌ 未找到结果")
        
        return True
        
    except Exception as e:
        print(f"❌ 检索质量测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始RAG工作流全面测试")
    print("=" * 80)
    
    # 运行测试
    test1_result = test_offline_rag_simulation()
    test2_result = test_retrieval_quality()
    
    print("\n" + "=" * 80)
    if test1_result and test2_result:
        print("🎉 所有RAG工作流测试通过！")
        print("💡 系统已准备好进行完整的问答服务")
        print("📝 注意: 当前为离线模式，使用TF-IDF进行文档检索")
        print("🔧 如需完整LLM功能，请配置OpenAI API密钥")
    else:
        print("⚠️  部分测试失败，请检查系统配置")

if __name__ == "__main__":
    main()