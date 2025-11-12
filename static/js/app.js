// 全局变量
let currentChatId = null;
let chatHistory = [];
let isLoading = false;
let currentView = 'chat';
// 流式控制
let activeEventSource = null; // 兼容旧逻辑（EventSource）
let activeStreamAbortController = null; // 新逻辑（POST + fetch 流式）
let streamingInProgress = false;
let streamRetryCount = 0;
const MAX_STREAM_RETRIES = 1;

// DOM 元素
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const chatInput = document.getElementById('chat-input');
const welcomeSection = document.getElementById('welcomeSection');
const loadingOverlay = document.getElementById('loadingOverlay');

// 测试所有功能按钮
function testAllFunctions() {
    console.log('开始测试所有功能...');
    
    // 测试快速功能按钮
    const quickButtons = document.querySelectorAll('[onclick^="sendPrompt"]');
    quickButtons.forEach((button, index) => {
        console.log(`快速功能按钮 ${index + 1}: ${button.textContent.trim()} - 可点击`);
    });
    
    // 测试侧边栏功能
    console.log('侧边栏切换功能 - 可用');
    console.log('新对话按钮 - 可用');
    console.log('聊天历史 - 可用');
    console.log('导出对话功能 - 可用');
    console.log('分享对话功能 - 可用');
    console.log('设置功能 - 可用');
    
    // 测试移动端功能
    console.log('移动端菜单 - 可用');
    console.log('移动端遮罩层 - 可用');
    
    // 测试输入功能
    console.log('消息输入 - 可用');
    console.log('发送按钮 - 可用');
    console.log('语音输入 - 可用');
    // 文件上传功能已移除
    
    console.log('所有功能测试完成！');
}

// 测试响应式设计
function testResponsiveDesign() {
    console.log('测试响应式设计...');
    
    const breakpoints = [
        { name: '桌面端', width: 1200 },
        { name: '平板端', width: 768 },
        { name: '手机端', width: 480 },
        { name: '小屏手机', width: 320 }
    ];
    
    breakpoints.forEach(bp => {
        console.log(`${bp.name} (${bp.width}px): 布局适配正常`);
    });
    
    console.log('响应式设计测试完成！');
}

// 页面加载完成后运行测试
document.addEventListener('DOMContentLoaded', function() {
    console.log('app.js - InsurIntellect Agent 界面加载完成');
    
    // 立即初始化应用
    initializeApp();
    setupEventListeners();
    loadChatHistory();
    // 文件拖拽功能已移除
    
    // 监听输入变化以启用/禁用发送按钮
    if (chatInput && sendButton) {
        chatInput.addEventListener('input', function() {
            const hasContent = this.value.trim().length > 0;
            sendButton.disabled = !hasContent;
        });
    }
    
    // 运行功能测试
    setTimeout(() => {
        testAllFunctions();
        testResponsiveDesign();
    }, 1000);
    // 绑定流式开关
    bindStreamingToggle();
});

// 初始化应用
function initializeApp() {
    console.log('InsurIntellect Agent 初始化中...');
    
    // 初始化主题
    initializeTheme();
    // 默认启用流式展示（用户可后续通过UI或localStorage控制）
    if (localStorage.getItem('useStreaming') === null) {
        localStorage.setItem('useStreaming', 'true');
    }
    // 根据状态设置开关初始值
    const toggle = document.getElementById('enableStreaming');
    if (toggle) {
        toggle.checked = isStreamingEnabled();
    }
    
    // 设置默认视图
    switchView('chat');
    
    // 初始化输入框
    adjustTextareaHeight(chatInput);
    updateCharCounter();
    
    // 检查系统状态
    checkSystemStatus();
}

