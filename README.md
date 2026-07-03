# MoviePilot-MatterMost-Notification

MoviePilot 第三方插件库。

## 安装本插件库

MoviePilot → 设定 → 插件 → 插件市场地址中追加本仓库地址：

```
https://github.com/kyalpha313/MoviePilot-MatterMost-Notification
```

保存后到「插件市场」搜索安装。

## 插件列表

### Mattermost消息通知 (v1.0.3)

通过 Mattermost Bot 将 MoviePilot 的各类通知（下载、入库、订阅、站点等）推送到指定或全部频道，
富附件渲染（按消息类型着色 + 标题链接 + 海报图），发送失败自动降级纯文本。

**前置准备（Mattermost 侧）：**

1. 系统控制台或 集成 → Bot账户 → 创建 Bot，复制**访问令牌**（只显示一次）。
2. 团队菜单 → 邀请成员，把 Bot 邀请进团队。
3. 在目标频道中添加 Bot 为频道成员。
4. 获取频道 ID：频道名下拉 → 查看信息 → 复制频道 ID（26 位）。

**插件配置：**

| 配置项 | 说明 |
|---|---|
| 服务器地址 | Mattermost 地址，如 `https://mm.example.com` |
| Bot访问密钥 | 上面第 1 步复制的 Access Token（表单中隐藏显示） |
| 频道 | 留空 = 发送到 Bot 已加入的所有公开/私有团队频道；也可填频道 ID（推荐）或 `团队名/频道名`（URL 中的名称） |
| 附带海报图片 | 通知本身带有媒体海报 URL 时附带；测试消息使用插件图标演示图片效果 |
| 消息类型 | 勾选要转发的类型；**不选 = 全部发送** |

配置完成后打开「测试插件」开关并保存，Bot 应在频道中发出一条测试消息。
