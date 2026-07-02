from typing import Any, Dict, List, Optional, Tuple

from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils


class MattermostMsg(_PluginBase):
    # 插件名称
    plugin_name = "Mattermost消息通知"
    # 插件描述
    plugin_desc = "通过 Mattermost Bot 将 MoviePilot 通知推送到指定频道。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/kyalpha313/MoviePilot-Plugins/main/icons/Mattermost_A.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "kyalpha313"
    # 作者主页
    author_url = "https://github.com/kyalpha313"
    # 插件配置项ID前缀
    plugin_config_prefix = "mattermostmsg_"
    # 加载顺序
    plugin_order = 27
    # 可使用的用户级别
    auth_level = 1

    # 附件正文最大长度（Mattermost 客户端自动折叠长文本，此处保守截断）
    _MAX_TEXT_LENGTH = 4000
    # 消息类型 -> 附件左侧色条颜色
    _COLOR_MAP = {
        "Download": "#2196F3",
        "Organize": "#4CAF50",
        "Subscribe": "#9C27B0",
        "SiteMessage": "#FF9800",
        "MediaServer": "#00BCD4",
        "Manual": "#F44336",
        "Plugin": "#607D8B",
        "Agent": "#009688",
        "Other": "#9E9E9E",
    }
    _DEFAULT_COLOR = "#607D8B"

    # 私有属性
    _enabled = False
    _onlyonce = False
    _server = None
    _token = None
    _channel = None
    _channel_id = None
    _send_image = True
    _msgtypes = []

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._server = (config.get("server") or "").strip().rstrip("/")
            self._token = (config.get("token") or "").strip()
            self._channel = (config.get("channel") or "").strip()
            self._send_image = config.get("send_image", True)
            self._msgtypes = config.get("msgtypes") or []

        # 解析频道ID（支持 26位ID 或 团队名/频道名 两种格式）
        if self._server and self._token and self._channel:
            self._channel_id = self._resolve_channel_id()
        else:
            self._channel_id = None

    def get_state(self) -> bool:
        return bool(self._enabled and self._server and self._token and self._channel)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        # 遍历 NotificationType 枚举，生成消息类型选项
        MsgTypeOptions = []
        for item in NotificationType:
            MsgTypeOptions.append({
                "title": item.value,
                "value": item.name
            })
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 6
                                },
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 6
                                },
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "测试插件（发送一条测试消息）",
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 6
                                },
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "server",
                                            "label": "服务器地址",
                                            "placeholder": "https://mm.example.com",
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 6
                                },
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "token",
                                            "label": "Bot访问令牌",
                                            "type": "password",
                                            "placeholder": "Bot Access Token",
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 6
                                },
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "channel",
                                            "label": "频道",
                                            "placeholder": "频道ID 或 团队名/频道名",
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 6
                                },
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "send_image",
                                            "label": "附带海报图片",
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12
                                },
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "multiple": True,
                                            "chips": True,
                                            "model": "msgtypes",
                                            "label": "消息类型",
                                            "items": MsgTypeOptions
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12
                                },
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "使用前请先在 Mattermost 中创建 Bot 并复制访问令牌，"
                                                    "将 Bot 邀请进团队并加入目标频道。"
                                                    "频道支持两种填法：频道ID（频道信息页可复制，推荐）"
                                                    "或 团队名/频道名（URL中的名称，如 myteam/town-square）。"
                                                    "消息类型不选表示全部发送。"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "server": "",
            "token": "",
            "channel": "",
            "send_image": True,
            "msgtypes": [],
        }

    def get_page(self) -> List[dict]:
        pass

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _resolve_channel_id(self) -> Optional[str]:
        """
        频道配置含 "/" 时按 团队名/频道名 调用API解析，否则原样作为频道ID
        """
        if "/" not in self._channel:
            return self._channel
        team_name, channel_name = self._channel.split("/", 1)
        url = (f"{self._server}/api/v4/teams/name/{team_name.strip()}"
               f"/channels/name/{channel_name.strip()}")
        res = RequestUtils(headers=self._headers()).get_res(url)
        if res is not None and res.status_code == 200:
            channel_id = res.json().get("id")
            logger.info(f"Mattermost 频道 {self._channel} 解析成功：{channel_id}")
            return channel_id
        status = res.status_code if res is not None else "无响应"
        logger.error(f"Mattermost 频道 {self._channel} 解析失败（{status}），"
                     f"请检查团队名/频道名是否正确、Bot是否已加入该团队")
        return None

    def _send_msg(self, title: str, text: str = None, image: str = None,
                  link: str = None, mtype_name: str = None):
        """
        发送消息到 Mattermost：优先富附件，失败降级纯文本重试一次
        """
        try:
            if not self._server or not self._token:
                logger.warn("Mattermost 参数未配置，无法发送消息")
                return
            if not self._channel_id:
                logger.warn("Mattermost 频道ID无效，无法发送消息（请检查频道配置）")
                return
            title = title or ""
            text = text or ""
            if len(text) > self._MAX_TEXT_LENGTH:
                text = text[:self._MAX_TEXT_LENGTH] + "\n……（内容过长已截断）"
            # 富附件
            attachment = {
                "fallback": title or text,
                "color": self._COLOR_MAP.get(mtype_name, self._DEFAULT_COLOR),
                "title": title,
                "text": text,
            }
            if link and str(link).startswith("http"):
                attachment["title_link"] = link
            if self._send_image and image and str(image).startswith("http"):
                attachment["image_url"] = image
            payload = {
                "channel_id": self._channel_id,
                "message": "",
                "props": {"attachments": [attachment]},
            }
            res = RequestUtils(headers=self._headers()).post_res(
                f"{self._server}/api/v4/posts", json=payload)
            if res is not None and res.status_code == 201:
                logger.info(f"Mattermost 消息发送成功：{title}")
                return
            status = res.status_code if res is not None else "无响应"
            body = res.text[:200] if res is not None else ""
            logger.warn(f"Mattermost 附件消息发送失败（{status} {body}），"
                        f"尝试降级为纯文本发送")
            # 降级：纯 Markdown 文本
            lines = []
            if title:
                lines.append(f"**{title}**")
            if text:
                lines.append(text)
            if link and str(link).startswith("http"):
                lines.append(f"[查看详情]({link})")
            if self._send_image and image and str(image).startswith("http"):
                lines.append(f"![image]({image})")
            fallback_payload = {
                "channel_id": self._channel_id,
                "message": "\n\n".join(lines),
            }
            res = RequestUtils(headers=self._headers()).post_res(
                f"{self._server}/api/v4/posts", json=fallback_payload)
            if res is not None and res.status_code == 201:
                logger.info(f"Mattermost 纯文本消息发送成功：{title}")
            elif res is not None:
                logger.warn(f"Mattermost 消息发送失败，错误码：{res.status_code}，"
                            f"响应：{res.text[:200]}")
            else:
                logger.warn("Mattermost 消息发送失败：未获取到返回信息")
        except Exception as e:
            logger.error(f"Mattermost 消息发送异常：{str(e)}")

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event):
        """
        消息发送事件
        """
        if not self.get_state():
            return
        if not event.event_data:
            return
        msg_body = event.event_data
        # 渠道：定向到内置渠道的消息不重复转发
        channel = msg_body.get("channel")
        if channel:
            return
        # 类型
        msg_type: NotificationType = msg_body.get("type")
        # 标题、正文、图片、链接
        title = msg_body.get("title")
        text = msg_body.get("text")
        image = msg_body.get("image")
        link = msg_body.get("link")
        if not title and not text:
            logger.warn("标题和内容不能同时为空")
            return
        if (msg_type and self._msgtypes
                and msg_type.name not in self._msgtypes):
            logger.info(f"消息类型 {msg_type.value} 未开启消息发送")
            return
        self._send_msg(title=title, text=text, image=image, link=link,
                       mtype_name=msg_type.name if msg_type else None)

    def stop_service(self):
        """
        退出插件
        """
        pass
