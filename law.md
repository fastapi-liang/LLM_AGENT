理解 Harnrness Engineering 开发范式，能够构建基于 LLM 的系统化基础设施，保证智能体执行任务的稳定性。
 熟悉DeepAgents开发框架，拥有构建能够处理复杂、长周期任务的智能体的企业落地开发经验，对 DeepAgents的规划能力、虚拟文件后端以及 SubAgent 有深刻理解，对 Agent 上下文臃肿及缺乏专业性有企业落地经验。
 拥有企业级 Claw 的落地开发经验，掌握自定义安全沙箱后端来保证企业中数据及文件的安全隔离。 熟悉 Agent Skills 架构的智能体开发，熟练掌握 Agent + Skills 的架构高度模块化、可扩展的设计范式。
  熟悉 LangChain 开发框架，掌握 LLM, Chat, models, PromptTempmplates, OutptputParser, Chains 组件使用。
  掌握自定义 FunctionTool，实现工具的同异步调用。实现聊天以及信息搜索的 Agent 调用功能。 掌握 LangGraph 核心组件，掌握 WoWorkflflow 的构建 和 Multi-Agent 多智能体的工作流企业落地实践。
  掌握 LangGraph 中的长短期记忆的落地实践，基于 Human-in-the-Loop 提升系统的可靠性，安全性和合规性。
  掌握基于 BGE-large-zh-v1.5 私有化方式实现向量数据库的相似性搜索、RARAG 增强检索。
  熟练使用 Document Loaders 对多种文件格式（JSON、HTML、PDF、Markdown、CSV）进行结构化提取，掌握小红书基于 Transfoformer 的 Docs.OCR 和 DeepSeek-OCR 的私有化部署和 OCR 识别图文提取。
  熟练使用 Chroma、Milvus 等向量数据库的分布式部署，构建本地知识库，实现存储与查询。
  掌握向量搜索的元数据增强策略优化，的双索引架构和混合检索，以及多路融合的重排策略优化。
  熟悉 RARAG + RARAGAS 结合 WoWorkFlow 实现动态路由和多模态知识库的检索及评估。
  熟练掌握 FastAPI 框架，具备异步编程与依赖注入能力，可高效开发高性能 RESTfuful API。
  熟悉基于 vllm 的各种大模型的私有化部署，包括但不限于 DeepSeek，Qwen2.5，Qwen3.5，Llama-3.2 等。

为什么不用全量微调，而使用 LoRA？
LoRA 到底修改了模型的什么参数？
LoRA 和 QLoRA 有什么区别？
NF4 为什么能把显存从 19G 降到 7G？
4bit 量化之后，为什么还能训练？
SFT 和 DPO 分别解决什么问题？
DPO 为什么不需要像 PPO 一样训练 Reward Model？
P-Tuning、Prefix-Tuning、LoRA 有什么区别？
训练出现 OOM，你是怎么定位和解决的？
数值下溢是什么？为什么低精度训练容易出现？
你的 20% 准确率提升是怎么测出来的？
为什么选择 LLaMA 3.1-8B？
4090 24GB 为什么能训练 8B 模型？
19GB → 7GB 的显存具体是哪些部分减少了？
如果让你现在重新做这个项目，你会怎么优化？