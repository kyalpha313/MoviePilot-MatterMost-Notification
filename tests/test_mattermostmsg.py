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


class TestSendToMattermost:
    def test_sends_attachment_post(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        plugin._send_msg(title="开始下载", text="沙丘2",
                         image="https://img.example.com/p.jpg",
                         link="https://mp.example.com/#/d",
                         mtype_name="Download")
        posts = [c for c in fake_http.calls if c["method"] == "post"]
        assert len(posts) == 1
        call = posts[0]
        assert call["url"] == "https://mm.example.com/api/v4/posts"
        assert call["headers"]["Authorization"] == "Bearer test-token"
        assert call["headers"]["Content-Type"] == "application/json"
        body = call["json"]
        assert body["channel_id"] == base_config["channel"]
        assert body["message"] == ""
        att = body["props"]["attachments"][0]
        assert att["title"] == "开始下载"
        assert att["text"] == "沙丘2"
        assert att["fallback"] == "开始下载"
        assert att["color"] == "#2196F3"
        assert att["title_link"] == "https://mp.example.com/#/d"
        assert att["image_url"] == "https://img.example.com/p.jpg"

    def test_unknown_mtype_uses_default_color(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        plugin._send_msg(title="t", text="x", mtype_name="FutureType")
        att = fake_http.calls[-1]["json"]["props"]["attachments"][0]
        assert att["color"] == "#607D8B"

    def test_image_toggle_off(self, base_config, fake_http):
        plugin = _make_plugin({**base_config, "send_image": False})
        plugin._send_msg(title="t", text="x",
                         image="https://img.example.com/p.jpg")
        att = fake_http.calls[-1]["json"]["props"]["attachments"][0]
        assert "image_url" not in att

    def test_non_http_link_and_image_ignored(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        plugin._send_msg(title="t", text="x", image="/local/path.jpg",
                         link="ftp://x")
        att = fake_http.calls[-1]["json"]["props"]["attachments"][0]
        assert "image_url" not in att and "title_link" not in att

    def test_long_text_truncated(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        plugin._send_msg(title="t", text="x" * 5000)
        att = fake_http.calls[-1]["json"]["props"]["attachments"][0]
        assert len(att["text"]) < 4100
        assert att["text"].endswith("（内容过长已截断）")

    def test_degrades_to_plain_text_on_failure(self, base_config, fake_http):
        fake_http.queue.append(
            ("post", "/api/v4/posts",
             fake_http.make_response(400, text="invalid props")))
        plugin = _make_plugin(base_config)
        plugin._send_msg(title="开始下载", text="沙丘2",
                         link="https://mp.example.com/#/d",
                         mtype_name="Download")
        posts = [c for c in fake_http.calls if c["method"] == "post"]
        assert len(posts) == 2
        retry = posts[1]["json"]
        assert "props" not in retry
        assert "**开始下载**" in retry["message"]
        assert "沙丘2" in retry["message"]
        assert "https://mp.example.com/#/d" in retry["message"]

    def test_skips_when_channel_id_missing(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        plugin._channel_id = None
        plugin._send_msg(title="t", text="x")
        assert [c for c in fake_http.calls if c["method"] == "post"] == []


class TestChannelResolution:
    def test_plain_channel_id_used_directly(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        assert plugin._channel_id == base_config["channel"]
        assert fake_http.calls == []   # 纯ID不发任何请求

    def test_team_slash_name_resolved_via_api(self, base_config, fake_http):
        fake_http.queue.append(
            ("get", "/api/v4/teams/name/myteam/channels/name/moviepilot",
             fake_http.make_response(200, {"id": "resolved123"})))
        plugin = _make_plugin({**base_config, "channel": "myteam/moviepilot"})
        assert plugin._channel_id == "resolved123"

    def test_resolution_failure_sets_none(self, base_config, fake_http):
        fake_http.queue.append(
            ("get", "/api/v4/teams/name/",
             fake_http.make_response(404, text="not found")))
        plugin = _make_plugin({**base_config, "channel": "myteam/nochan"})
        assert plugin._channel_id is None

    def test_no_resolution_when_config_incomplete(self, base_config, fake_http):
        plugin = _make_plugin({**base_config, "token": "",
                               "channel": "myteam/moviepilot"})
        assert plugin._channel_id is None
        assert fake_http.calls == []
