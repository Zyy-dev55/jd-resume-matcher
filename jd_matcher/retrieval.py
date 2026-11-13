"""零依赖的轻量检索：BM25 + 中文字符二元组。

不引入 jieba / faiss / 向量库，保证 clone 下来就能跑；
接口按「可替换」设计，后续把 search() 换成向量检索即可对比效果。
"""
import math
import re
from collections import Counter


def tokenize(text):
    """英文按词、中文按 2-gram，短查询也能命中。"""
    text = text.lower()
    en = re.findall(r"[a-z0-9_+#.]+", text)
    zh = re.findall(r"[\u4e00-\u9fff]+", text)
    grams = []
    for seg in zh:
        if len(seg) == 1:
            grams.append(seg)
        else:
            grams.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return en + grams


MIN_EVIDENCE_SCORE = 5.0  # 低于此分视为「无相关证据」，不生成匹配结论；实测负例 <3.3、正例 >12


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [tokenize(d) for d in docs]
        self.k1, self.b = k1, b
        self.n = len(self.docs)
        self.lens = [len(d) for d in self.docs]
        self.avgdl = sum(self.lens) / self.n if self.n else 1.0
        df = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {}
        for term, freq in df.items():
            self.idf[term] = math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))

    def score(self, query_tokens, idx):
        tf = Counter(self.docs[idx])
        dl = self.lens[idx] or 1
        s = 0.0
        for t in set(query_tokens):
            f = tf.get(t, 0)
            if not f:
                continue
            idf = self.idf.get(t, 0.0)
            s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def topk(self, query, k=4):
        q = tokenize(query)
        scored = [(i, self.score(q, i)) for i in range(self.n)]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]


class EvidenceRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        docs = [c["text"] + " " + c["project_name"] + " " + " ".join(c["tags"]) for c in chunks]
        self.bm25 = BM25(docs)

    def search(self, jd, k=4):
        results = []
        for idx, score in self.bm25.topk(jd, k=k):
            c = dict(self.chunks[idx])
            c["score"] = round(score, 3)
            results.append(c)
        return results
