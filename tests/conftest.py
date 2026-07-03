"""为插件单测注入 MoviePilot 运行时的轻量替身。

插件源码 import 的 5 个 app.* 模块在此全部 stub。枚举取值逐字复制自
jxxghp/MoviePilot@v2.14.0，若未来核心枚举变化，仅影响测试不影响插件运行
（插件对枚举的使用均为动态遍历 / dict.get 带默认值）。
必须在任何测试模块 import 插件之前完成注入，故放在 conftest 顶层执行。
"""
import enum
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _install_moviepilot_stubs():
    if "app" in sys.modules:
        return

    app_mod = types.ModuleType("app")
    app_mod.__path__ = []

    # ---- app.schemas.types ----
    schemas_mod = types.ModuleType("app.schemas")
    schemas_mod.__path__ = []
    types_mod = types.ModuleType("app.schemas.types")

    class EventType(enum.Enum):
        NoticeMessage = "notice.message"

    class NotificationType(enum.Enum):
        Download = "资源下载"
        Organize = "整理入库"
        Subscribe = "订阅"
        SiteMessage = "站点"
        MediaServer = "媒体服务器"
        Manual = "手动处理"
        Plugin = "插件"
        Agent = "智能体"
        Other = "其它"

    class MessageChannel(enum.Enum):
        Telegram = "Telegram"
        Web = "Web"

    types_mod.EventType = EventType
    types_mod.NotificationType = NotificationType
    types_mod.MessageChannel = MessageChannel

    # ---- app.core.event ----
    core_mod = types.ModuleType("app.core")
    core_mod.__path__ = []
    event_mod = types.ModuleType("app.core.event")

    class Event:
        def __init__(self, etype=None, data=None):
            self.event_type = etype
            self.event_data = data or {}

    class _EventManager:
        @staticmethod
        def register(etype, **kwargs):
            def decorator(func):
                return func
            return decorator

        def send_event(self, *args, **kwargs):
            pass

    event_mod.Event = Event
    event_mod.eventmanager = _EventManager()

    # ---- app.log ----
    log_mod = types.ModuleType("app.log")

    class _Logger:
        def __getattr__(self, name):
            def _log(*args, **kwargs):
                pass
            return _log

    log_mod.logger = _Logger()

    # ---- app.plugins ----
    plugins_mod = types.ModuleType("app.plugins")
    plugins_mod.__path__ = []

    class _PluginBase:
        def __init__(self):
            self.updated_configs = []

        def update_config(self, config, plugin_id=None):
            self.updated_configs.append(config)
            return True

    plugins_mod._PluginBase = _PluginBase

    # ---- app.utils.http ----
    utils_mod = types.ModuleType("app.utils")
    utils_mod.__path__ = []
    http_mod = types.ModuleType("app.utils.http")

    class RequestUtils:
        """占位实现；单测中会被 monkeypatch 为 FakeRequestUtils。"""

        def __init__(self, **kwargs):
            self.init_kwargs = kwargs

        def get_res(self, url, **kwargs):
            raise AssertionError("测试中不允许发出真实网络请求")

        def post_res(self, url, **kwargs):
            raise AssertionError("测试中不允许发出真实网络请求")

    http_mod.RequestUtils = RequestUtils

    sys.modules.update({
        "app": app_mod,
        "app.schemas": schemas_mod,
        "app.schemas.types": types_mod,
        "app.core": core_mod,
        "app.core.event": event_mod,
        "app.log": log_mod,
        "app.plugins": plugins_mod,
        "app.utils": utils_mod,
        "app.utils.http": http_mod,
    })


_install_moviepilot_stubs()

# 让 `import mattermostmsg` 生效（plugins.v2 目录名含点号，不能作包名，直接入 sys.path）
sys.path.insert(0, str(_ROOT / "plugins.v2"))


# ---------------- 测试辅助件 ----------------

class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


class FakeRequestUtils:
    """记录全部 HTTP 调用；按 (method, url子串) 队列匹配返回预设响应，命中即出队。

    未命中队列时：get 默认 200 空 json，post 默认 201 空 json。
    """
    calls = []   # 每项：{"method","url","json","headers"}
    queue = []   # 每项：(method, url_substring, FakeResponse)

    def __init__(self, **kwargs):
        self._headers = (kwargs or {}).get("headers") or {}

    def _do(self, method, url, **kwargs):
        FakeRequestUtils.calls.append({
            "method": method,
            "url": url,
            "json": kwargs.get("json"),
            "headers": self._headers,
        })
        for i, (m, sub, resp) in enumerate(FakeRequestUtils.queue):
            if m == method and sub in url:
                FakeRequestUtils.queue.pop(i)
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return FakeResponse(201 if method == "post" else 200)

    def get_res(self, url, **kwargs):
        return self._do("get", url, **kwargs)

    def post_res(self, url, **kwargs):
        return self._do("post", url, **kwargs)

    @classmethod
    def reset(cls):
        cls.calls = []
        cls.queue = []

    @classmethod
    def make_response(cls, status_code=200, json_data=None, text=""):
        """测试用响应构造入口（避免测试文件直接 import conftest）"""
        return FakeResponse(status_code, json_data, text)


@pytest.fixture()
def fake_http(monkeypatch):
    """把插件模块内的 RequestUtils 替换为 FakeRequestUtils 并在用例间重置。"""
    import mattermostmsg
    FakeRequestUtils.reset()
    monkeypatch.setattr(mattermostmsg, "RequestUtils", FakeRequestUtils)
    yield FakeRequestUtils
    FakeRequestUtils.reset()


BASE_CONFIG = {
    "enabled": True,
    "onlyonce": False,
    "server": "https://mm.example.com",
    "token": "test-token",
    "channel": "abcdefghijklmnopqrstuvwxyz",
    "send_image": True,
    "msgtypes": [],
}


@pytest.fixture()
def base_config():
    return dict(BASE_CONFIG)
