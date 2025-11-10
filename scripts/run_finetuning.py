import argparse
import json
import os
from pathlib import Path
from typing import List

import torch
from torch.utils.data import DataLoader
from torch.optim import AdamW
from transformers import get_linear_schedule_with_warmup
from tqdm.auto import tqdm
from sentence_transformers import SentenceTransformer, InputExample, losses


def load_pairs(path: Path, max_samples: int = 0) -> List[InputExample]:
    examples: List[InputExample] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            obj = json.loads(line)
            texts = obj.get("texts")
            if not texts or len(texts) < 2:
                continue
            anchor, positive = texts[0], texts[1]
            examples.append(InputExample(texts=[anchor, positive]))
            if max_samples and len(examples) >= max_samples:
                break
    return examples


def main():
    parser = argparse.ArgumentParser(description="Finetune BGE model with MNRL on prepared pairs")
    parser.add_argument("--train_pairs_path", type=str, default="data/train_pairs.jsonl")
    parser.add_argument("--base_model", type=str, default="BAAI/bge-large-zh-v1.5")
    parser.add_argument("--output_dir", type=str, default="models/finetuned_embedding_v1")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--warmup_fraction", type=float, default=0.1)
    parser.add_argument("--max_samples", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)

    train_path = Path(args.train_pairs_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading pairs from {train_path}")
    train_examples = load_pairs(train_path, max_samples=args.max_samples)
    if not train_examples:
        raise RuntimeError("No training pairs loaded. Ensure data/train_pairs.jsonl exists and is non-empty.")

    print(f"Loading base model: {args.base_model}")
    model = SentenceTransformer(args.base_model)
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    model.to(device)
    model.max_seq_length = 512

    train_dataloader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=min(args.batch_size, 32),
        collate_fn=model.smart_batching_collate,
    )
    train_loss = losses.MultipleNegativesRankingLoss(model)

    warmup_steps = int(len(train_dataloader) * args.epochs * args.warmup_fraction)
    print(f"Device: {device} | Epochs: {args.epochs} | Batch size: {train_dataloader.batch_size} | LR: {args.lr} | Warmup steps: {warmup_steps}")

    # Manual training loop (avoids HF Trainer/accelerate issues on Windows CPU)
    total_steps = len(train_dataloader) * args.epochs
    optimizer = AdamW(model.parameters(), lr=args.lr)
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )

    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        for features, labels in tqdm(train_dataloader, total=len(train_dataloader), desc=f"Epoch {epoch+1}/{args.epochs}"):
            optimizer.zero_grad()
            loss_value = train_loss(features, labels)
            loss_value.backward()
            optimizer.step()
            scheduler.step()
            epoch_loss += loss_value.item()

        avg_loss = epoch_loss / max(1, len(train_dataloader))
        print(f"Epoch {epoch+1} average loss: {avg_loss:.4f}")

    # Save the finetuned model
    model.save(str(output_dir))
    print(f"Finetuned model saved to {output_dir}")


if __name__ == "__main__":
    main()
