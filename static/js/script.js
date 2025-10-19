// 全局变量
let currentView = 'chat';
let isLoading = false;
let chatHistory = [];
let currentConversationId = null;

// DOM 元素
const elements = {
    sidebar: null,
    navItems: null,
    views: null,
    chatInput: null,
    sendButton: null,
    chatMessages: null,
    loadingOverlay: null,
    promptCards: null
};

// 初始化应用
document.addEventListener('DOMContentLoaded', function() {
    initializeElements();
    initializeEventListeners();
    initializeUI();
    checkSystemStatus();
    
    // 添加平滑的页面加载动画
    document.body.style.opacity = '0';
    setTimeout(() => {
        document.body.style.transition = 'opacity 0.5s ease';
        document.body.style.opacity = '1';
    }, 100);
});

// 初始化DOM元素引用
function initializeElements() {
    elements.sidebar = document.querySelector('.sidebar');
    elements.navItems = document.querySelectorAll('.nav-item');
    elements.views = document.querySelectorAll('.view');
    elements.chatInput = document.getElementById('chat-input');
    elements.sendButton = document.querySelector('.send-button');
    elements.chatMessages = document.querySelector('.chat-messages');
    elements.loadingOverlay = document.querySelector('.loading-overlay');
    elements.promptCards = document.querySelectorAll('.prompt-card');
}

// 初始化事件监听器
function initializeEventListeners() {
    // 导航切换
    elements.navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetView = item.dataset.view;
            if (targetView) {
                switchView(targetView);
                updateActiveNavItem(item);
            }
        });
    });

    // 聊天输入
    if (elements.chatInput) {
        elements.chatInput.addEventListener('keydown', handleChatInputKeydown);
        elements.chatInput.addEventListener('input', handleChatInputChange);
    }

    // 发送按钮
    if (elements.sendButton) {
        elements.sendButton.addEventListener('click', handleSendMessage);
    }

    // 建议提示卡片
    elements.promptCards.forEach(card => {
        card.addEventListener('click', () => {
            const promptText = card.querySelector('.prompt-title').textContent;
            if (elements.chatInput) {
                elements.chatInput.value = promptText;
                elements.chatInput.focus();
                handleSendMessage();
            }
        });
    });

    // 窗口大小变化
    window.addEventListener('resize', handleWindowResize);

    // 键盘快捷键
    document.addEventListener('keydown', handleGlobalKeydown);
}

// 初始化UI状态
function initializeUI() {
    // 设置默认视图
    switchView('chat');
    
    // 设置聊天输入焦点
    if (elements.chatInput) {
        elements.chatInput.focus();
    }

    // 初始化字符计数器
    updateCharCounter();

    // 添加欢迎消息动画
    animateWelcomeSection();
}

// 视图切换
function switchView(viewName) {
    if (currentView === viewName) return;

    const currentViewElement = document.querySelector(`.view[data-view="${currentView}"]`);
    const targetViewElement = document.querySelector(`.view[data-view="${viewName}"]`);

    if (!targetViewElement) return;

    // 淡出当前视图
    if (currentViewElement) {
        currentViewElement.style.opacity = '0';
        currentViewElement.style.transform = 'translateY(10px)';
        
        setTimeout(() => {
            currentViewElement.classList.remove('active');
            
            // 淡入目标视图
            targetViewElement.classList.add('active');
            targetViewElement.style.opacity = '0';
            targetViewElement.style.transform = 'translateY(10px)';
            
            requestAnimationFrame(() => {
                targetViewElement.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                targetViewElement.style.opacity = '1';
                targetViewElement.style.transform = 'translateY(0)';
            });
        }, 150);
    } else {
        targetViewElement.classList.add('active');
    }

    currentView = viewName;

    // 根据视图执行特定初始化
    switch (viewName) {
        case 'chat':
            if (elements.chatInput) {
                setTimeout(() => elements.chatInput.focus(), 300);
            }
            break;
        case 'analysis':
            loadAnalysisData();
            break;
        case 'history':
            loadHistoryData();
            break;
    }
}

