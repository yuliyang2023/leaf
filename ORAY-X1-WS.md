# OrayBox X1：VMess + WebSocket UPX

使用 `leaf-oray` 的可选 `websocket` 功能增加 `outbound-ws` 和 `outbound-chain`，原有 TCP 构建保持不变。不包含 TLS，因此只支持 VMess over WS，不支持 WSS。

目标为 MIPS 小端、软浮点、O32、MIPS32r2；musl 和 OpenSSL 静态链接。原始版与 UPX 版都必须通过 QEMU 24KEc 配置检查、SOCKS5 握手、实际 WebSocket 路径/Host 升级和承载 VMess 的二进制帧测试。该测试不替代真实服务器 VMess 认证和上网测试。

## 构建

GitHub：Actions → **Build Oray X1 VMess WebSocket UPX** → **Run workflow**。构建脚本为 `scripts/build-oray-vmess-ws.sh`，构建结束后下载 `leaf-oray-x1-vmess-ws` artifact。

产物目录包含 `leaf-oray-vmess-ws`、可直接执行的 `leaf-oray-vmess-ws-upx`、仅用于下载的 gzip、`SHA256SUMS`、`SIZES.md`、构建信息和配置示例。实际大小以成功构建产物的 `SIZES.md` 为准；UPX 打包或测试失败时构建失败，不提供未验证的 UPX 成功结果。

## 转换 Clash 节点

以 `leaf-oray/leaf.vmess-ws.example.json` 为模板：

| Clash 字段 | Leaf 字段 |
| --- | --- |
| server | vmess.settings.address，使用真实服务器 IP |
| port | vmess.settings.port |
| uuid | vmess.settings.uuid |
| alterId: 0 | 此构建使用 VMess AEAD，不填写 alterId |
| cipher: auto | 显式选择 chacha20-ietf-poly1305 或 aes-128-gcm |
| network: ws | 使用 chain，actors 顺序为 websocket、vmess |
| ws-opts.path / ws-path | websocket.settings.path |
| ws-opts.headers.Host / ws-headers.Host | websocket.settings.headers.Host |

`proxy` chain 必须放在 outbounds 的第一项，作为默认出口。重复的新旧 WS 字段只保留一份。`name` 是显示名称，不影响协议。`udp: true` 只是客户端选项，不证明服务器实际能中继 UDP。

现有 HEV 映射 DNS 会把上游域名解析成 TUN 中的合成 IP，应预先解析真实服务器 IP 填入 VMess address，同时保留原 WS Host 域名，避免循环代理。

## 部署

验证成功、填写真实节点后才替换设备上的旧二进制。安装此版本本身不改变 HEV 配置或接管客户端流量。

```sh
chmod 700 /root/leaf-oray-vmess-ws-upx
/root/leaf-oray-vmess-ws-upx -c /root/leaf.json -T
```

如使用当前 `/etc/init.d/leaf` 服务，需把服务脚本的 BIN 改成新版本路径，再启动 Leaf。本地 SOCKS5 默认为 127.0.0.1:1080；确认真实节点可用后，再切换 HEV 的本地 SOCKS5 后端并移除原用户名、密码。