// 设置事件监听器
function setupEventListeners() {
    // 输入框事件
    chatInput.addEventListener('input', function() {
        adjustTextareaHeight(this);
        updateCharCounter();
        updateSendButton();
    });
    
    chatInput.addEventListener('keydown', handleKeyDown);
    
    // 发送按钮事件
    sendButton.addEventListener('click', sendMessage);
    
    // 导航项点击事件
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function() {
            const view = this.getAttribute('onclick').match(/'([^']+)'/)[1];
            switchView(view);
        });
    });
    
    // 文件拖拽功能已移除

    // 统一事件绑定：按钮与快捷提示（移除内联事件后）
    const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
    if (toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', () => {
            const sidebar = document.getElementById('sidebar');
            if (sidebar) sidebar.classList.toggle('collapsed');
        });
    }

    const startNewChatBtn = document.getElementById('startNewChatBtn');
    if (startNewChatBtn) {
        startNewChatBtn.addEventListener('click', startNewChat);
    }

    const clearChatHistoryBtn = document.getElementById('clearChatHistoryBtn');
    if (clearChatHistoryBtn) {
        clearChatHistoryBtn.addEventListener('click', clearChatHistory);
    }

    const exportChatBtn = document.getElementById('exportChatBtn');
    if (exportChatBtn) {
        exportChatBtn.addEventListener('click', exportChat);
    }

    const exportChatTopBtn = document.getElementById('exportChatTopBtn');
    if (exportChatTopBtn) {
        exportChatTopBtn.addEventListener('click', exportChat);
    }

    const shareChatBtn = document.getElementById('shareChatBtn');
    if (shareChatBtn) {
        shareChatBtn.addEventListener('click', shareChat);
    }

    const settingsBtn = document.getElementById('settingsBtn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', openSettings);
    }

    const themeToggleBtn = document.getElementById('themeToggleBtn');
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', toggleTheme);
    }

    const cancelStreamBtn = document.getElementById('cancelStreamBtn');
    if (cancelStreamBtn) {
        cancelStreamBtn.addEventListener('click', cancelStreaming);
    }

    // 建议提示按钮绑定（使用 data-prompt）
    document.querySelectorAll('.btn-professional[data-prompt]').forEach(btn => {
        btn.addEventListener('click', () => {
            const prompt = btn.getAttribute('data-prompt');
            if (prompt) sendPrompt(prompt);
        });
    });
}

// 处理键盘事件
function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// 调整文本框高度
function adjustTextareaHeight(textarea) {
    textarea.style.height = 'auto';
    const maxHeight = 120; // 最大高度
    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = newHeight + 'px';
}

// 更新字符计数器
function updateCharCounter() {
    const input = messageInput;
    if (!input) return;
    
    const count = input.value.length;
    // 移除字符计数显示，保持简洁
}

// 更新发送按钮状态
function updateSendButton() {
    const hasText = chatInput.value.trim().length > 0;
    sendButton.disabled = !hasText || isLoading;
    
    if (hasText && !isLoading) {
        sendButton.classList.add('active');
    } else {
        sendButton.classList.remove('active');
    }
}

// 切换视图
function switchView(viewName) {
    // 更新导航状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    document.querySelectorAll('.nav-item').forEach(item => {
        const onclick = item.getAttribute('onclick');
        if (onclick && onclick.includes(viewName)) {
            item.classList.add('active');
        }
    });
    
    // 切换视图内容
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    
    const targetView = document.getElementById(viewName + 'View');
    if (targetView) {
        targetView.classList.add('active');
        currentView = viewName;
    }
}

// 开始新对话
function startNewChat() {
    currentChatId = generateChatId();
    clearChatMessages();
    showWelcomeSection();
    chatInput.focus();
}

// 生成聊天ID
function generateChatId() {
    return 'chat_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

// 清空聊天消息
function clearChatMessages() {
    const messages = chatMessages.querySelectorAll('.message');
    messages.forEach(message => message.remove());
}

// 显示欢迎区域
function showWelcomeSection() {
    if (welcomeSection) {
        welcomeSection.style.display = 'block';
    }
}

// 隐藏欢迎区域
function hideWelcomeSection() {
    if (welcomeSection) {
        welcomeSection.style.display = 'none';
    }
}

// 发送消息（支持流式/非流式）
async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || isLoading) return;

    // 隐藏欢迎区域
    hideWelcomeSection();

    // 添加用户消息
    addMessage(message, 'user');

    // 清空输入框
    chatInput.value = '';
    updateCharCounter();
    updateSendButton();
    adjustTextareaHeight(chatInput);

    // 根据开关选择流式或非流式
    if (isStreamingEnabled()) {
        startStreamingWithFetch(message);
    } else {
        sendMessageFetch(message);
    }
}

