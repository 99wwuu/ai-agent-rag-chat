# -*- coding: utf-8 -*-
r"""
RAG 系统量化评测脚本
=================================
功能：
  1. 用黑神话悟空.txt 构建真实 FAISS 知识库
  2. 用 20 道测试题跑 FAISS-only / BM25-only / Ensemble 混合 三种检索
  3. 测每个问题的 Recall@k（关键词是否命中 Top-k 文档）
  4. 测三种检索的平均耗时
  5. 额外测：混合检索对单路的提升率
  6. 额外测：大模型生成的 TTFT（首 token 延迟）和 tokens/s
  7. 输出 JSON 报告 + 终端摘要

用法：
  cd <项目根目录>
  python eval/run_eval.py

环境要求：
  依赖项目已有的 langchain、faiss、jieba、siliconflow API key
"""

import os
import sys
import json
import time
import statistics

# ============ 路径准备 ============
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # 切到项目根目录，让 configs/setting.py 里的相对路径正常工作

# 评测用的临时知识库（不污染项目正式知识库；评测脚本用内存版 FAISS，根本不写盘）
TEST_FILE = os.path.join(PROJECT_ROOT, "data", "wukong", "黑神话悟空.txt")
TEST_DATASET = os.path.join(PROJECT_ROOT, "eval", "test_dataset.json")
REPORT_JSON = os.path.join(PROJECT_ROOT, "eval", "report.json")

# ============ 复用项目的配置 ============
from configs.setting import api_key, base_url, chat_model_name  # noqa: E402
from langchain_openai import OpenAIEmbeddings  # noqa: E402
from langchain.embeddings.base import Embeddings  # noqa: E402
from langchain_community.vectorstores import FAISS  # noqa: E402
from langchain_community.retrievers import BM25Retriever  # noqa: E402
from langchain.retrievers import EnsembleRetriever  # noqa: E402
from langchain.text_splitter import RecursiveCharacterTextSplitter  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
import jieba  # noqa: E402


# 和 kb_routes.py 里完全一致的 CustomEmbeddingModel
# 硅基流动的 embedding API 需要显式把 model 名传给 client.create()
class CustomEmbeddingModel(Embeddings):
    def __init__(self, model, model_name):
        self.model = model
        self.model_name = model_name

    def embed_documents(self, texts):
        return [self.model.client.create(
            model=self.model_name, input=text
        ).data[0].embedding for text in texts]

    def embed_query(self, text):
        return self.model.client.create(
            model=self.model_name, input=text
        ).data[0].embedding

print("=" * 60)
print("🎯 RAG 系统量化评测")
print("=" * 60)

# ========================================================
# Step 1: 构建评测用 FAISS 知识库
# ========================================================
print("\n[Step 1] 构建评测知识库 ...")

start = time.time()

# 读取文档
with open(TEST_FILE, "r", encoding="utf-8") as f:
    raw_text = f.read()

# 项目里的切块配置（和 kb_routes.py 保持一致）
splitter = RecursiveCharacterTextSplitter(
    chunk_size=128,
    chunk_overlap=20,
    separators=["\n\n", "\n", " ", ".", ",", "，", "。", ""],
)
chunks = splitter.split_text(raw_text)
docs = [Document(page_content=c, metadata={"source": TEST_FILE, "chunk_id": i})
        for i, c in enumerate(chunks)]
print(f"  文档总字符数: {len(raw_text):,}")
print(f"  切分块数量:   {len(chunks)}")

# 构建 Embedding（和 kb_routes.py 完全一致：OpenAIEmbeddings 只传 api_key+base_url，
# model 名通过 CustomEmbeddingModel 显式传给 client.create()）
_emb_base = OpenAIEmbeddings(
    api_key=api_key,
    base_url="https://api.siliconflow.cn/v1",
)
embedding = CustomEmbeddingModel(_emb_base, "BAAI/bge-large-zh-v1.5")

# 向量化 + 建 FAISS（内存版，评测不需要写盘）
faiss_store = FAISS.from_documents(docs, embedding, normalize_L2=True)
build_time = time.time() - start
print(f"  ✅ FAISS 知识库构建完成，耗时 {build_time:.2f}s")
print(f"     吞吐: {len(chunks) / build_time:.1f} chunks/s")

# ========================================================
# Step 2: 准备三种检索器
# ========================================================
print("\n[Step 2] 初始化三种检索器 ...")

faiss_retriever = faiss_store.as_retriever(search_kwargs={"k": 5})

