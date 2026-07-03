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
        assert MattermostMsg.plugin_version == "1.0.2"
        assert MattermostMsg.plugin_config_prefix == "mattermostmsg_"
        assert MattermostMsg.auth_level == 1

    def test_form_structure_and_defaults(self):
        form, defaults = MattermostMsg().get_form()
        assert isinstance(form, list) and form[0]["component"] == "VForm"
        assert defaults == {
            "enabled": False,
            "onlyonce": False,
            "mm_host": "",
            "mm_bot_key": "",
            "mm_room": "",
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

    def test_form_fields_disable_browser_password_autofill(self):
        form, _ = MattermostMsg().get_form()

        def find_props_by_model(node, model):
            if isinstance(node, dict):
                props = node.get("props") or {}
                if props.get("model") == model:
                    return props
                for value in node.values():
                    found = find_props_by_model(value, model)
                    if found:
                        return found
            if isinstance(node, list):
                for item in node:
                    found = find_props_by_model(item, model)
                    if found:
                        return found
            return None

        old_models = {
            "server": find_props_by_model(form, "server"),
            "token": find_props_by_model(form, "token"),
            "channel": find_props_by_model(form, "channel"),
        }
        assert old_models == {"server": None, "token": None, "channel": None}

        server_props = find_props_by_model(form, "mm_host")
        token_props = find_props_by_model(form, "mm_bot_key")
        room_props = find_props_by_model(form, "mm_room")
        assert server_props["autocomplete"] == "off"
        assert server_props["data-bwignore"] == "true"
        assert token_props["type"] == "text"
        assert token_props["autocomplete"] == "off"
        assert token_props["data-bwignore"] == "true"
        assert room_props["autocomplete"] == "off"
        assert room_props["data-bwignore"] == "true"


class TestState:
    def test_state_true_when_configured(self, base_config):
        assert _make_plugin(base_config).get_state() is True

    def test_state_false_when_disabled_or_missing(self, base_config):
        for override in ({"enabled": False}, {"mm_host": ""},
                         {"mm_bot_key": ""}, {"mm_room": ""}):
            config = {**base_config, **override}
            assert _make_plugin(config).get_state() is False

    def test_server_trailing_slash_stripped(self, base_config):
        plugin = _make_plugin({**base_config, "mm_host": "https://mm.example.com/"})
        assert plugin._server == "https://mm.example.com"

    def test_legacy_config_keys_still_work(self):
        plugin = _make_plugin({
            "enabled": True,
            "onlyonce": False,
            "server": "https://mm.example.com/",
            "token": "legacy-token",
            "channel": "legacy-channel",
            "send_image": True,
            "msgtypes": [],
        })
        assert plugin.get_state() is True
        assert plugin._server == "https://mm.example.com"
        assert plugin._token == "legacy-token"
        assert plugin._channel == "legacy-channel"


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
        assert body["channel_id"] == base_config["mm_room"]
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
        plugin = _make_plugin({**base_config, "mm_room": ""})
        plugin._send_msg(title="t", text="x")
        assert [c for c in fake_http.calls if c["method"] == "post"] == []


class TestChannelResolution:
    def test_plain_channel_id_used_directly(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        assert plugin._channel_id == base_config["mm_room"]
        assert fake_http.calls == []   # 纯ID不发任何请求

    def test_team_slash_name_not_resolved_while_saving(self, base_config, fake_http):
        fake_http.queue.append(
            ("get", "/api/v4/teams/name/myteam/channels/name/moviepilot",
             fake_http.make_response(200, {"id": "resolved123"})))
        plugin = _make_plugin({**base_config, "mm_room": "myteam/moviepilot"})
        assert plugin._channel_id is None
        assert fake_http.calls == []

    def test_team_slash_name_resolved_lazily_when_sending(self, base_config, fake_http):
        fake_http.queue.append(
            ("get", "/api/v4/teams/name/myteam/channels/name/moviepilot",
             fake_http.make_response(200, {"id": "resolved123"})))
        plugin = _make_plugin({**base_config, "mm_room": "myteam/moviepilot"})
        plugin._send_msg(title="t", text="x")
        assert plugin._channel_id == "resolved123"
        assert [c["method"] for c in fake_http.calls] == ["get", "post"]

    def test_resolution_failure_sets_none(self, base_config, fake_http):
        fake_http.queue.append(
            ("get", "/api/v4/teams/name/",
             fake_http.make_response(404, text="not found")))
        plugin = _make_plugin({**base_config, "mm_room": "myteam/nochan"})
        plugin._send_msg(title="t", text="x")
        assert plugin._channel_id is None

    def test_no_resolution_when_config_incomplete(self, base_config, fake_http):
        plugin = _make_plugin({**base_config, "mm_bot_key": "",
                               "mm_room": "myteam/moviepilot"})
        assert plugin._channel_id is None
        assert fake_http.calls == []

    def test_resolution_exception_never_escapes_save(self, base_config, fake_http):
        fake_http.queue.append(
            ("get", "/api/v4/teams/name/myteam/channels/name/moviepilot",
             RuntimeError("network boom")))
        plugin = _make_plugin({**base_config, "mm_room": "myteam/moviepilot"})
        assert plugin._channel_id is None
        assert fake_http.calls == []


class TestOnlyOnce:
    def test_onlyonce_resets_and_schedules_background_test(
            self, base_config, fake_http, monkeypatch):
        scheduled = []
        monkeypatch.setattr(
            MattermostMsg,
            "_start_test_message_thread",
            lambda self: scheduled.append(self._onlyonce)
        )
        plugin = _make_plugin({**base_config, "onlyonce": True})
        assert scheduled == [False]
        assert fake_http.calls == []
        # onlyonce 已复位并持久化（规避 MeoW v1.0.1 修复过的坑）
        assert plugin._onlyonce is False
        assert plugin.updated_configs[-1]["onlyonce"] is False
        assert plugin.updated_configs[-1]["mm_host"] == base_config["mm_host"]
        assert plugin.updated_configs[-1]["mm_bot_key"] == base_config["mm_bot_key"]
        assert plugin.updated_configs[-1]["mm_room"] == base_config["mm_room"]

    def test_send_test_message_verifies_token_and_sends(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        plugin._send_test_message()
        urls = [c["url"] for c in fake_http.calls]
        assert "https://mm.example.com/api/v4/users/me" in urls
        posts = [c for c in fake_http.calls if c["method"] == "post"]
        assert len(posts) == 1
        att = posts[0]["json"]["props"]["attachments"][0]
        assert "测试" in att["title"]

    def test_no_test_message_when_token_invalid(self, base_config, fake_http):
        fake_http.queue.append(
            ("get", "/api/v4/users/me",
             fake_http.make_response(401, text="unauthorized")))
        plugin = _make_plugin(base_config)
        plugin._send_test_message()
        assert [c for c in fake_http.calls if c["method"] == "post"] == []

    def test_no_side_effects_without_onlyonce(self, base_config, fake_http):
        plugin = _make_plugin(base_config)
        assert plugin.updated_configs == []
        assert [c for c in fake_http.calls if c["method"] == "post"] == []

    def test_token_validation_exception_does_not_escape_save(self, base_config, fake_http):
        fake_http.queue.append(
            ("get", "/api/v4/users/me", RuntimeError("network boom")))
        plugin = _make_plugin(base_config)
        plugin._send_test_message()
        assert [c for c in fake_http.calls if c["method"] == "post"] == []