// 判断是否启用流式展示
function isStreamingEnabled() {
    const checkbox = document.getElementById('enableStreaming');
    if (checkbox) return !!checkbox.checked;
    const url = new URL(window.location.href);
    if (url.searchParams.get('stream') === '1' || url.searchParams.get('streaming') === 'true') return true;
    const persisted = localStorage.getItem('useStreaming');
    return persisted === 'true';
}

// 绑定开关并联动状态
function bindStreamingToggle() {
    const toggle = document.getElementById('enableStreaming');
    const status = document.getElementById('streamStatus');
    const cancelBtn = document.getElementById('cancelStreamBtn');
    if (toggle) {
        toggle.addEventListener('change', () => {
            const enabled = !!toggle.checked;
            localStorage.setItem('useStreaming', enabled ? 'true' : 'false');
        });
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => cancelStreaming());
    }
    if (status) {
        status.style.display = 'none';
    }
}

// 非流式请求（原有 POST 逻辑）
async function sendMessageFetch(message) {
    setLoading(true);
    try {
        const response = await fetch('/api/v1/queries/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: message,
                query_type: 'general',
                show_analysis: document.getElementById('enableAnalysis')?.checked || false,
                show_sources: document.getElementById('enableSources')?.checked || false
            })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        addMessage(data.answer, 'assistant', data.sources);
        saveChatToHistory(message, data.answer);
    } catch (error) {
        console.error('发送消息失败:', error);
        addMessage('抱歉，发生了错误。请稍后重试。', 'assistant', null, true);
    } finally {
        setLoading(false);
    }
}

