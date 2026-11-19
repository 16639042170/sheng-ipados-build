# P1 构建 handoff（2026-11-19 夜间）

## 目标
小米平板 6S Pro（sheng, SM8550, 12+256, SN 6ddd3ec6）刷 iPadOS 27（profile `ipados-27.0.1-24A446`），
P1 产物：带 sleep/wake（ArmCpu sleep）的 boot.img，启动参数 `platform-sleep=1`。只刷 `boot_a`。

## 方向（用户 2026-11-19 拍板：A）
内核回 `82b847c4ac3f68a57024b3082ffa3a03442defd9`（device 仓库自己钉的版本），
cherry-pick 两个 sleep 提交 `90873392b74445c75a15d48769bd570322b8136a`（PR #299，merge）和 `099c72fd`，
然后叠 device 的 25 条板级补丁（去掉 `sheng-startup-failure-log.patch`、`sheng-process-exit-log.patch`）。

## 已确认（预检 44561480376）
1. `90873392` 是 merge commit，必须 `git cherry-pick -m 1`。
2. cherry-pick 在 `drivers/ArmCpu` 子模块指针上冲突；提示要把子模块更新到合并提交 `5f37026`（或该提交带入的指针）。
   下一步：`git -C drivers/ArmCpu fetch` 后 checkout 到 90873392 里的指针，再 `git add drivers/ArmCpu` 继续。
3. 板级补丁要在 **xnu 源码根** 里 `git apply -p1`，不是 UniXNU 仓库根。预检里 xnu 根路径识别仍不对（报 `osfmk/arm64/cpu.c` 找不到）。
   下一步：先打印 `find kernel -name osfmk -type d` 确认根，再 cd 进去打。

## 当前在跑
- `package-sleep-27` run `44557722898`（commit `0317471`，519d8024 路线第 14 轮）——睡后继续跑，出包可作对照。
- 历史 13 轮修的上游缺陷见本地 `D:\sheng-ipados\P1-CI-2026-11-19.md`（云环境无此文件）。

## 明日第一步（不需要用户操作）
1. 修 preflight 的两个问题（子模块冲突 + xnu 根），重跑预检（~8 分钟）。
2. 预检绿了再改主 workflow 到 82b847c 路线全量构建（~70–80 分钟）。
3. 出包后：重打成 v4 格式（`repack-v4.py`）、核 SHA、再喊用户接 USB。

## 禁忌（不变）
只刷 boot_a；不 erase userdata、不 fastboot -w、不 fastboot boot、不选 Install and boot、不切 slot、不锁 BL。
fastboot 用 `C:\Windows\System32\fastboot.exe`（36.0.0），禁用 `C:\adb\fastboot.exe`。
