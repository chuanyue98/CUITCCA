// ===== 问题反馈页面逻辑 (feed_back.html) =====
// 依赖: sidebar.js 已在上方加载

// Toast 工具函数
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
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
    var emailInput = document.getElementById("email");
    if (!emailInput.checkValidity()) {
        showToast("请输入有效的邮箱地址。", "error");
        return;
    }

    var text = document.getElementById("feedback").value;
    if (text.trim() === "") {
        showToast("请填写反馈内容。", "error");
        return;
    }

    var feedbackButton = document.getElementById("feedbackButton");
    feedbackButton.disabled = true;

    try {
        const response = await fetch('/manage/feedback', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + (localStorage.getItem('api_key') || '')
            },
            body: JSON.stringify({
                email: emailInput.value,
                message: text
            })
        });

        if (response.ok) {
            showToast("发送成功！期待您的下次反馈！", "success");
            document.getElementById("email").value = "";
            document.getElementById("feedback").value = "";
        } else {
            showToast("发送失败: " + response.status, "error");
        }
    } catch (error) {
        console.error("请求失败:", error);
        showToast("发送失败: " + error.message, "error");
    } finally {
        feedbackButton.disabled = false;
    }
}