// 更新活跃导航项
function updateActiveNavItem(activeItem) {
    elements.navItems.forEach(item => {
        item.classList.remove('active');
        // 添加点击动画
        item.style.transform = 'scale(0.95)';
        setTimeout(() => {
            item.style.transform = 'scale(1)';
        }, 100);
    });
    
    activeItem.classList.add('active');
    
    // 添加激活动画
    activeItem.style.transform = 'scale(1.05)';
    setTimeout(() => {
        activeItem.style.transform = 'scale(1)';
    }, 200);
}

// 处理聊天输入键盘事件
function handleChatInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
    }
    
    // 自动调整文本框高度
    autoResizeTextarea(e.target);
}

// 处理聊天输入变化
function handleChatInputChange(e) {
    updateCharCounter();
    updateSendButtonState();
    autoResizeTextarea(e.target);
}

// 自动调整文本框高度
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    const newHeight = Math.min(textarea.scrollHeight, 120);
    textarea.style.height = newHeight + 'px';
}

// 更新字符计数器
function updateCharCounter() {
    const counter = document.querySelector('.char-counter');
    if (counter && elements.chatInput) {
        const currentLength = elements.chatInput.value.length;
        const maxLength = 2000;
        counter.textContent = `${currentLength}/${maxLength}`;
        
        if (currentLength > maxLength * 0.9) {
            counter.style.color = 'var(--accent-warning)';
        } else {
            counter.style.color = 'var(--text-muted)';
        }
    }
}

// 更新发送按钮状态
function updateSendButtonState() {
    if (elements.sendButton && elements.chatInput) {
        const hasContent = elements.chatInput.value.trim().length > 0;
        elements.sendButton.disabled = !hasContent || isLoading;
        
        if (hasContent && !isLoading) {
            elements.sendButton.style.background = 'var(--accent-primary)';
            elements.sendButton.style.transform = 'scale(1)';
        } else {
            elements.sendButton.style.background = 'var(--text-muted)';
            elements.sendButton.style.transform = 'scale(0.9)';
        }
    }
}

// 处理发送消息
async function handleSendMessage() {
    if (!elements.chatInput || isLoading) return;
    
    const message = elements.chatInput.value.trim();
    if (!message) return;

    // 添加用户消息到界面
    addMessageToChat('user', message);
    
    // 清空输入框
    elements.chatInput.value = '';
    elements.chatInput.style.height = 'auto';
    updateCharCounter();
    updateSendButtonState();

    // 显示加载状态
    showLoading();
    
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
                show_analysis: document.getElementById('show-analysis')?.checked || false,
                show_sources: document.getElementById('show-sources')?.checked || false
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        // 添加AI回复到界面
        addMessageToChat('assistant', data.answer);
        
        // 如果有分析信息，也显示出来
        if (data.analysis && document.getElementById('show-analysis')?.checked) {
            addMessageToChat('assistant', `分析过程: ${data.analysis}`, false, 'analysis');
        }
        
        // 如果有来源信息，也显示出来
        if (data.sources && document.getElementById('show-sources')?.checked) {
            const sourcesText = data.sources.map(source => `来源: ${source.filename} (相似度: ${source.similarity})`).join('\n');
            addMessageToChat('assistant', sourcesText, false, 'sources');
        }

    } catch (error) {
        console.error('Error sending message:', error);
        addMessageToChat('assistant', '抱歉，发生了错误。请稍后再试。', true);
    } finally {
        hideLoading();
    }
}

