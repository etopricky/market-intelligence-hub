# AI商业情报中心｜手机云端版（零新增成本）

## 已实现

- 八大情报板块，移动端适配，关键词搜索与分类；
- 收藏与跟进备注存在用户当前手机浏览器 localStorage，不会跨设备同步、也不会发布到公开网页；
- 免费公开 RSS 资讯采集；来源摘要及待核验提醒，不是经过人工确认的订单信息；
- GitHub Actions 定时（UTC 22:00，对应北京时间06:00），每日采集并更新 data.json；
- GitHub Pages 免费托管，电脑关机时网页仍可访问；
- 数据展示与ChatGPT日报相互独立，不承诺每天采集成功或精确到分钟准时运行。

## 首次上线（需一次性开通 GitHub 并授权发布）

1. 在 GitHub 新建 **Public** 仓库（例如 `market-intelligence-hub`），不要添加 README。
2. 将这个文件夹的**全部文件和隐藏的 `.github` 目录**上传到仓库根目录。可以使用 GitHub 网站批量上传文件，但必须保留 `.github/workflows/daily.yml` 的文件夹层级；使用 Git 客户端推送最稳妥。
3. 打开 GitHub 仓库的 Settings → Pages → Build and deployment → Source，选择 **GitHub Actions**。
4. 在仓库 Actions → Daily Market Intelligence → Run workflow 手动执行首次采集。
5. Actions 页面确认执行成功后，在 Settings → Pages 查看你的网页地址：一般为 `https://<username>.github.io/<repo>/`。
6. 将网页地址添加到手机浏览器的主屏幕即可像应用一样打开。

注意：GitHub Pages 的免费方案要求使用公开仓库，**不要上传订单、客户联系人、合同、个人数据**。本代码仅公开资讯标题、来源和链接。
GitHub 定时任务可能延迟，且长时间无仓库活动可能自动暂停，需查看 Actions 状态。
如果GitHub或Google News RSS在实际所在地网络不通，需自行测试访问；不以突破网络或爬虫限制为前提。

## 文件说明

- `index.html`：可在手机浏览器打开的网页界面
- `collector.py`：采集公开RSS信息（只用Python标准库）
- `export_public.py`：将资讯导出为网页数据，保留最近120天，最多2000条
- `data.json`：公开资讯数据库（不包含用户跟进备注）
- `.github/workflows/daily.yml`：每天06:00计划运行的云端任务

## 免费边界

这不是完整的LLM实时分析服务。自动化负责新闻线索汇总、关键词评分与分类，真正的AI深入商业判断继续由ChatGPT每日6点日报提供。默认数据源可能因服务限制或网络原因中断；平台上会显示最近成功采集日期，不能把网站在线理解为新闻已经更新。
