# 硅基流动 API 配置指南

## 概述
硅基流动（SiliconFlow）是一个提供大语言模型API服务的平台。本项目已配置为使用硅基流动的API服务。

## 配置步骤

### 1. 获取API密钥
1. 访问 [硅基流动官网](https://siliconflow.cn)
2. 注册账号并登录
3. 在控制台中获取您的API密钥

### 2. 配置环境变量
在项目根目录的 `.env` 文件中，将以下配置项替换为您的真实API密钥：

```env
# OpenAI API Configuration (现在使用硅基流动)
OPENAI_API_KEY=your_siliconflow_api_key_here_replace_with_real_key
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL=Qwen/Qwen2.5-7B-Instruct

# 硅基流动 SiliconFlow API配置
SILICONFLOW_API_KEY=your_siliconflow_api_key_here_replace_with_real_key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=Qwen/Qwen2.5-7B-Instruct
```

### 3. 支持的模型
硅基流动支持多种模型，推荐使用：
- `Qwen/Qwen2.5-7B-Instruct` - 通义千问2.5-7B指令模型
- `Qwen/Qwen2.5-14B-Instruct` - 通义千问2.5-14B指令模型
- `deepseek-ai/DeepSeek-V2.5` - DeepSeek V2.5模型

### 4. API兼容性
硅基流动的API与OpenAI API完全兼容，因此项目中的OpenAI客户端可以直接使用硅基流动的服务，只需要修改：
- `base_url` 为 `https://api.siliconflow.cn/v1`
- `api_key` 为您的硅基流动API密钥
- `model` 为硅基流动支持的模型名称

### 5. 测试配置
配置完成后，可以通过以下方式测试：

1. 重启应用服务器
2. 访问健康检查端点：`GET /api/v1/health/`
3. 测试查询端点：`POST /api/v1/query/`

### 6. 注意事项
- 请妥善保管您的API密钥，不要将其提交到版本控制系统
- 硅基流动有使用配额限制，请根据需要选择合适的套餐
- 如果遇到API调用问题，请检查网络连接和API密钥是否正确

## 故障排除

### 常见错误
1. **401 Unauthorized**: API密钥错误或已过期
2. **429 Too Many Requests**: 超出API调用频率限制
3. **500 Internal Server Error**: 服务器内部错误，请稍后重试

### 解决方案
1. 检查API密钥是否正确配置
2. 确认网络连接正常
3. 查看硅基流动控制台的使用情况和配额
4. 检查模型名称是否正确

## 参考链接
- [硅基流动官网](https://siliconflow.cn)
- [硅基流动API文档](https://docs.siliconflow.cn/cn/api-reference/chat-completions/chat-completions)
- [支持的模型列表](https://docs.siliconflow.cn/cn/models)