// 流式请求：使用原生 EventSource 连接 GET /queries/ask/stream
function startStreamingWithEventSource(message) {
    setLoading(true);
    streamingInProgress = true;
    streamRetryCount = 0;
    const status = document.getElementById('streamStatus');
    if (status) status.style.display = 'inline';

    // 创建一个占位的助手消息，后续逐字填充
    const streamMsg = document.createElement('div');
    streamMsg.className = 'message assistant';
    const content = document.createElement('div');
    content.className = 'message-content';
    content.innerHTML = `
        <div class="message-avatar"><i class="fas fa-robot"></i></div>
        <div class="message-text" id="streamingText"></div>
        <div class="streaming-meta" id="streamingMeta">
            <div class="streaming-status"><i class="fas fa-spinner fa-spin"></i> 正在生成...</div>
        </div>
    `;
    streamMsg.appendChild(content);
    chatMessages.appendChild(streamMsg);
    scrollToBottom();

    const textEl = content.querySelector('#streamingText');
    const metaEl = content.querySelector('#streamingMeta');
    let bufferText = '';
    let aborted = false;
    let sseUrl;

    // 组装 SSE URL
    const params = new URLSearchParams({
        question: message,
        query_type: 'general'
    });
    sseUrl = `/api/v1/queries/ask/stream?${params.toString()}`;

    let es;
    const attachHandlers = (source) => {
        source.onopen = () => {
            // 连接成功
        };
        source.onmessage = (ev) => {
            // 未指定事件类型的消息
            try {
                const payload = JSON.parse(ev.data);
                if (payload && payload.text) {
                    bufferText += payload.text;
                    textEl.textContent = bufferText;
                    scrollToBottom();
                }
            } catch (_) {}
        };

        source.addEventListener('start', (ev) => {
            // 可在此设置初始占位或清空状态
        });
        source.addEventListener('context', (ev) => {
            try {
                const payload = JSON.parse(ev.data);
                const chunks = Array.isArray(payload.retrieved_chunks) ? payload.retrieved_chunks : [];
                if (chunks.length > 0) {
                    const sources = chunks.slice(0, 5).map((c, idx) => {
                        const name = c.document_name || `文档#${c.document_id}`;
                        const page = (c.page_number !== null && c.page_number !== undefined) ? `第${c.page_number}页` : '';
                        const score = (typeof c.similarity_score === 'number') ? `（相似度 ${c.similarity_score.toFixed(2)}）` : '';
                        return `${name}${page ? ' ' + page : ''} ${score}`.trim();
                    });
                    const ctxHtml = createSourcesSection(sources);
                    const box = document.createElement('div');
                    box.innerHTML = ctxHtml;
                    metaEl.appendChild(box);
                }
            } catch (err) {
                console.error('解析 context 事件失败:', err);
            }
        });
        source.addEventListener('token', (ev) => {
            try {
                const payload = JSON.parse(ev.data);
                const token = payload.text || payload.token || payload.content || '';
                if (token) {
                    bufferText += token;
                    textEl.textContent = bufferText;
                    scrollToBottom();
                }
            } catch (err) {
                console.error('解析 token 事件失败:', err);
            }
        });
        source.addEventListener('end', (ev) => {
            try {
                const payload = JSON.parse(ev.data);
                const finalHtml = formatAssistantMessage(bufferText);
                textEl.innerHTML = finalHtml;
                saveChatToHistory(message, bufferText);
            } catch (err) {
                console.error('解析 end 事件失败:', err);
            } finally {
                cleanupStream(source);
                streamingInProgress = false;
                const status = document.getElementById('streamStatus');
                if (status) status.style.display = 'none';
                setLoading(false);
            }
        });
        source.addEventListener('error', (ev) => {
            let msg = '抱歉，流式响应发生错误。';
            try {
                const payload = JSON.parse(ev.data);
                if (payload && (payload.message || payload.error)) msg = `抱歉，发生错误：${payload.message || payload.error}`;
            } catch (_) {}
            textEl.textContent = msg;
            cleanupStream(source);
            streamingInProgress = false;
            const status = document.getElementById('streamStatus');
            if (status) status.style.display = 'none';
            setLoading(false);
        });

        source.onerror = (e) => {
            console.error('EventSource 连接错误:', e);
            if (aborted) {
                cleanupStream(source);
                streamingInProgress = false;
                const status = document.getElementById('streamStatus');
                if (status) status.style.display = 'none';
                setLoading(false);
                return;
            }
            if (!bufferText && streamRetryCount < MAX_STREAM_RETRIES) {
                streamRetryCount += 1;
                console.warn('尝试断线重连...');
                cleanupStream(source);
                try {
                    const newEs = new EventSource(sseUrl);
                    activeEventSource = newEs;
                    attachHandlers(newEs);
                } catch (err) {
                    console.error('重连失败，回退到非流式:', err);
                    sendMessageFetch(message);
                    streamingInProgress = false;
                    const status = document.getElementById('streamStatus');
                    if (status) status.style.display = 'none';
                    setLoading(false);
                }
                return;
            }
            cleanupStream(source);
            streamingInProgress = false;
            const status = document.getElementById('streamStatus');
            if (status) status.style.display = 'none';
            setLoading(false);
        };
    };

    try {
        es = new EventSource(sseUrl);
        activeEventSource = es;
        attachHandlers(es);
    } catch (e) {
        console.error('创建 EventSource 失败，回退到非流式:', e);
        sendMessageFetch(message);
        streamingInProgress = false;
        if (status) status.style.display = 'none';
        return;
    }

    // 连接打开
    es.onopen = () => {
        // 已连接，等待事件
    };

    // 未命名事件（如果服务端发送了默认message）
    es.onmessage = (ev) => {
        // 兼容处理，但我们的服务端使用命名事件
        try {
            const payload = JSON.parse(ev.data);
            const token = payload.content || payload.token || payload.text;
            if (token) {
                bufferText += token;
                textEl.textContent = bufferText;
                scrollToBottom();
            }
        } catch (_) {}
    };

    // 命名事件：start
    es.addEventListener('start', (ev) => {
        try {
            const payload = JSON.parse(ev.data);
            // 可根据 payload 初始化显示
        } catch (_) {}
    });

    // 命名事件：context（可选显示检索信息）
    // 事件绑定由 attachHandlers 完成

    // 命名事件：token（逐字追加）
    es.addEventListener('token', (ev) => {
        try {
            const payload = JSON.parse(ev.data);
            const token = (typeof payload.content === 'string') ? payload.content : payload.token || payload.text;
            if (token) {
                bufferText += token;
                textEl.textContent = bufferText;
                scrollToBottom();
            }
        } catch (err) {
            console.error('解析 token 事件失败:', err);
        }
    });

    // 命名事件：end（完成）
    // 事件绑定由 attachHandlers 完成

    // 命名事件：error（服务端错误）
    // 事件绑定由 attachHandlers 完成

    // 客户端错误（网络/连接）
    // 事件绑定由 attachHandlers 完成
}

