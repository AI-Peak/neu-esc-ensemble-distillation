"""Semantic contract for the pinned PhoBERT-base-v2 checkpoint, not a file hash.

Explicit values come from vinai/phobert-base-v2 at revision
86cd7fd4c148980922ac11a2cf5e257f2ba639e1. Implicit values are the normalized
RobertaConfig/PretrainedConfig defaults in the supported Transformers 4.44.2.
Compare the loaded config so save_pretrained variants and metadata are harmless.
"""
from __future__ import annotations

PHOBERT_MODEL_ID = "vinai/phobert-base-v2"
PHOBERT_CONFIG_CONTRACT = "phobert-base-v2-inference-v1"
EXPECTED_PHOBERT_CONFIG = {
    "model_type": "roberta",
    "vocab_size": 64001,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "intermediate_size": 3072,
    "max_position_embeddings": 258,
    "type_vocab_size": 1,
    "pad_token_id": 1,
    "bos_token_id": 0,
    "eos_token_id": 2,
    "hidden_act": "gelu",
    "layer_norm_eps": 1e-5,
    "position_embedding_type": "absolute",
    "hidden_dropout_prob": 0.1,
    "attention_probs_dropout_prob": 0.1,
    # Bidirectional encoder; decoder=True changes masks with identical weights.
    "is_decoder": False,
    "add_cross_attention": False,
    "is_encoder_decoder": False,
    "cross_attention_hidden_size": None,
    "tie_encoder_decoder": False,
    "use_cache": True,  # RobertaModel disables KV caching when is_decoder=False.
    "pruned_heads": {},
    "chunk_size_feed_forward": 0,
    # Linear2Head consumes .last_hidden_state; forbid tuple/TorchScript overrides.
    "return_dict": True,
    "torchscript": False,
    "output_attentions": False,
    "output_hidden_states": False,
}


def verify_phobert_config_object(cfg) -> None:
    """Reject shape-compatible forward changes before model allocation or reuse."""
    expected_values = {**EXPECTED_PHOBERT_CONFIG, "_attn_implementation": "eager"}
    # RobertaModel in Transformers 4.44.2 has no SDPA/Flash implementation. The
    # normalized property is eager for both absent and explicit eager settings;
    # this runtime override is deliberately omitted by Transformers.to_dict().
    for field, expected in expected_values.items():
        actual = getattr(cfg, field, None)
        if actual != expected:
            raise ValueError(
                f"PhoBERT config mismatch for {field}: expected {expected!r}, got {actual!r}. "
                "Re-prepare the pinned config with scripts/model_prepare_phobert.py "
                "--out runtime/cache/phobert-base-v2 --source demo and pass "
                "--encoder-config runtime/cache/phobert-base-v2."
            )