bm25_retriever = BM25Retriever.from_documents(
    docs, preprocess_func=jieba.lcut_for_search
)
bm25_retriever.k = 5

ensemble_retriever = EnsembleRetriever(
    retrievers=[bm25_retriever, faiss_retriever], weights=[0.5, 0.5]
)

print("  ✅ FAISS-only   retriever 就绪 (k=5)")
print("  ✅ BM25-only    retriever 就绪 (k=5, jieba 分词)")
print("  ✅ Ensemble(混合) retriever 就绪 (BM25 0.5 + FAISS 0.5)")

# ========================================================
# Step 3: 加载测试集 + 跑三种检索，测 Recall@k
# ========================================================
print("\n[Step 3] 跑三种检索对比 (20 道题) ...")

with open(TEST_DATASET, "r", encoding="utf-8") as f:
    dataset = json.load(f)

RETRIEVERS = {
    "FAISS-only":    faiss_retriever,
    "BM25-only":     bm25_retriever,
    "Ensemble(混合)": ensemble_retriever,
}

K_VALUES = [2, 3, 5]  # 测 Top-2/3/5 的命中率

results = {}  # 每种检索器的结果
latencies = {}  # 每种检索器的耗时列表

for retriever_name, retriever in RETRIEVERS.items():
    print(f"\n  —— {retriever_name} ——")
    results[retriever_name] = {}
    latencies[retriever_name] = []

    for k in K_VALUES:
        results[retriever_name][f"Recall@{k}"] = []

    for item in dataset:
        q = item["question"]
        kws = item["keywords"]

        t0 = time.perf_counter()
        top_docs = retriever.invoke(q)
        t1 = time.perf_counter()
        latencies[retriever_name].append((t1 - t0) * 1000)  # ms

        # 对每个 k 值检查
        for k in K_VALUES:
            top_k = top_docs[:k]
            hit = any(
                kw in "".join(d.page_content for d in top_k)
                for kw in kws
            )
            results[retriever_name][f"Recall@{k}"].append(int(hit))

# ========================================================
# Step 4: 统计检索指标
# ========================================================
print("\n" + "=" * 60)
print("📊 检索召回率对比（20 道事实型问答）")
print("=" * 60)

summary = {}
print(f"{'检索器':<18} {'Recall@2':>10} {'Recall@3':>10} {'Recall@5':>10} {'平均延迟':>12}")
print("-" * 62)

for name in RETRIEVERS:
    row = {"retriever": name}
    for k in K_VALUES:
        vals = results[name][f"Recall@{k}"]
        rate = sum(vals) / len(vals) * 100
        row[f"Recall@{k}"] = round(rate, 1)
    lat = statistics.mean(latencies[name])
    row["avg_latency_ms"] = round(lat, 1)
    row["p95_latency_ms"] = round(sorted(latencies[name])[int(len(latencies[name]) * 0.95)], 1)
    summary[name] = row
    print(f"{name:<18} {row['Recall@2']:>9}% {row['Recall@3']:>9}% {row['Recall@5']:>9}% {lat:>10.1f} ms")

# 混合检索提升率
print("\n📈 混合检索 vs 单路检索的提升率：")
ens_r3 = summary["Ensemble(混合)"]["Recall@3"]
faiss_r3 = summary["FAISS-only"]["Recall@3"]
bm25_r3  = summary["BM25-only"]["Recall@3"]

improve_vs_faiss = round(ens_r3 - faiss_r3, 1)
improve_vs_bm25  = round(ens_r3 - bm25_r3, 1)
print(f"  Recall@3 比 FAISS-only 提升 {improve_vs_faiss:+.1f}% ({faiss_r3}% → {ens_r3}%)")
print(f"  Recall@3 比 BM25-only 提升  {improve_vs_bm25:+.1f}% ({bm25_r3}% → {ens_r3}%)")

# ========================================================
# Step 5: 端到端生成测试（TTFT + tokens/s）
# ========================================================
print("\n" + "=" * 60)
print("⚡ 端到端生成性能测试 (3 道题取平均)")
print("=" * 60)

# 挑 3 道题，用混合检索的前 3 条结果作为上下文
llm = ChatOpenAI(
    model=chat_model_name,
    api_key=api_key,
    base_url=base_url,
    temperature=0.5,
    max_tokens=256,
    streaming=True,
)

e2e_samples = dataset[:3]  # 前 3 道
ttft_list = []
total_time_list = []
tokens_per_sec_list = []