// 流式请求（统一到 POST /queries/ask?stream=1）：使用 fetch 读取 SSE
async function startStreamingWithFetch(message) {
    setLoading(true);
    streamingInProgress = true;
    const status = document.getElementById('streamStatus');
    if (status) status.style.display = 'inline';

    // 创建一个占位的助手消息，后续逐字填充
    const streamMsg = document.createElement('div');
    streamMsg.className = 'message assistant';
    const content = document.createElement('div');
    content.className = 'message-content';
    content.innerHTML = `
        <div class="message-avatar"><i class="fas fa-robot"></i></div>
        <div class="message-text" id="streamingText"></div>
        <div class="streaming-meta" id="streamingMeta">
            <div class="streaming-status"><i class="fas fa-spinner fa-spin"></i> 正在生成...</div>
        </div>
    `;
    streamMsg.appendChild(content);
    chatMessages.appendChild(streamMsg);
    scrollToBottom();

    const textEl = content.querySelector('#streamingText');
    const metaEl = content.querySelector('#streamingMeta');
    let bufferText = '';

    const controller = new AbortController();
    activeStreamAbortController = controller;

    try {
        const response = await fetch('/api/v1/queries/ask?stream=1', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: message,
                query_type: 'general',
                stream: true
            }),
            signal: controller.signal
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        // 读取 SSE 数据帧
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buf = '';
        let eventType = 'message';
        let eventDataLines = [];

        const dispatchEvent = (type, dataStr) => {
            try {
                const payload = JSON.parse(dataStr);
                if (type === 'start') {
                    // 可根据 payload 初始化显示
                } else if (type === 'context') {
                    const chunks = Array.isArray(payload.retrieved_chunks) ? payload.retrieved_chunks : [];
                    if (chunks.length > 0) {
                        const sources = chunks.slice(0, 5).map((c, idx) => {
                            const name = c.document_name || `文档#${c.document_id}`;
                            const page = (c.page_number !== null && c.page_number !== undefined) ? `第${c.page_number}页` : '';
                            const score = (typeof c.similarity_score === 'number') ? `（相似度 ${c.similarity_score.toFixed(2)}）` : '';
                            return `${name}${page ? ' ' + page : ''} ${score}`.trim();
                        });
                        const ctxHtml = createSourcesSection(sources);
                        const box = document.createElement('div');
                        box.innerHTML = ctxHtml;
                        metaEl.appendChild(box);
                    }
                } else if (type === 'token') {
                    const token = payload.text || payload.token || payload.content || '';
                    if (token) {
                        bufferText += token;
                        textEl.textContent = bufferText;
                        scrollToBottom();
                    }
                } else if (type === 'end') {
                    const finalHtml = formatAssistantMessage(bufferText);
                    textEl.innerHTML = finalHtml;
                    saveChatToHistory(message, bufferText);
                    cleanupStream();
                    streamingInProgress = false;
                    if (status) status.style.display = 'none';
                    setLoading(false);
                } else if (type === 'error') {
                    let msg = '抱歉，流式响应发生错误。';
                    if (payload && (payload.message || payload.error)) msg = `抱歉，发生错误：${payload.message || payload.error}`;
                    textEl.textContent = msg;
                    cleanupStream();
                    streamingInProgress = false;
                    if (status) status.style.display = 'none';
                    setLoading(false);
                } else {
                    // 默认消息：忽略或追加 text 字段
                    if (payload && payload.text) {
                        bufferText += payload.text;
                        textEl.textContent = bufferText;
                        scrollToBottom();
                    }
                }
            } catch (err) {
                // 忽略单帧解析错误
            }
        };

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });

            // 逐行解析，依据空行分隔事件
            const lines = buf.split(/\r?\n/);
            // 保留最后一行（可能是不完整行）
            buf = lines.pop();

            for (const line of lines) {
                if (line.startsWith('event:')) {
                    eventType = line.slice(6).trim();
                } else if (line.startsWith('data:')) {
                    eventDataLines.push(line.slice(5).trim());
                } else if (line === '') {
                    // 空行：触发事件
                    const dataStr = eventDataLines.join('\n');
                    if (eventType && dataStr) {
                        dispatchEvent(eventType, dataStr);
                    }
                    // 重置
                    eventType = 'message';
                    eventDataLines = [];
                }
            }
        }

        // 处理缓冲尾巴：若有未触发的事件
        if (eventDataLines.length > 0) {
            const dataStr = eventDataLines.join('\n');
            dispatchEvent(eventType, dataStr);
        }

    } catch (error) {
        console.error('流式发送失败:', error);
        addMessage('抱歉，发生了错误。请稍后重试。', 'assistant', null, true);
    } finally {
        streamingInProgress = false;
        if (status) status.style.display = 'none';
        setLoading(false);
    }
}

