// ===== 问题反馈页面逻辑 (feed_back.html) =====
// 依赖: sidebar.ts 已在上方加载

// Toast 工具函数
function showToast(message: string, type: string = 'info') {
    const container = document.getElementById('toast-container')!;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerText = message;
    container.appendChild(toast);

    // 触发淡入动画
    setTimeout(() => toast.classList.add('show'), 50);

    // 3秒后移除
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

async function submitFeedback() {
    var emailInput = document.getElementById("email") as HTMLInputElement | null;
    if (!emailInput || !emailInput.checkValidity()) {
        showToast("请输入有效的邮箱地址。", "error");
        return;
    }

    var text = document.getElementById("feedback") as HTMLTextAreaElement | null;
    if (!text || text.value.trim() === "") {
        showToast("请填写反馈内容。", "error");
        return;
    }

    var feedbackButton = document.getElementById("feedbackButton") as HTMLButtonElement | null;
    if (feedbackButton) feedbackButton.disabled = true;

    try {
        const response = await fetch('/manage/feedback', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + (localStorage.getItem('api_key') || '')
            },
            body: JSON.stringify({
                email: emailInput.value,
                message: text.value
            })
        });

        if (response.ok) {
            showToast("发送成功！期待您的下次反馈！", "success");
            emailInput.value = "";
            if (text) text.value = "";
        } else {
            showToast("发送失败: " + response.status, "error");
        }
    } catch (error) {
        console.error("请求失败:", error);
        showToast("发送失败: " + (error instanceof Error ? error.message : String(error)), "error");
    } finally {
        if (feedbackButton) feedbackButton.disabled = false;
    }
}
