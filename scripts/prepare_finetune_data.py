import argparse
import json
from pathlib import Path
from typing import List, Dict, Tuple

from tqdm import tqdm
from rank_bm25 import BM25Plus
import jieba


def tokenize(text: str) -> List[str]:
    text = (text or "").strip().lower()
    return [t for t in jieba.lcut(text) if t.strip()]


def load_benchmark_cases(path: Path) -> Tuple[List[Dict], List[Dict]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    corpus = data.get("corpus", [])
    queries = data.get("queries", [])
    return corpus, queries


def load_chunks(chunks_path: Path) -> List[str]:
    texts: List[str] = []
    if not chunks_path.exists():
        return texts
    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            text = obj.get("text") or obj.get("content")
            if text:
                texts.append(str(text))
    return texts


def build_bm25_index(corpus_texts: List[str]) -> Tuple[BM25Plus, List[List[str]]]:
    tokenized_corpus = [tokenize(t) for t in corpus_texts]
    bm25_model = BM25Plus(tokenized_corpus)
    return bm25_model, tokenized_corpus


def main():
    parser = argparse.ArgumentParser(description="Prepare finetuning data: pairs and triplets with BM25 hard negatives")
    parser.add_argument("--benchmark_cases_path", type=str, default="tools/embedding_benchmark_cases.json")
    parser.add_argument("--chunks_path", type=str, default="data/processed/chunks.jsonl")
    parser.add_argument("--output_pairs_path", type=str, default="data/train_pairs.jsonl")
    parser.add_argument("--output_triplets_path", type=str, default="data/train_triplets.jsonl")
    parser.add_argument("--num_hard_negatives", type=int, default=3)
    parser.add_argument("--max_pairs", type=int, default=0, help="Limit number of pairs (0 means no limit)")
    args = parser.parse_args()

    benchmark_path = Path(args.benchmark_cases_path)
    chunks_path = Path(args.chunks_path)
    out_pairs = Path(args.output_pairs_path)
    out_triplets = Path(args.output_triplets_path)

    out_pairs.parent.mkdir(parents=True, exist_ok=True)
    out_triplets.parent.mkdir(parents=True, exist_ok=True)

    corpus, queries = load_benchmark_cases(benchmark_path)
    doc_map: Dict[str, str] = {d["id"]: d.get("content", "") for d in corpus}
    corpus_texts = [d.get("content", "") for d in corpus]
    chunk_texts = load_chunks(chunks_path)

    combined_texts: List[str] = []
    combined_texts.extend([t for t in corpus_texts if t])
    combined_texts.extend([t for t in chunk_texts if t])

    if not combined_texts:
        raise RuntimeError("No texts found for BM25 index. Ensure corpus and chunks.jsonl exist.")

    bm25_model, _ = build_bm25_index(combined_texts)

    pairs_written = 0
    seen_pairs = set()

    with out_pairs.open("w", encoding="utf-8") as fpairs, out_triplets.open("w", encoding="utf-8") as ftrip:
        for q in tqdm(queries, desc="Generating pairs & triplets"):
            anchor = q.get("text", "").strip()
            rel_ids = q.get("relevant_doc_ids", [])
            if not anchor or not rel_ids:
                continue

            # BM25 retrieval
            q_tokens = tokenize(anchor)
            top_docs = bm25_model.get_top_n(q_tokens, combined_texts, n=50)

            for pid in rel_ids:
                positive = (doc_map.get(pid) or "").strip()
                if not positive:
                    continue

                # Write pair for MNRL
                key = (anchor, positive)
                if key not in seen_pairs:
                    fpairs.write(json.dumps({
                        "texts": [anchor, positive],
                        "meta": {"query_id": q.get("id"), "positive_doc_id": pid}
                    }, ensure_ascii=False) + "\n")
                    seen_pairs.add(key)
                    pairs_written += 1

                # Generate hard negatives among BM25 results, exclude positives
                negatives = []
                for cand in top_docs:
                    if cand.strip() == positive:
                        continue
                    if cand and cand not in negatives:
                        negatives.append(cand)
                    if len(negatives) >= args.num_hard_negatives:
                        break

                # Write triplets
                for neg in negatives:
                    triplet = {
                        "anchor": anchor,
                        "positive": positive,
                        "negative": neg,
                        "meta": {"query_id": q.get("id"), "positive_doc_id": pid}
                    }
                    ftrip.write(json.dumps(triplet, ensure_ascii=False) + "\n")

            if args.max_pairs and pairs_written >= args.max_pairs:
                break

    print(f"Pairs written: {pairs_written}. Triplets path: {out_triplets}")


if __name__ == "__main__":
    main()

