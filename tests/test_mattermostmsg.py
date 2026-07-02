from app.core.event import Event
from app.schemas.types import EventType, MessageChannel, NotificationType

from mattermostmsg import MattermostMsg


def _make_plugin(config):
    plugin = MattermostMsg()
    plugin.init_plugin(config)
    return plugin


class TestMetadataAndForm:
    def test_metadata(self):
        assert MattermostMsg.plugin_name == "Mattermost消息通知"
        assert MattermostMsg.plugin_version == "1.0.0"
        assert MattermostMsg.plugin_config_prefix == "mattermostmsg_"
        assert MattermostMsg.auth_level == 1

    def test_form_structure_and_defaults(self):
        form, defaults = MattermostMsg().get_form()
        assert isinstance(form, list) and form[0]["component"] == "VForm"
        assert defaults == {
            "enabled": False,
            "onlyonce": False,
            "server": "",
            "token": "",
            "channel": "",
            "send_image": True,
            "msgtypes": [],
        }

    def test_form_msgtypes_options_cover_all_enum(self):
        form, _ = MattermostMsg().get_form()

        # 在整个表单 JSON 中收集 VSelect 的 items
        def find_select_items(node):
            if isinstance(node, dict):
                if node.get("component") == "VSelect":
                    return node["props"]["items"]
                for v in node.values():
                    found = find_select_items(v)
                    if found:
                        return found
            if isinstance(node, list):
                for item in node:
                    found = find_select_items(item)
                    if found:
                        return found
            return None

        items = find_select_items(form)
        assert items is not None
        assert {i["value"] for i in items} == {t.name for t in NotificationType}


class TestState:
    def test_state_true_when_configured(self, base_config):
        assert _make_plugin(base_config).get_state() is True

    def test_state_false_when_disabled_or_missing(self, base_config):
        for override in ({"enabled": False}, {"server": ""},
                         {"token": ""}, {"channel": ""}):
            config = {**base_config, **override}
            assert _make_plugin(config).get_state() is False

    def test_server_trailing_slash_stripped(self, base_config):
        plugin = _make_plugin({**base_config, "server": "https://mm.example.com/"})
        assert plugin._server == "https://mm.example.com"


class TestSendFilters:
    @staticmethod
    def _capture(plugin, monkeypatch):
        sent = []
        monkeypatch.setattr(plugin, "_send_msg",
                            lambda **kwargs: sent.append(kwargs))
        return sent

    def test_forwards_broadcast_message(self, base_config, monkeypatch):
        plugin = _make_plugin(base_config)
        sent = self._capture(plugin, monkeypatch)
        plugin.send(Event(EventType.NoticeMessage, {
            "channel": None,
            "type": NotificationType.Download,
            "title": "开始下载",
            "text": "沙丘2 已推送下载器",
            "image": "https://image.tmdb.org/t/p/poster.jpg",
            "link": "https://mp.example.com/#/downloading",
        }))
        assert sent == [{
            "title": "开始下载",
            "text": "沙丘2 已推送下载器",
            "image": "https://image.tmdb.org/t/p/poster.jpg",
            "link": "https://mp.example.com/#/downloading",
            "mtype_name": "Download",
        }]

    def test_skips_when_disabled(self, base_config, monkeypatch):
        plugin = _make_plugin({**base_config, "enabled": False})
        sent = self._capture(plugin, monkeypatch)
        plugin.send(Event(EventType.NoticeMessage,
                          {"channel": None, "title": "t", "text": "x"}))
        assert sent == []

    def test_skips_empty_event_data(self, base_config, monkeypatch):
        plugin = _make_plugin(base_config)
        sent = self._capture(plugin, monkeypatch)
        plugin.send(Event(EventType.NoticeMessage, None))
        assert sent == []

    def test_skips_channel_directed_message(self, base_config, monkeypatch):
        plugin = _make_plugin(base_config)
        sent = self._capture(plugin, monkeypatch)
        plugin.send(Event(EventType.NoticeMessage, {
            "channel": MessageChannel.Telegram,
            "title": "定向消息", "text": "不应转发",
        }))
        assert sent == []

    def test_skips_when_title_and_text_empty(self, base_config, monkeypatch):
        plugin = _make_plugin(base_config)
        sent = self._capture(plugin, monkeypatch)
        plugin.send(Event(EventType.NoticeMessage,
                          {"channel": None, "title": None, "text": ""}))
        assert sent == []

    def test_msgtypes_filter(self, base_config, monkeypatch):
        plugin = _make_plugin({**base_config, "msgtypes": ["Subscribe"]})
        sent = self._capture(plugin, monkeypatch)
        plugin.send(Event(EventType.NoticeMessage, {
            "channel": None, "type": NotificationType.Download,
            "title": "开始下载", "text": "x",
        }))
        assert sent == []
        plugin.send(Event(EventType.NoticeMessage, {
            "channel": None, "type": NotificationType.Subscribe,
            "title": "新增订阅", "text": "x",
        }))
        assert len(sent) == 1 and sent[0]["mtype_name"] == "Subscribe"

    def test_empty_msgtypes_means_all(self, base_config, monkeypatch):
        plugin = _make_plugin({**base_config, "msgtypes": []})
        sent = self._capture(plugin, monkeypatch)
        plugin.send(Event(EventType.NoticeMessage, {
            "channel": None, "type": NotificationType.Other,
            "title": "任意消息", "text": "x",
        }))
        assert len(sent) == 1

    def test_message_without_type_is_forwarded(self, base_config, monkeypatch):
        plugin = _make_plugin({**base_config, "msgtypes": ["Subscribe"]})
        sent = self._capture(plugin, monkeypatch)
        plugin.send(Event(EventType.NoticeMessage, {
            "channel": None, "type": None, "title": "无类型消息", "text": "x",
        }))
        assert len(sent) == 1 and sent[0]["mtype_name"] is None
