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
