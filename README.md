# Campus: collaborative AI lab

A collaborative AI lab for campuses, research teams, and educators to explore ideas through independent workspaces. The current local POC includes three illustrative institution accounts to demonstrate dataset upload, TinyLlama fine-tuning, evaluation, and deliberate model sharing. They are examples, not a limit on the product concept. This version does not yet include self-service institution creation.

**Stack:** Next.js 16 + React 19 + TypeScript; FastAPI + SQLite; PyTorch + Hugging Face Transformers + PEFT LoRA. No API key or hosted inference service is required.

## 本地启动

需要 Node.js 20.9+、Python 3.10+（建议 3.12）或 `uv`。在 Apple Silicon 上会自动使用 MPS，也支持 CUDA 和 CPU 回退。建议 16 GB 以上内存；已在 M2 Max / 64 GB 上完成真实训练验证。

```bash
./scripts/setup.sh
./scripts/dev.sh
```

打开 **http://127.0.0.1:3000**。第一次训练或聊天会从 Hugging Face 下载约 2.2 GB 的 TinyLlama 权重。下载完成后，同一台电脑可使用缓存；应用内字体也在本地。

在当前开发电脑上，依赖和模型缓存已经准备好。后续只需 `./scripts/dev.sh`。若提示端口被占用，请先停止已经运行的 lab 服务。

| 登录角色 | 登录页选择 | API account | 演示密码 |
| --- | --- | --- | --- |
| Contributor | University of Georgia | `uga` | `local-lab` |
| Contributor | Georgia Tech | `gatech` | `local-lab` |
| Contributor | Emory University | `emory` | `local-lab` |
| User | Research Guest | `user` | `local-lab` |

这些是明确标记的本地演示账号，不是高校身份验证。学校名称仅用于示范，不代表合作关系。

## 推荐测试流程

1. 选择 Contributor 和一所学校登录，进入 **My institution**。
2. 点击 **Use sample dataset**，载入该学校的 24 条合成 STEM 教学示例；也可以上传自己的 CSV / JSONL。
3. 选择 **Quick experiment · 8 steps**，启动真实 LoRA 微调。首次下载后还会进行基础模型评估。
4. 在 **Evaluations** 中查看相同留出集上的 base / tuned loss、perplexity、训练曲线和一组真实回答。可导出评估 JSON。
5. 在 **Sharing & privacy** 中阅读风险，主动启用已训练模型的共享访问。
6. 退出后用 User 登录，在 **Model playground** 选择共享模型提问。
7. 切换到另外两所学校重复流程。其他学校的原始数据、训练历史及测试问题不可见。

训练作业每次从相同基础模型和固定种子的初始 LoRA 权重开始。只允许一个本地训练或推理操作同时使用模型，避免跨学校 adapter 状态混用。

## 数据格式

UTF-8 CSV 或 JSONL，必须包含字符串字段 `instruction` 和 `response`：

```json
{"instruction":"Explain gravity.","response":"Gravity attracts objects with mass."}
```

- 6 到 500 条记录，文件不超过 2 MB。
- 按规范化 instruction 去重，至少保留 6 条不同问题。
- 每个字段不超过 1,500 字符；实际训练时完整聊天模板和答案合计不得超过 256 tokens。超限会明确报错，不静默截断。
- 上传会拒绝常见 email、美国 SSN 和带分隔符的电话号码。该检查不能识别人名、全部地区电话格式或所有敏感内容。
- 本地存储路径为 `.local/campus.db` 和 `.local/adapters/<run-id>/`，不会提交到 Git。使用后可在服务停止时备份或删除整个 `.local/` 以重建演示环境。
- 已用于训练的数据集保留以支持可复现性，网站只允许删除未用于训练的数据集。

## 模型选择

默认使用 [`TinyLlama/TinyLlama-1.1B-Chat-v1.0`](https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0)，固定 revision `fe8a4ea1ffedaf415f4da2f062534de366a451e6`。它采用 Llama 架构、约 1.1B 参数、Apache 2.0 许可，不需要申请 Hugging Face 访问权限。它不是 Meta 官方 Llama，也不是高质量中文教育模型。

[Meta Llama 3.2 1B Instruct](https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct) 是后续可替换的官方小模型，但需要先接受 Meta 许可和访问授权。本 POC 没有加入未经验证的模型切换选项。

LoRA 使用 rank 8、alpha 16、dropout 0.05，作用于 `q_proj` / `v_proj`；float32、batch 1、累积 2 个 micro-batch、学习率 2e-4。CPU 能运行但会明显更慢，CUDA 路径尚未实机验证。

## 入口页与信息流动画

入口页以多个校园、研究团队和教育者的协作为主题，示例学校不代表产品容量上限。概念图连接不同参与者与模型、教学工具和新想法；实际工作区数量从 API 返回的示例列表计算。