// 添加消息到聊天界面
function addMessageToChat(sender, content, isError = false, messageType = 'normal') {
    if (!elements.chatMessages) return;

    // 隐藏欢迎区域
    const welcomeSection = document.querySelector('.welcome-section');
    if (welcomeSection) {
        welcomeSection.style.opacity = '0';
        welcomeSection.style.transform = 'translateY(-20px)';
        setTimeout(() => {
            welcomeSection.style.display = 'none';
        }, 300);
    }

    const messageElement = document.createElement('div');
    messageElement.className = `message ${sender} ${messageType}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    
    // 根据消息类型设置不同的头像
    if (sender === 'user') {
        avatar.textContent = 'U';
    } else {
        if (messageType === 'analysis') {
            avatar.innerHTML = '<i class="fas fa-chart-line"></i>';
        } else if (messageType === 'sources') {
            avatar.innerHTML = '<i class="fas fa-book"></i>';
        } else {
            avatar.textContent = 'AI';
        }
    }
    
    const content_div = document.createElement('div');
    content_div.className = 'message-content';
    
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    if (isError) {
        bubble.style.background = 'var(--accent-error)';
        bubble.style.color = 'white';
    } else if (messageType === 'analysis') {
        bubble.style.background = 'var(--accent-info)';
        bubble.style.borderLeft = '4px solid var(--accent-primary)';
    } else if (messageType === 'sources') {
        bubble.style.background = 'var(--accent-success)';
        bubble.style.borderLeft = '4px solid var(--accent-secondary)';
    }
    bubble.textContent = content;
    
    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = new Date().toLocaleTimeString();
    
    content_div.appendChild(bubble);
    content_div.appendChild(time);
    messageElement.appendChild(avatar);
    messageElement.appendChild(content_div);
    
    // 添加进入动画
    messageElement.style.opacity = '0';
    messageElement.style.transform = 'translateY(20px)';
    
    elements.chatMessages.appendChild(messageElement);
    
    // 触发动画
    requestAnimationFrame(() => {
        messageElement.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        messageElement.style.opacity = '1';
        messageElement.style.transform = 'translateY(0)';
    });
    
    // 滚动到底部
    scrollToBottom();
    
    // 添加到历史记录
    chatHistory.push({
        sender,
        content,
        timestamp: new Date().toISOString(),
        isError,
        messageType
    });
}

// 滚动到底部
function scrollToBottom() {
    if (elements.chatMessages) {
        setTimeout(() => {
            const scrollOptions = {
                top: elements.chatMessages.scrollHeight,
                behavior: 'smooth'
            };
            elements.chatMessages.scrollTo(scrollOptions);
        }, 100);
    }
}

// 显示加载状态
function showLoading() {
    isLoading = true;
    updateSendButtonState();
    
    if (elements.loadingOverlay) {
        elements.loadingOverlay.classList.add('show');
    }
    
    // 添加打字指示器
    addTypingIndicator();
}

// 隐藏加载状态
function hideLoading() {
    isLoading = false;
    updateSendButtonState();
    
    if (elements.loadingOverlay) {
        elements.loadingOverlay.classList.remove('show');
    }
    
    // 移除打字指示器
    removeTypingIndicator();
}

// 添加打字指示器
function addTypingIndicator() {
    const existingIndicator = document.querySelector('.typing-indicator');
    if (existingIndicator) return;

    const indicator = document.createElement('div');
    indicator.className = 'message assistant typing-indicator';
    indicator.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    
    // 添加打字动画样式
    const style = document.createElement('style');
    style.textContent = `
        .typing-dots {
            display: flex;
            gap: 4px;
            align-items: center;
        }
        .typing-dots span {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--text-muted);
            animation: typing 1.4s infinite ease-in-out;
        }
        .typing-dots span:nth-child(1) { animation-delay: -0.32s; }
        .typing-dots span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes typing {
            0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
            40% { transform: scale(1); opacity: 1; }
        }
    `;
    document.head.appendChild(style);
    
    elements.chatMessages.appendChild(indicator);
    scrollToBottom();
}

// 移除打字指示器
function removeTypingIndicator() {
    const indicator = document.querySelector('.typing-indicator');
    if (indicator) {
        indicator.style.opacity = '0';
        setTimeout(() => {
            indicator.remove();
        }, 300);
    }
}

// 欢迎区域动画
function animateWelcomeSection() {
    const welcomeSection = document.querySelector('.welcome-section');
    if (!welcomeSection) return;

    const elements = welcomeSection.querySelectorAll('.welcome-icon, .welcome-content h2, .welcome-content p, .prompt-card');
    
    elements.forEach((el, index) => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        
        setTimeout(() => {
            el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
            el.style.opacity = '1';
            el.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

// 初始化应用
function initializeApp() {
    console.log('初始化应用...');
    
    // 检查系统状态
    checkSystemStatus();
    
    // 加载聊天历史
    loadChatHistory();
    
    // 设置事件监听器
    setupEventListeners();
    
    // 初始化UI
    initializeUI();
    
    // 加载分析数据
    loadAnalysisData();
    
    console.log('应用初始化完成');
}

// 加载分析数据
async function loadAnalysisData() {
    const analysisCards = document.querySelectorAll('.analysis-card .card-content');
    
    analysisCards.forEach(card => {
        card.innerHTML = '<div class="empty-state">正在加载数据...</div>';
    });

    try {
        const response = await fetch('/api/analysis');
        const data = await response.json();
        
        // 更新分析卡片内容
        updateAnalysisCards(data);
        
    } catch (error) {
        analysisCards.forEach(card => {
            card.innerHTML = '<div class="empty-state">加载失败</div>';
        });
    }
}

// 更新分析卡片
function updateAnalysisCards(data) {
    // 这里可以根据实际的分析数据结构来更新卡片内容
    const cards = document.querySelectorAll('.analysis-card');
    
    cards.forEach((card, index) => {
        const content = card.querySelector('.card-content');
        if (content) {
            // 添加淡入动画
            content.style.opacity = '0';
            setTimeout(() => {
                content.innerHTML = `<div class="empty-state">分析数据 ${index + 1}</div>`;
                content.style.transition = 'opacity 0.3s ease';
                content.style.opacity = '1';
            }, index * 100);
        }
    });
}

// 加载历史数据
async function loadHistoryData() {
    const historyList = document.querySelector('.history-list');
    if (!historyList) return;

    historyList.innerHTML = '<div class="empty-state">正在加载历史记录...</div>';

    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        
        if (data.length === 0) {
            historyList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📝</div>
                    <h3>暂无历史记录</h3>
                    <p>开始对话后，您的聊天记录将显示在这里</p>
                </div>
            `;
        } else {
            updateHistoryList(data);
        }
        
    } catch (error) {
        historyList.innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

// 更新历史列表
function updateHistoryList(historyData) {
    const historyList = document.querySelector('.history-list');
    if (!historyList) return;

    historyList.innerHTML = '';
    
    historyData.forEach((item, index) => {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        historyItem.innerHTML = `
            <div class="item-header">
                <div class="item-title">${item.title}</div>
                <div class="item-time">${new Date(item.timestamp).toLocaleString()}</div>
            </div>
            <div class="item-content">${item.preview}</div>
        `;
        
        // 添加点击事件
        historyItem.addEventListener('click', () => {
            loadConversation(item.id);
        });
        
        // 添加进入动画
        historyItem.style.opacity = '0';
        historyItem.style.transform = 'translateY(20px)';
        
        historyList.appendChild(historyItem);
        
        setTimeout(() => {
            historyItem.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            historyItem.style.opacity = '1';
            historyItem.style.transform = 'translateY(0)';
        }, index * 50);
    });
}

// 加载对话
function loadConversation(conversationId) {
    currentConversationId = conversationId;
    switchView('chat');
    
    // 这里可以加载具体的对话内容
    // 暂时显示提示信息
    addMessageToChat('assistant', `已加载对话 ${conversationId}`);
}

// 处理窗口大小变化
function handleWindowResize() {
    // 移动端侧边栏处理
    if (window.innerWidth <= 768) {
        if (elements.sidebar) {
            elements.sidebar.classList.remove('open');
        }
    }
}

// 处理全局键盘快捷键
function handleGlobalKeydown(e) {
    // Ctrl/Cmd + K 快速聚焦到搜索框
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (elements.chatInput) {
            elements.chatInput.focus();
        }
    }
    
    // Escape 键关闭加载遮罩
    if (e.key === 'Escape' && elements.loadingOverlay?.classList.contains('show')) {
        hideLoading();
    }
}

// 工具函数：防抖
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 工具函数：节流
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    }
}

// 导出主要函数供外部使用
window.ChatApp = {
    switchView,
    addMessageToChat,
    showLoading,
    hideLoading,
    checkSystemStatus
};