for i, item in enumerate(e2e_samples):
    q = item["question"]
    # 取混合检索前 3 条当上下文（真实 RAG 流程）
    hits = ensemble_retriever.invoke(q)[:3]
    context = "\n".join(d.page_content for d in hits)
    prompt = f"""根据以下资料回答问题，只说答案不要废话：
资料：{context}
问题：{q}
答案："""

    t_start = time.perf_counter()
    first_token_received = False
    first_token_time = 0.0
    token_count = 0

    # streaming 遍历
    for chunk in llm.stream(prompt):
        if not first_token_received:
            first_token_received = True
            first_token_time = time.perf_counter() - t_start
        token_count += 1

    total_t = time.perf_counter() - t_start
    ttft_list.append(first_token_time * 1000)
    total_time_list.append(total_t)
    tokens_per_sec_list.append(token_count / total_t if total_t > 0 else 0)
    print(f"  [{i+1}/3] Q: {q[:20]:20s} | TTFT={first_token_time*1000:.0f}ms | 生成 {token_count} tokens / {total_t:.1f}s")

ttft_avg = round(statistics.mean(ttft_list), 0)
total_avg = round(statistics.mean(total_time_list), 2)
tps_avg = round(statistics.mean(tokens_per_sec_list), 1)

print(f"\n  📌 首 token 延迟 (TTFT) 平均: {ttft_avg:.0f} ms")
print(f"  📌 单题总耗时 平均:           {total_avg:.2f} s")
print(f"  📌 生成速度 平均:             {tps_avg:.1f} tokens/s")

# ========================================================
# Step 6: 构建速度指标
# ========================================================
chunk_per_sec = round(len(chunks) / build_time, 1)
build_time_round = round(build_time, 1)

# ========================================================
# Step 7: 汇总写入报告
# ========================================================
report = {
    "测试信息": {
        "知识库": "黑神话悟空.txt",
        "文档总字符": len(raw_text),
        "切块数量": len(chunks),
        "chunk_size": 128,
        "chunk_overlap": 20,
        "Embedding模型": "BAAI/bge-large-zh-v1.5 (硅基流动)",
        "LLM模型": chat_model_name,
        "测试题数": len(dataset),
        "日期": time.strftime("%Y-%m-%d %H:%M"),
    },
    "检索召回率": {
        name: {k.replace("Recall@", "Top-") + "命中率": f"{v}%"
               for k, v in vals.items() if k.startswith("Recall@")}
        for name, vals in summary.items()
    },
    "检索延迟": {
        name: {
            "平均延迟_ms": vals["avg_latency_ms"],
            "P95延迟_ms": vals["p95_latency_ms"],
        }
        for name, vals in summary.items()
    },
    "混合检索提升率": {
        "vs_FAISS-only": f"{improve_vs_faiss:+.1f}% (Top-3命中率)",
        "vs_BM25-only":  f"{improve_vs_bm25:+.1f}% (Top-3命中率)",
    },
    "知识库构建": {
        "总耗时_s": build_time_round,
        "吞吐量_chunks_per_sec": chunk_per_sec,
    },
    "端到端生成性能": {
        "TTFT_首token延迟_ms": ttft_avg,
        "单题平均总耗时_s": total_avg,
        "生成速度_tokens_per_sec": tps_avg,
    },
    "可写入简历的指标": [
        f"基于 FAISS + BM25 双路召回(0.5:0.5)的 Ensemble 混合检索，"
        f"在 20 道事实型问答测试集上 Top-3 召回率达 {ens_r3:.0f}%，"
        f"较单路 FAISS({faiss_r3:.0f}%)提升 {improve_vs_faiss:.0f}%，"
        f"较单路 BM25({bm25_r3:.0f}%)提升 {improve_vs_bm25:.0f}%",
        f"流式响应首 token 延迟(TTFT)平均 {ttft_avg:.0f} ms，生成速度 {tps_avg:.1f} tokens/s，"
        f"显著降低长问答等待体感",
        f"知识库构建吞吐量 {chunk_per_sec:.0f} chunks/s，N 个文档向量化全流程耗时稳定在 {build_time_round:.1f} s 级别",
    ],
}

with open(REPORT_JSON, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 60)
print("✅ 评测完成！报告已保存到:")
print(f"   {REPORT_JSON}")
print("\n🎯 可直接写进简历的量化指标：")
print("=" * 60)
for item in report["可写入简历的指标"]:
    print(f"  📌 {item}")
print("=" * 60)
