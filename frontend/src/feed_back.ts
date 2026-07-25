// ===== 问题反馈页面的逻辑 (feed_back.html) =====
// 依赖: sidebar.ts 已在上方加载

import { apiFetch } from "./utils/api";
import { showToast } from "./utils/toast";

async function submitFeedback() {
    const emailInput = document.getElementById("email") as HTMLInputElement | null;
    if (!emailInput || !emailInput.checkValidity()) {
        showToast("请输入有效的邮箱地址。", "error");
        return;
    }

    const text = document.getElementById("feedback") as HTMLTextAreaElement | null;
    if (!text || text.value.trim() === "") {
        showToast("请填写反馈内容。", "error");
        return;
    }

    const feedbackButton = document.getElementById("feedbackButton") as HTMLButtonElement | null;
    if (feedbackButton) feedbackButton.disabled = true;

    try {
        const response = await apiFetch("/manage/feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
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

document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("feedbackButton");
    if (btn) {
        btn.addEventListener("click", submitFeedback);
    }
});
