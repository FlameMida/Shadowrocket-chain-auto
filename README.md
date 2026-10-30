# Shadowrocket 原版同源规则包

发布仓库：[FlameMida/Shadowrocket-chain-auto](https://github.com/FlameMida/Shadowrocket-chain-auto)。

小火箭配置导入地址：

```text
https://raw.githubusercontent.com/FlameMida/Shadowrocket-chain-auto/main/Shadowrocket-chain-auto.conf
```

`Shadowrocket-snapshot.conf` 已内置本次下载的规则，可以离线导入；`Shadowrocket-chain-auto.conf` 引用本仓库的远程规则。下载目录中的旧配置保留；本目录内为同源规则版。

## 文件

- `Shadowrocket-snapshot.conf`：静态快照，无远程规则下载，不会自动更新。
- `Shadowrocket-chain-auto.conf`：托管版，引用此仓库 `rules/` 中的转换结果；发布前地址不可用。
- `Shadowrocket-chain-auto.conf.template`：配置模板，修改分组或规则顺序时编辑它。
- `scripts/update_rules.py`：仅使用 Python 标准库，下载、转换并验证规则。
- `rules/*.list`：转换后的 Shadowrocket RULE-SET 文本。
- `manifest.json`：逐个记录上游 URL 和规则数量。
- `last-success.txt`：生成时间（UTC）；工作流仅在规则或配置发生变化时提交，因此远端此时间代表最近一次产物变化，不代表最近一次定时检查。
- `.github/workflows/update-rules.yml`：每小时第 23 分钟拉取并转换上游规则，仅在产物变化时提交，也可手动触发。GitHub 调度可能延迟；手机端仍按 App 设置和 iOS 后台调度刷新，不保证每小时同步。

## 来源与转换

规则主要来自 `https://github.com/appshubcc/bett-rules/tree/meta/geo`，Anthropic 保持原脚本的 Sor85/claude-ruleset 来源。

- 裸域名转为 `DOMAIN`，`+.example.com` 转为 `DOMAIN-SUFFIX`。
- IPv4/IPv6 网段分别转为 `IP-CIDR`/`IP-CIDR6`，保留 `no-resolve`。
- Anthropic classical 文本经类型验证后保留。
- 规则集中的每条规则不附加策略名称，由配置中的 RULE-SET 指定策略。
- 不支持的格式、空规则集或任一下载失败会导致命令失败，不把失败内容发布为空规则。
- `gfw`/`cn` 采用同仓库文本适配；它们不保证与用户原 Mihomo 内核内置数据库版本一致。
- 上游独立文件依次下载，不保证它们属于同一 Git 提交；不保证 `.list` 与同次 `.mrs` 的二进制内容逐条一致。
- 各上游版权和使用条款仍适用；本包保留来源，不额外授予上游数据的再分发许可。

## 现有设置

默认代理跟随首页当前节点；八个服务组按 Clash 的选择方式，在同一组内直接选择普通节点或“链式落地”，各服务独立记录选择，不增加“服务名节点”子组。Microsoft、Apple、Spotify 保留直连选项。分组采用 `use=true` 组合固定选项与正则节点列表，筛选表达式保留链式落地和直连名称。该写法参考 [Repcz 的 Shadowrocket 配置](https://github.com/Repcz/Tool/blob/X/Shadowrocket/Shadowrocket.conf)，尚需 App 实机确认。移除 FCM、自动测速选节点和负载均衡。21 条原版静态域名规则保留，五条 GitHub 域名按用户要求走 GitHub 组。

修复分组后需要从原地址重新导入配置；后台更新只刷新规则集，不会替换本地分组。请先在首页添加备注严格为 `自建-美国-TCP` 的 SOCKS5 节点，链式落地组才能引用该节点。链式落地初始选中 REJECT，需要手动改为实际落地节点。

原版 private、geolocation-cn、Epic 前置规则及国外域名优先于最终 GEOIP,CN 的顺序已补回。服务优先顺序沿用当前适配版：Anthropic → AI → Google → GitHub → Microsoft → Apple → Telegram → Spotify → AdBlock，以保证细分服务选择优先。

## 本地生成

需要 Python 3.9 或以上版本：

```sh
python3 scripts/update_rules.py --repository OWNER/REPO --branch main
```

`OWNER/REPO` 必须替换为实际托管仓库。默认发布仓库为 `FlameMida/Shadowrocket-chain-auto`。仓库应能被小火箭匿名访问，通常使用公开仓库；不要将私人订阅 URL、节点密码或组网登录密钥写入其中。

## 发布后使用

1. 将本目录内容（包括 `.github`）上传到确认的 GitHub 仓库 `main` 分支，启用 Actions，并允许工作流读写仓库内容。
2. 手动运行 `Update same-source rules`，确认成功，并检查远程 `Shadowrocket-chain-auto.conf` 和 `rules/*.list` 可以下载。推送触发条件只覆盖模板、脚本和工作流，首次发布后建议手动执行一次。
3. 在小火箭导入仓库的 `Shadowrocket-chain-auto.conf` 原始文件地址；先准备可用的节点或订阅，并使用“配置”路由模式。
4. 设置 → 配置 → 自动后台更新，建议 1 天；允许 iOS 后台 App 刷新。iOS 和 GitHub 均不保证任务准点运行；GitHub 可能暂停长期无活动公开仓库的定时任务。
5. 本配置没有 `update-url`，后台刷新规则集不会覆盖本地分组。修改模板后若要更新分组，需要重新导入配置。

## 链式代理

在小火箭添加真实 SOCKS5 节点，备注为 `自建-美国-TCP`，在该节点的“代理通过”中选择具体机场节点。方向为“手机 → 机场中转 → SOCKS5 落地 → 网站”。链式中转组仅供参考，不会自动绑定“代理通过”。链式落地默认 REJECT，完成设置后再选实际节点。缺失已绑定的代理链时拒绝连接。

## 兼容差异与验证范围

- UDP 闸门保留手工私网范围加 App GEOIP,CN，其余 UDP 拒绝；并未将原版 private_ip/cn_ip 集嵌入逻辑规则。服务与最终私网 IP 分流使用同源转换结果。
- DNS 使用国外 DoH 经默认代理、直连请求使用国内 DNS，代理服务器域名通过国内 DNS 引导。并非原版 Mihomo DNS policy/fake-ip 的完整等价实现；没有强制禁止 App 的 DNS 回退。
- 保留三个公共 DNS 主机的一条固定 IP。原版多 IP 轮换、`services.googleapis.cn` 域名别名尚未移植；PCDN 用规则拒绝替代 hosts 归零。
- 节点自动清洗、补国旗、重命名及五种直连 IP 偏好没有移植。
- 原生组网功能默认关闭。使用时先在支持该功能的小火箭版本登录，按配置注释添加真实设备 IP，并置于 UDP 闸门前。
- 静态快照包含约十多万条规则，比之前离线精简版大，首次导入可能耗时；按需优先使用发布后的远程规则版。
- 已进行上游下载、转换和本地结构校验；尚未在 Shadowrocket App 实机验证，自动更新任务状态可在仓库 Actions 页面检查。
