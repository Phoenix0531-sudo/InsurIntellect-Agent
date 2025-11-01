#!/usr/bin/env python3
"""
重置代理实例的脚本
"""

import sys
import os
from app.core.app_logging import setup_logging, get_logger

# 添加项目路径
sys.path.insert(0, os.path.abspath('.'))

# 初始化日志
logger = setup_logging()

def reset_agent_instance():
    """重置代理实例"""
    try:
        logger.info("🔄 正在重置代理实例...")
        
        # 导入reset_agent函数
        from app.core.rag_workflow import reset_agent
        
        # 重置代理实例
        reset_agent()
        logger.info("✅ 代理实例重置成功")
        
        # 测试重新创建代理
        from app.core.rag_workflow import get_agent
        agent = get_agent()
        logger.info(f"✅ 新代理实例创建成功: {type(agent)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 重置代理时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    reset_agent_instance()