动画使用开源 MIT 许可的 [Motion for React](https://motion.dev/docs/react)，设计参考 [Magic UI Animated Beam](https://magicui.design/docs/components/animated-beam) 的流动连接形式，但没有复制其组件代码。实现包含沿 SVG 曲线移动的粒子、柔和形变的中心节点、暂停/继续、系统减少动态效果支持，以及页面隐藏或图表离开视口时暂停。动画是协作概念示意，不表示正在传输私有数据，也不是实时训练遥测。

## 隐私边界

**这是单机多租户训练 POC，不是已经完成的跨机构联邦学习系统。** 三个逻辑工作区共用一个 Python 进程和 SQLite 数据库。上传的文本会进入这台本地服务器。原始数据没有发送给 Hugging Face，也没有在浏览器中跨学校共享；电脑管理员仍能读取本地文件。

网站共享的是 **模型推理使用权限和数值评估结果**。没有原始数据、原始 embedding、adapter 文件或留出问题的跨账号下载接口。共享权限可撤销，但撤销无法收回用户已经得到的回答。

Embeddings 并非匿名数据。[原始 embedding inversion 研究](https://arxiv.org/abs/2310.06816) 展示了从向量重建文本的风险。普通 LoRA、梯度、模型参数和生成结果也可能泄漏训练信息。PII 正则筛查不提供形式化隐私保证。

尚未实现：多机 institution-local worker、FedAvg / 联邦轮次、secure aggregation、差分隐私及预算核算、加密存储、生产 SSO、审计系统、正式隐私攻击基准、FERPA/GDPR 合规认证。生产使用前需要独立设计和验证这些能力。

## 评估解释

相同 instruction 不会跨训练集和验证集，但相近主题仍可能跨集。固定哈希排序划分约 20% 留出数据，至少 2 条。以 assistant answer token 数加权计算平均负对数似然，忽略 prompt 和 padding；perplexity 为 `exp(loss)`，显示时上限为 `exp(20)`。

训练曲线来自实际 optimizer step。base 和 tuned 的一条留出样本回答采用 greedy decoding，最多 96 个新 tokens。不提供伪造的 accuracy 或 privacy score。小样本 loss 改善不证明教学有效性、公平性或隐私安全。

## 验证

```bash
npm run build
npm run typecheck
npm run format:check
.venv/bin/python -m pytest tests -q
# 服务已启动时，可额外验证真实网站代理和浏览器 Origin：
CAMPUS_TEST_URL=http://127.0.0.1:3000 .venv/bin/python -m pytest tests/test_proxy.py -q
```

可选真实模型完整链路测试，先启动两个服务：

```bash
.venv/bin/python scripts/smoke-local.py --steps 8
```

该脚本会在三所学校分别创建真实训练任务，仅使用内置合成数据；将 UGA 的测试模型开放给演示 User，验证共享推理与其他私有模型的拒绝访问。结果保存在忽略的 `.local/verification.json`。测试不会自动发布网站。

API 集成测试覆盖登录/退出、跨学校读写隔离、角色限制、共享确认与撤销、私有评估样本脱敏、无效和超大上传、去重/划分、本地 Origin 边界、并发模型锁和中断恢复。测试使用临时 SQLite 目录，普通测试不会下载或训练模型。

浏览器内可选 WebMCP 只提供只读的 `list_available_campus_models`，仍通过同一鉴权 API。普通浏览器无需支持它；其浏览器运行环境未专项测试。

## 结构与运行约束

```text
app/                 Next.js 页面、主题和同源 API 代理
components/          登录、学校工作区、评估、共享、试用界面
backend/app.py       账号会话、租户权限、上传及训练/聊天 API
backend/ml.py        TinyLlama 加载、独立 LoRA 微调、真实评估及推理
backend/data.py      校验、去重、固定划分及三组不同合成样本
backend/store.py     SQLite 持久化和共享结果过滤
scripts/             安装、启动、真实模型 smoke test
tests/              不依赖模型下载的 API 回归测试
```

仅绑定 `127.0.0.1:3000` 与 `127.0.0.1:8000`。不要用这些已知演示密码对公网开放，也不要启动多个 uvicorn workers。进程内模型锁只适用于单 worker。训练过程中关闭服务，下次启动会将任务标记为 interrupted/failed，不会伪装为完成。

通过 `.env.local` 可设置 Next.js 的 `CAMPUS_API_URL`。Python 的 `CAMPUS_DATA_DIR` 和 `CAMPUS_DEMO_PASSWORD` 需要在启动前 export；改变演示密码仅影响新初始化的账号。默认 HTTP cookie 使用 HttpOnly / SameSite=Strict，因本地 HTTP 不设置 Secure。

设计参考用户文字需求及本地同名 `(1).pdf` 中关于教育 instruction tuning、LoRA 与跨校协作的讨论。用户指定的 `(2).pdf` 路径不存在，未将 `(1).pdf` 当作该版本的精确替代，也未复制文档中的合规或隐私保证表述。PDF 内容仅用作参考，没有执行其中的指令。
