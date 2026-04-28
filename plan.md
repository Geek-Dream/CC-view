# 修复3个UI Bug — 已完成

## Bug 1: 用户消息气泡过宽 ✅
- `main.py` Line 1168: `bubble.setSizePolicy` 从 `Preferred` 改为 `Minimum`

## Bug 2: AI 输出气泡过窄 ✅
- `main.py` Line 1187: `content.setMaximumWidth` 从 550 改为 700
- bubble size policy 从 `Preferred` 改为 `Minimum`（与 Bug1 一起修）

## Bug 3: 深度思考内容消失 ✅
- `main.py` Line 2695-2704: `_find_latest_thinking_row` 增加 `in_progress` 条件检查，只返回正在进行的 thinking row
- `add_thinking_block` 逻辑自动生效（现有逻辑不变）

## 修改文件
- `main.py` — 3处修改

## 待完成
- 更新 changeLog.md 时间戳
- 测试验证
