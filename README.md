# 万能 GIF 工坊 · Universal GIF Studio

给支持 Agent Skills 和图像生成的助手使用。输入角色、动漫或游戏名，助手会选角色、设计动作、生成关键姿势，再用项目脚本导出独立 GIF 并打包。默认 **8 张，每张 64 帧，512×512，透明底，循环播放**。

| 你输入 | 默认产出 |
| --- | --- |
| 胡桃 | 同一角色的 8 个不同动作 |
| 火影忍者 | 8 位角色，每人一个招牌动作 |
| 王者荣耀 | 8 位英雄，每人一个招牌动作 |
| 只做 3 张，像素风，动作和时长我指定 | 按你的要求制作 |

也可以输入自创角色、参考图、动作清单或已有素材。生图助手负责理解指令和绘制关键姿势。Python 脚本接收动作图或已有 GIF，负责插帧、透明导出和视频合成。

## 在支持 Agent Skills 的环境使用

把本目录作为一个 Skill 导入。入口为 `SKILL.md`，请保留 `scripts/` 和 `agents/`。然后向助手输入：

> 用万能 GIF 工坊做《火影忍者》的 8 张 Q 版招牌动作 GIF，透明底，打包成 ZIP。

> 用万能 GIF 工坊给胡桃做 3 张。动作是招来小幽灵、偷偷探头、笑着挥手。每张节奏按动作调整。

## 本地处理已有素材

使用 Python 3.10 或更新版本。九宫格视频额外需要支持 H.264 编码的 FFmpeg，以及能显示角色名的字体。默认使用 Linux 的 Noto Sans CJK，其他环境可传入 `--regular-font` 和 `--bold-font`。

```bash
python -m pip install -r requirements.txt
python scripts/export_gif.py atlas.png output/action.gif --duration-ms 2300
python scripts/showcase.py showcase.json output/showcase.mp4
```

`atlas.png` 为包含 16 个连续姿势的 4×4 透明动作图，顺序从左到右、从上到下。也可使用透明的 512×512、16 帧 GIF 作为输入。导出脚本会校验输出帧数、透明背景、循环和时长。 可用 `--size 320` 调整尺寸，或用 `--background "#f8f5fc"` 指定实底。

`showcase.json` 的 `items` 需要九个条目，每项使用 `{"name":"角色名","gif":"output/action.gif"}`。GIF 路径相对清单文件。可选字段包括 `title`、`subtitle` 和 `seconds`。输出是浅色实底的 1080×1920 MP4，各角色按自己的时间轴播放。

## 许可

代码和文档采用 MIT 许可证。仓库不包含既有角色图片、动画素材或账号密钥。
