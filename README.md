# 发票解析系统

还原你的真实工作流：**上传原始 Tracker list.xlsx（只有 Tracker list 表）→ 上传一批发票 →
融合生成新的 xlsx（Tracker list + Expenses report + Bills 三个 sheet）**。

- **Tracker list** 等原有 sheet 原样保留（openpyxl 副本上追加，不改动原内容）。
- **Bills** 模块：发票按时间顺序编号 `1#`、`2#`…，左右两栏贴图（E/N 列标签）。
  贴图做了防重叠：每张等比缩放到「宽 ≤570px、高 ≤430px」，在半栏（9 列）内
  水平居中，左右互不越线、块与块不互相压盖，缝隙最小。
- **Expenses report** 模块：交通/路程类发票自动进表，表头与原表完全一致
  （`Date: | Item: | Location: | Amt (RMB): | HK$ | Bill No.`），日期格式 `d-mmm`。
  无发票的行程（如"工厂已付"）可手工添加，不占编号。
- 若基准文件里已有 Expenses report / Bills（老账本）：新内容**追加**在其后，
  编号自动衔接已有最大编号，旧行一字不动。

## 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | **Python 3.12 + FastAPI + Uvicorn** | 本系统的性能瓶颈在 PDF 解析与 OCR（CPU 密集），Python 拥有最完整的生态：pdfplumber（PDF 文字层）、pypdfium2（扫描件渲染）、RapidOCR（离线中文 OCR）、openpyxl（按原格式写 xlsx）。FastAPI 异步 + 线程池并发解析，上传批次并行处理 |
| OCR | **RapidOCR (onnxruntime)** | 离线、轻量、中文效果好，CPU 即可用 |
| 前端 | **Vue 3 + TypeScript + Vite** | 构建产物 gzip 后约 32KB，纯静态由 FastAPI 直接托管，无 Node 运行时依赖 |

> 为什么不用 Go/Rust：重写后端会失去上述整个发票解析生态（还得再嵌一层 Python
> 或调外部 OCR API），实际吞吐反而更差。Web 层本身不是瓶颈。

## 登录与安全

- 打开页面需先登录；所有 `/api/*` 接口均校验会话，未登录返回 401
- 首次启动自动创建管理员账号 **admin**，随机初始密码写入 `backend/data/初始密码.txt`，
  登录后请在右上角「修改密码」立即修改（修改后其他设备全部退出登录）
- 口令使用 scrypt（内存困难型）加盐哈希存储；登录失败 5 次锁定 15 分钟；
  会话 Cookie 为 HttpOnly + SameSite=Strict，服务端只存 token 的哈希
- 写操作校验 Origin 同源（抗 CSRF）；`/docs` 等调试入口已关闭

## 每日自动清理

- 每天凌晨 **03:00** 自动执行一次：
  - 删除上传时间超过**保留期（默认 30 天）**的发票：记录、原文件、缩略图一起清
  - 清理不被任何记录引用的孤儿文件（反复上传留下的副本）
- 保留期可用环境变量调整，如 `set RETENTION_DAYS=7` 后启动
- 服务启动时也会先做一次孤儿清理

## 快速开始

```bat
:: 1. 首次安装依赖（已装可跳过）
python -m pip install -r requirements.txt

:: 2. 启动（或直接双击 启动.bat）
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://127.0.0.1:8000 ，拖入发票即可。

前端改了代码后重新构建：

```bat
cd frontend
npm install
npm run build
```

## 使用流程

1. **上传基准**：先点「上传 Tracker list.xlsx」加载原始账本（只有 Tracker list 表的
   干净版即可）。
2. **上传发票**：拖拽或点选多张发票（支持 PDF/OFD/PNG/JPG，单张 ≤30MB）。
3. **核对**：两张表都可在线编辑（日期、项目、路程、金额、HK$、分类）。
   点卡片上的 `→ Bills / → 路程` 可把发票在两个模块间移动；解析存疑的会黄条提醒。
4. **补录**：`＋ 添加无发票行程` 录入工厂已付等无票行程（备注默认"（工厂已付）"）。
5. **导出**：`导出 Excel` 生成融合后的新 xlsx（含 Tracker list + Expenses report +
   Bills）。

## 识别能力

- 字段：发票号码、开票/乘车日期（优先乘车时间）、价税合计、税额、销售方、项目名称。
- 分类：滴滴/出租/高铁/动车/火车/机票/住宿 等自动归类进 Expenses report，
  其余（餐费、办公用品…）只进 Bills。
- 路程：按票据类型套用 Location 规则——高铁/动车/火车统一成「A站到B站」
  （如 赣州站到长沙站，缺「站」字自动补）；滴滴打车/出租车**不自动填**，
  留空由人工补充。规则集中在 `parsers/fields.py` 的
  `apply_location_rules`，后续新规则加在那里。
- PDF 有文字层直接解析；扫描件自动渲染走 OCR；OFD 直接解包 XML 抽文本。

## 目录结构

```
backend/
  app/
    main.py            FastAPI 路由 + 静态托管 frontend/dist
    pipeline.py        单张发票处理流水线
    parsers/extract.py PDF/OFD/图片取文本、渲染、缩略图（PDFium 全局锁）
    parsers/fields.py  字段正则抽取、分类、路程识别
    exporter.py        按原 Tracker 格式生成 xlsx
    store.py           data/session.json 会话存储
  data/                上传原文件、缩略图、会话（运行时生成）
frontend/              Vue3 + TS + Vite 源码，构建产物在 frontend/dist
scripts/
  make_samples.py      伪造样例发票（滴滴 PDF/高铁/火车/OCR 图片）
  e2e_test.py          端到端测试（干净基准融合 / 老账本追加 / 无基准，含贴图防重叠断言）
  fixtures/            tracker_blank.xlsx（干净基准副本）等测试夹具
```

## 已知边界

- OFD 无通用渲染器：字段可解析，但 Bills 贴图会跳过该张（只保留编号）。
- 图片发票识别依赖 OCR 质量，个别字段可能要手工改；所有字段均可编辑。
- 并发安全：PDFium 非线程安全，所有渲染已统一走全局锁；OCR 引擎单例共享。
- 会话数据在 `backend/data/session.json`，页面"清空"只清记录不删文件。

## 测试

```bat
python scripts/e2e_test.py
```

自动生成样例发票 → 起服务 → 上传断言 → 导出校验（表头/排序/编号/贴图锚点）。