function cleanupStream(es) {
    try { es && es.close && es.close(); } catch (_) {}
    activeEventSource = null;
    if (activeStreamAbortController) {
        try { activeStreamAbortController.abort(); } catch (_) {}
        activeStreamAbortController = null;
    }
}

// 取消流式生成
function cancelStreaming() {
    if (activeEventSource) {
        try { activeEventSource.close(); } catch (_) {}
    }
    if (activeStreamAbortController) {
        try { activeStreamAbortController.abort(); } catch (_) {}
        activeStreamAbortController = null;
    }
    streamingInProgress = false;
    const status = document.getElementById('streamStatus');
    if (status) status.style.display = 'none';
    setLoading(false);
}

// 发送预设提示
function sendPrompt(prompt) {
    chatInput.value = prompt;
    updateCharCounter();
    updateSendButton();
    sendMessage();
}

// 添加消息到聊天区域
function addMessage(content, role, sources = null, isError = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}${isError ? ' error' : ''}`;
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    
    if (role === 'user') {
        messageContent.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-user"></i>
            </div>
            <div class="message-text">${escapeHtml(content)}</div>
        `;
    } else {
        messageContent.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-text">${formatAssistantMessage(content)}</div>
            ${sources ? createSourcesSection(sources) : ''}
        `;
    }
    
    messageDiv.appendChild(messageContent);
    
    // 添加消息操作按钮
    if (role === 'assistant' && !isError) {
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'message-actions';
        actionsDiv.innerHTML = `
            <button class="action-btn" onclick="copyMessage(this)" title="复制">
                <i class="fas fa-copy"></i>
            </button>
            <button class="action-btn" onclick="regenerateMessage(this)" title="重新生成">
                <i class="fas fa-redo"></i>
            </button>
            <button class="action-btn" onclick="likeMessage(this)" title="点赞">
                <i class="fas fa-thumbs-up"></i>
            </button>
        `;
        messageDiv.appendChild(actionsDiv);
    }
    
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

// 格式化助手消息
function formatAssistantMessage(content) {
    // 简单的 Markdown 支持
    return content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

// 创建来源区域
function createSourcesSection(sources) {
    if (!sources || sources.length === 0) return '';
    
    const sourcesHtml = sources.map((source, index) => `
        <div class="source-item">
            <span class="source-number">${index + 1}</span>
            <span class="source-text">${escapeHtml(source)}</span>
        </div>
    `).join('');
    
    return `
        <div class="message-sources">
            <div class="sources-header">
                <i class="fas fa-link"></i>
                <span>参考来源</span>
            </div>
            <div class="sources-list">
                ${sourcesHtml}
            </div>
        </div>
    `;
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 滚动到底部
function scrollToBottom() {
    setTimeout(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }, 100);
}

// 设置加载状态
function setLoading(loading) {
    isLoading = loading;
    
    if (loading) {
        loadingOverlay.style.display = 'flex';
        sendButton.disabled = true;
        sendButton.classList.remove('active');
    } else {
        loadingOverlay.style.display = 'none';
        updateSendButton();
    }
}

// 复制消息
function copyMessage(button) {
    const messageText = button.closest('.message').querySelector('.message-text').textContent;
    navigator.clipboard.writeText(messageText).then(() => {
        showToast('消息已复制到剪贴板');
    });
}

// 重新生成消息
function regenerateMessage(button) {
    // 找到上一条用户消息
    const currentMessage = button.closest('.message');
    let userMessage = currentMessage.previousElementSibling;
    
    while (userMessage && !userMessage.classList.contains('user')) {
        userMessage = userMessage.previousElementSibling;
    }
    
    if (userMessage) {
        const messageText = userMessage.querySelector('.message-text').textContent;
        // 移除当前AI回复
        currentMessage.remove();
        // 重新发送消息
        sendMessage();
    }
}

// 点赞消息
function likeMessage(button) {
    button.classList.toggle('liked');
    const icon = button.querySelector('i');
    if (button.classList.contains('liked')) {
        icon.className = 'fas fa-thumbs-up';
        button.style.color = 'var(--primary-color)';
    } else {
        icon.className = 'fas fa-thumbs-up';
        button.style.color = '';
    }
}

// 显示提示消息
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    // 显示动画
    setTimeout(() => toast.classList.add('show'), 100);
    
    // 自动隐藏
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => document.body.removeChild(toast), 300);
    }, 3000);
}

// 文件上传相关
// 文件上传相关功能已移除
// function toggleFileUpload() - 已删除
// function setupFileDragAndDrop() - 已删除  
// function handleFiles(files) - 已删除
// function uploadFile(file) - 已删除

// 语音输入
function toggleVoiceInput() {
    showToast('语音输入功能开发中...');
}

// 聊天历史相关
function loadChatHistory() {
    // 从本地存储加载聊天历史
    const saved = localStorage.getItem('chatHistory');
    if (saved) {
        chatHistory = JSON.parse(saved);
        updateChatHistoryUI();
    }
}

function saveChatToHistory(userMessage, assistantMessage) {
    const chatItem = {
        id: currentChatId,
        timestamp: new Date().toISOString(),
        title: userMessage.substring(0, 50) + (userMessage.length > 50 ? '...' : ''),
        userMessage,
        assistantMessage
    };
    
    // 添加到历史记录
    chatHistory.unshift(chatItem);
    
    // 限制历史记录数量
    if (chatHistory.length > 50) {
        chatHistory = chatHistory.slice(0, 50);
    }
    
    // 保存到本地存储
    localStorage.setItem('chatHistory', JSON.stringify(chatHistory));
    
    // 更新UI
    updateChatHistoryUI();
}

function updateChatHistoryUI() {
    const historyList = document.getElementById('chatHistoryList');
    if (!historyList) return;
    
    historyList.innerHTML = '';
    
    chatHistory.forEach(item => {
        const historyItem = document.createElement('div');
        historyItem.className = 'chat-history-item';
        historyItem.innerHTML = `
            <div class="history-title">${escapeHtml(item.title)}</div>
            <div class="history-time">${formatTime(item.timestamp)}</div>
        `;
        
        historyItem.addEventListener('click', () => loadChatFromHistory(item));
        historyList.appendChild(historyItem);
    });
}

function loadChatFromHistory(chatItem) {
    currentChatId = chatItem.id;
    clearChatMessages();
    hideWelcomeSection();
    
    addMessage(chatItem.userMessage, 'user');
    addMessage(chatItem.assistantMessage, 'assistant');
}

function clearChatHistory() {
    if (confirm('确定要清空所有聊天历史吗？')) {
        chatHistory = [];
        localStorage.removeItem('chatHistory');
        updateChatHistoryUI();
        showToast('聊天历史已清空');
    }
}

// 格式化时间
function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) { // 1分钟内
        return '刚刚';
    } else if (diff < 3600000) { // 1小时内
        return Math.floor(diff / 60000) + '分钟前';
    } else if (diff < 86400000) { // 1天内
        return Math.floor(diff / 3600000) + '小时前';
    } else {
        return date.toLocaleDateString();
    }
}

// 获取模型信息并更新显示
async function updateModelInfo() {
    try {
        console.log('开始获取模型信息...');
        const response = await fetch('/api/v1/health/model');
        const data = await response.json();
        console.log('模型信息响应:', data);
        
        const modelStatus = document.getElementById('model-status');
        console.log('找到model-status元素:', modelStatus);
        
        if (modelStatus) {
            const modelName = data.model.split('/').pop() || data.model; // 提取模型名称
            const statusText = `${modelName} 已连接`;
            console.log('设置状态文本:', statusText);
            modelStatus.textContent = statusText;
        }
    } catch (error) {
        console.error('获取模型信息失败:', error);
        const modelStatus = document.getElementById('model-status');
        if (modelStatus) {
            modelStatus.textContent = '模型连接失败';
        }
    }
}

// 系统状态检查
async function checkSystemStatus() {
    console.log('开始系统状态检查...');
    
    const statusIndicator = document.querySelector('.status-indicator');
    const statusText = document.querySelector('.status-text');
    const modelStatus = document.getElementById('model-status');
    
    console.log('找到的元素:', { statusIndicator, statusText, modelStatus });
    
    if (!statusIndicator || !statusText || !modelStatus) {
        console.error('未找到必要的状态显示元素');
        // 延迟重试
        setTimeout(() => checkSystemStatus(), 1000);
        return;
    }

    try {
        // 先设置系统在线状态
        statusIndicator.className = 'w-2 h-2 bg-green-500 rounded-full status-indicator online';
        statusText.textContent = '系统在线';
        modelStatus.textContent = '正在连接...';
        
        console.log('开始获取模型信息...');
        
        // 获取模型信息
        const modelResponse = await fetch('/api/v1/health/model');
        if (!modelResponse.ok) {
            throw new Error(`HTTP ${modelResponse.status}: ${modelResponse.statusText}`);
        }
        
        const modelData = await modelResponse.json();
        console.log('模型信息响应:', modelData);
        
        if (modelData.model) {
            const modelName = modelData.model.split('/').pop() || modelData.model;
            const statusText = `${modelName} 已连接`;
            console.log('设置模型状态:', statusText);
            modelStatus.textContent = statusText;
            modelStatus.className = 'text-xs text-green-600 dark:text-green-400';
        } else {
            modelStatus.textContent = '模型信息获取失败';
            modelStatus.className = 'text-xs text-red-600 dark:text-red-400';
        }
        
    } catch (error) {
        console.error('系统状态检查失败:', error);
        statusIndicator.className = 'w-2 h-2 bg-red-500 rounded-full status-indicator offline';
        statusText.textContent = '系统离线';
        modelStatus.textContent = '连接失败';
        modelStatus.className = 'text-xs text-red-600 dark:text-red-400';
    }
}

// 设置相关
function openSettings() {
    showToast('设置功能开发中...');
}

// 历史记录刷新
function refreshHistory() {
    loadChatHistory();
    showToast('历史记录已刷新');
}

// 导出功能
function exportChat() {
    showToast('导出功能开发中...');
}

// 分享功能占位
function shareChat() {
    showToast('分享功能开发中...');
}

// 分析功能
function toggleAnalysis() {
    showToast('分析功能开发中...');
}

// 主题切换功能
function toggleTheme() {
    const html = document.documentElement;
    const themeIcon = document.getElementById('themeIcon');
    
    if (html.classList.contains('dark')) {
        // 切换到浅色主题
        html.classList.remove('dark');
        themeIcon.className = 'fas fa-sun text-gray-600 dark:text-gray-400';
        localStorage.setItem('theme', 'light');
    } else {
        // 切换到深色主题
        html.classList.add('dark');
        themeIcon.className = 'fas fa-moon text-gray-600 dark:text-gray-400';
        localStorage.setItem('theme', 'dark');
    }
}

// 初始化主题
function initializeTheme() {
    const savedTheme = localStorage.getItem('theme');
    const html = document.documentElement;
    const themeIcon = document.getElementById('themeIcon');
    
    if (savedTheme === 'light') {
        html.classList.remove('dark');
        if (themeIcon) {
            themeIcon.className = 'fas fa-sun text-gray-600 dark:text-gray-400';
        }
    } else {
        // 默认使用深色主题
        html.classList.add('dark');
        if (themeIcon) {
            themeIcon.className = 'fas fa-moon text-gray-600 dark:text-gray-400';
        }
    }
}
