# 夏天Jackey 游戏价目表（云端自动同步）

每小时自动从 WPS 金山文档拉取游戏表 → 解析脱敏 → 构建静态页 → 发布 GitHub Pages。

- 数据源：金山文档「夏天Jackey」PS丨NS数字版游戏表（仅 PS 游戏表实时同步）
- 隐私：账号/密码/邮箱等敏感列在解析阶段剔除，仓库与发布产物均不含敏感数据
- 手动触发：GitHub 仓库 → Actions → sync-and-deploy → Run workflow
