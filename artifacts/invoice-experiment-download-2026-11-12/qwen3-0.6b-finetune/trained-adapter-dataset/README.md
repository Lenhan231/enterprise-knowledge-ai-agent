# Qwen3-0.6B invoice LoRA adapter

Trained on the 900-invoice train split from the private 1,000 synthetic invoice dataset. The 50-invoice test cohort remained held out. Three epochs, 339 optimizer steps, LoRA r=16/alpha=32. Best validation loss: 1.0850759e-05 at step 339. Training runtime: 29,437 seconds on a Kaggle Tesla T4.

Base: `Qwen/Qwen3-0.6B` at revision `c1899de289a04d12100db370d81485cdf75e47ca`. This adapter was recovered from the completed training checkpoint after the Kaggle kernel died while initializing OCR for the holdout benchmark. Synthetic training evidence was reconstructed from invoice labels; real PDF OCR benchmark is still pending.
