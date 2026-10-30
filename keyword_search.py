"""
keyword_search.py — 關鍵字檢索與排名融合（混合檢索用）

語意檢索的弱點：一個切片混了好幾個主題時，重點字詞會被稀釋，
例如「重複上傳」只是 F-03 的一句話，整塊切片的向量卻偏向 F-01 ~ F-02。
關鍵字檢索直接比對字詞，正好補這個洞；兩者排名再用 RRF 合併。

全部手寫、不加新套件：
- 斷詞：中文取「相鄰兩字」(bigram)，英文、數字、程式名稱保持完整
- 評分：BM25（搜尋引擎常用；罕見字詞權重高、到處都有的字詞權重低）
- 融合：RRF（只看名次不看分數，兩種分數尺度不同也能公平合併）
"""
import math
import re
from collections import Counter

# 英數字詞（含 pdf_loader、.env、top-k 這類寫法）與連續的中日韓文字
_WORD = re.compile(r"[a-z0-9][a-z0-9_.\-]*|\.[a-z0-9_]+")
_CJK = re.compile(r"[一-鿿㐀-䶿]+")


def tokenize(text: str) -> list:
    """把文字拆成檢索用的詞：英數字詞整個保留，中文每相鄰兩字為一個詞"""
    text = text.lower()
    tokens = _WORD.findall(text)
    for run in _CJK.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


class BM25:
    """BM25 關鍵字評分；k1、b 為業界常用預設值"""

    def __init__(self, docs: list, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg_len = sum(self.lens) / len(self.lens) if self.lens else 0
        n = len(docs)
        df = Counter(t for tf in self.tfs for t in tf)
        # 出現在越少文件的詞，權重越高（+1 避免負值）
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list:
        """回傳每份文件對 query 的分數（與 docs 順序相同）"""
        q_terms = set(tokenize(query))
        result = []
        for tf, length in zip(self.tfs, self.lens):
            s = 0.0
            for t in q_terms:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            result.append(s)
        return result


def rrf(rankings: list, k: int = 60) -> list:
    """倒數排名融合：rankings 是多組「由好到差的 id 清單」，回傳合併後由好到差的 id

    每組排名第 r 名得 1 / (k + r) 分，加總後排序；k=60 為論文建議值，
    讓第 1 名與第 2 名的差距不會大到單一來源說了算。
    """
    total = {}
    for ranking in rankings:
        for r, doc_id in enumerate(ranking, start=1):
            total[doc_id] = total.get(doc_id, 0.0) + 1.0 / (k + r)
    return sorted(total, key=total.get, reverse=True)
