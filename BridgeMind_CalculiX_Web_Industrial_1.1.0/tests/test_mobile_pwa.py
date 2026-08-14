"""验证移动触控、PWA 清单和离线应用壳的静态交付。"""  # 说明测试文件用途。
from __future__ import annotations  # 启用延迟类型注解。
import json  # 提供 PWA 清单解析。
from pathlib import Path  # 提供资源路径处理。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。


def test_manifest_icons_and_service_worker_exist() -> None:  # 检查 PWA 安装资源完整。
    manifest = json.loads((ROOT / "web" / "manifest.webmanifest").read_text(encoding="utf-8"))  # 读取 PWA 清单。
    assert manifest["display"] == "standalone"  # 确认安装后以独立窗口运行。
    assert len(manifest["icons"]) == 2  # 确认提供两个标准图标尺寸。
    assert (ROOT / "web" / "icons" / "icon-192.png").is_file()  # 确认 192 像素图标存在。
    assert (ROOT / "web" / "icons" / "icon-512.png").is_file()  # 确认 512 像素图标存在。
    worker = (ROOT / "web" / "service-worker.js").read_text(encoding="utf-8")  # 读取离线缓存脚本。
    assert "APP_SHELL" in worker  # 确认应用壳资源列表存在。
    assert "url.pathname.startsWith(\"/api/\")" in worker  # 确认 API 不会被旧缓存伪装为实时结果。


def test_mobile_touch_contract_is_present() -> None:  # 检查触屏手势和响应式抽屉代码存在。
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")  # 读取前端交互脚本。
    styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")  # 读取响应式样式。
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")  # 读取网站页面。
    assert "gestureDistance" in script and "gestureMidpoint" in script  # 确认双指几何计算存在。
    assert "panCameraByScreen" in script  # 确认双指平移实现存在。
    assert "longPressTimer" in script  # 确认长按对象交互存在。
    assert "touch-action: none" in styles  # 确认浏览器不会抢占三维手势。
    assert "mobile-action-bar" in html  # 确认手机底部快捷操作栏存在。
    assert "manifest.webmanifest" in html  # 确认页面加载 PWA 清单。

def test_browser_api_key_session_contract_is_present() -> None:  # 检查生产访问密钥能够由手机和桌面网站安全附加。
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")  # 读取前端请求封装脚本。
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")  # 读取访问控制界面。
    assert 'sessionStorage.getItem("bridgemindApiKey")' in script  # 确认密钥只保存在当前浏览器会话。
    assert 'headers.set("X-API-Key", apiKey)' in script  # 确认受保护请求附加标准密钥请求头。
    assert 'id="apiKeyInput"' in html  # 确认触屏界面提供密钥输入控件。
    assert 'id="saveApiKeyButton"' in html  # 确认界面提供显式连接操作。

