"""Shared-encoder multi-task models with controlled interaction ablations.

The implementation is encoder-agnostic: a Hugging Face ``AutoModel`` can be passed
in, while the same module is also usable with a small test encoder.  The baseline
pooling convention is the first token representation (PhoBERT's ``<s>`` token).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import torch
from torch import Tensor, nn


@dataclass(frozen=True)
class InteractionConfig:
    hidden_size: int
    projection_size: Optional[int] = None
    dropout: float = 0.2
    variant: str = "adaptive"  # baseline, independent, ungated, adaptive
    sentiment_labels: int = 4
    topic_labels: int = 10

    def __post_init__(self):
        if self.variant not in {"baseline", "independent", "ungated", "adaptive"}:
            raise ValueError(f"unknown interaction variant: {self.variant}")
        if self.projection_size is not None and self.projection_size <= 0:
            raise ValueError("projection_size must be positive")


class TaskProjection(nn.Module):
    def __init__(self, in_size: int, out_size: int, dropout: float):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_size, out_size), nn.GELU(), nn.LayerNorm(out_size), nn.Dropout(dropout)
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x)


class AdaptiveInteractionModel(nn.Module):
    """PhoBERT encoder plus independent, ungated, or gated task interaction.

    For the full variant, ``g_s`` and ``g_a`` are learned element-wise gates and
    both directions remain differentiable:

    ``g_s = sigmoid(W_s [h_s; h_a])``; ``z_s = LN(h_s + g_s * T_s(h_a))``.
    """

    def __init__(self, encoder: nn.Module, config: InteractionConfig):
        super().__init__()
        self.encoder = encoder
        self.interaction_config = config
        size = config.projection_size or config.hidden_size
        self.sentiment_projection = TaskProjection(config.hidden_size, size, config.dropout)
        self.topic_projection = TaskProjection(config.hidden_size, size, config.dropout)
        self.sentiment_message = nn.Sequential(nn.Linear(size, size), nn.GELU())
        self.topic_message = nn.Sequential(nn.Linear(size, size), nn.GELU())
        self.sentiment_norm = nn.LayerNorm(size)
        self.topic_norm = nn.LayerNorm(size)
        if config.variant == "adaptive":
            self.sentiment_gate = nn.Linear(2 * size, size)
            self.topic_gate = nn.Linear(2 * size, size)
        else:
            self.sentiment_gate = None
            self.topic_gate = None
        self.sentiment_head = nn.Linear(size, config.sentiment_labels)
        self.topic_head = nn.Linear(size, config.topic_labels)

    def _encoder_features(self, input_ids: Tensor, attention_mask: Optional[Tensor]) -> Tensor:
        output = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        features = getattr(output, "last_hidden_state", None)
        if features is None:
            features = output[0]
        if features.ndim != 3:
            raise ValueError(f"encoder must return [batch, sequence, hidden], got {features.shape}")
        return features[:, 0, :]

    def forward(
        self, input_ids: Tensor, attention_mask: Optional[Tensor] = None, *, return_gates: bool = False
    ) -> Tuple[Tensor, Tensor] | Tuple[Tuple[Tensor, Tensor], Dict[str, Tensor]]:
        shared = self._encoder_features(input_ids, attention_mask)
        if self.interaction_config.variant == "baseline":
            # Verified baseline convention: one pooled shared vector feeds two heads.
            z_s, z_a = shared, shared
            gates = {"sentiment": torch.zeros_like(shared), "topic": torch.zeros_like(shared)}
        else:
            h_s = self.sentiment_projection(shared)
            h_a = self.topic_projection(shared)
            if self.interaction_config.variant == "independent":
                z_s, z_a = h_s, h_a
                gates = {"sentiment": torch.zeros_like(h_s), "topic": torch.zeros_like(h_a)}
            else:
                m_s = self.sentiment_message(h_a)
                m_a = self.topic_message(h_s)
                if self.interaction_config.variant == "ungated":
                    g_s = torch.ones_like(h_s)
                    g_a = torch.ones_like(h_a)
                else:
                    g_s = torch.sigmoid(self.sentiment_gate(torch.cat((h_s, h_a), dim=-1)))
                    g_a = torch.sigmoid(self.topic_gate(torch.cat((h_a, h_s), dim=-1)))
                z_s = self.sentiment_norm(h_s + g_s * m_s)
                z_a = self.topic_norm(h_a + g_a * m_a)
                gates = {"sentiment": g_s, "topic": g_a}
        logits = (self.sentiment_head(z_s), self.topic_head(z_a))
        return (logits, gates) if return_gates else logits

    def multitask_loss(self, logits: Tuple[Tensor, Tensor], sentiment: Tensor, topic: Tensor) -> Tensor:
        return 0.5 * (
            nn.functional.cross_entropy(logits[0], sentiment)
            + nn.functional.cross_entropy(logits[1], topic)
        )


def count_parameters(model: nn.Module) -> Dict[str, int]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"total": int(total), "trainable": int(trainable)}
