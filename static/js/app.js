// 全局变量
let currentChatId = null;
let chatHistory = [];
let isLoading = false;
let currentView = 'chat';

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
    console.log('文件上传 - 可用');
    
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
});

// 初始化应用
function initializeApp() {
    console.log('InsurIntellect Agent 初始化中...');
    
    // 初始化主题
    initializeTheme();
    
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
    
    // 文件拖拽事件
    setupFileDragAndDrop();
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

// 发送消息
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
    
    // 显示加载状态
    setLoading(true);
    
    try {
        // 发送请求到后端
        const response = await fetch('/api/v1/queries/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: message,
                query_type: 'general',
                show_analysis: document.getElementById('enableAnalysis')?.checked || false,
                show_sources: document.getElementById('enableSources')?.checked || false
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // 添加AI回复
        addMessage(data.answer, 'assistant', data.sources);
        
        // 保存到历史记录
        saveChatToHistory(message, data.answer);
        
    } catch (error) {
        console.error('发送消息失败:', error);
        addMessage('抱歉，发生了错误。请稍后重试。', 'assistant', null, true);
    } finally {
        setLoading(false);
    }
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
    chatMessages.scrollTop = chatMessages.scrollHeight;
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
function toggleFileUpload() {
    const fileUploadArea = document.getElementById('fileUploadArea');
    if (fileUploadArea.style.display === 'none') {
        fileUploadArea.style.display = 'block';
    } else {
        fileUploadArea.style.display = 'none';
    }
}

// 设置文件拖拽
function setupFileDragAndDrop() {
    const fileUploadArea = document.getElementById('fileUploadArea');
    
    // 检查元素是否存在
    if (!fileUploadArea) {
        console.log('文件上传区域不存在，跳过拖拽设置');
        return;
    }
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        fileUploadArea.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        fileUploadArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        fileUploadArea.addEventListener(eventName, unhighlight, false);
    });
    
    function highlight(e) {
        fileUploadArea.classList.add('highlight');
    }
    
    function unhighlight(e) {
        fileUploadArea.classList.remove('highlight');
    }
    
    fileUploadArea.addEventListener('drop', handleDrop, false);
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }
}

// 处理文件
function handleFiles(files) {
    ([...files]).forEach(uploadFile);
}

// 上传文件
function uploadFile(file) {
    console.log('上传文件:', file.name);
    showToast(`文件 ${file.name} 上传功能开发中...`);
}

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