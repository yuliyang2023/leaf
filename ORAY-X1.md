# Leaf：OrayBox X1 的 VMess 精简构建

Actions → **Build Oray X1 VMess** → **Run workflow**，选择 `master`。
此工作流只手动触发，构建目标为 MIPS 小端、软浮点、O32 ABI、MIPS32r2。
使用 Rust nightly-2026-10-04 自行编译 Tier 3 目标标准库，配合静态 musl C 工具链。

新增独立入口包 `leaf-oray`，上游 `leaf-cli` 的默认功能保持一致。
仅开启 `config-json,inbound-socks,outbound-vmess,openssl-aead,ctrlc`。
不编译 SS、VLESS、Trojan、TLS/WS 传输、QUIC、TUN、API 或热重载。
VMess 是 AEAD TCP 模式，支持 `aes-128-gcm` 和 `chacha20-ietf-poly1305`。
需要 TLS/WebSocket 的 VMess 节点不能用这个版本。

使用单线程 Tokio 运行时，优化配置为 `opt-level=z`、fat LTO、单代码生成单元、
panic abort 和符号剥离。OpenSSL 和 musl 静态链接，不依赖 Oray 上的动态库。
32 位 MIPS 缺少原生 64 位原子操作，流量统计使用 `portable-atomic` 的兼容实现；
原生支持 64 位原子操作的平台继续使用标准库类型。
静态展开依赖使用软浮点工具链的 GCC `libgcc_eh`（提供 `_Unwind` ABI），
通过 `libunwind.a` 链接别名供 Rust musl 标准库使用。

## 产物与空间

- `leaf-oray-vmess`：原始静态二进制，按此大小判断常规安装所需空间。
- `leaf-oray-vmess.gz`：只用于下载，执行前必须解压。
- `leaf-oray-vmess-upx`：如果打包成功，UPX 压缩后的可执行文件，执行前无需另行解压。
- `SHA256SUMS`、`BUILD-INFO.txt`、`FEATURES.txt`、`Cargo.lock`：校验值和构建依赖信息。

Actions Summary 报告实际字节数。CI 对原始和 UPX 可执行文件进行 MIPS 24KEc
模拟器启动、配置和 SOCKS5 握手测试。此测试不代表已连接真实远端 VMess 服务器。
如 UPX 不支持该 ELF，包中只提供原始版本并记录原因。

Oray 设备已知可写 Flash `/overlay` 总共 1.5 MiB、约剩 932 KiB。
只有可执行文件加配置及维护余量小于剩余空间，才适合放在 `/root` 持久运行。
设备的 16 MB Flash 大多属于系统固件，不等于有 16 MB 可用于安装。
如原始和 UPX 版都超过剩余 Flash，此构建不能满足当前固件上的持久安装需求；
需要可挂载的持久存储，或另行规划固件/分区，不能把 gzip 大小当作可运行大小。
UPX 只减少磁盘文件，运行时仍需内存解压，不是减少到相同大小的内存占用。
本工作流不刷写固件、调整分区或写入设备 Flash。

## 配置与 HEV 配合

编辑随包的 `leaf.example.json`，填入真实服务器 IP、端口、UUID 和加密方法，保存为 `leaf.json`。
文件只支持 JSON 配置，不接受其他客户端的 Base64 VMess 分享链接。
现有 HEV 映射 DNS 会影响路由器上的上游域名解析，因此这里建议预先解析服务器并填真实 IP。

```sh
chmod 600 /root/leaf.json
/root/leaf-oray-vmess -c /root/leaf.json -T
nohup /root/leaf-oray-vmess -c /root/leaf.json >/tmp/leaf.log 2>&1 </dev/null &
```

以上命令的前提是产物实际能装入 `/root`。使用 UPX 版时相应替换文件名。
确认 Leaf 可用后，HEV 的 SOCKS5 后端可指向 `127.0.0.1:1080`，本地入口无认证：

```text
客户端 → HEV tun0 → Leaf SOCKS5 入口 → VMess TCP 服务器
```

Leaf 负责 VMess；现有 HEV 管理脚本负责路由、DNS 和客户端转发。
运行内存、UDP、真实内核及具体远端节点的兼容性还需要设备上验证。
