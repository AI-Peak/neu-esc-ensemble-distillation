import torch
from adaptive_interaction import AdaptiveInteractionModel, InteractionConfig, count_parameters

class Encoder(torch.nn.Module):
    def __init__(self):
        super().__init__(); self.emb = torch.nn.Embedding(50, 16); self.config = type("C", (), {"hidden_size": 16})()
    def forward(self, input_ids, attention_mask=None): return type("O", (), {"last_hidden_state": self.emb(input_ids)})()

def test_variants_forward_and_gradients():
    x = torch.randint(0, 50, (4, 8)); mask = torch.ones_like(x); ys = torch.randint(0,4,(4,)); yt = torch.randint(0,10,(4,))
    for variant in ("independent", "ungated", "adaptive"):
        model = AdaptiveInteractionModel(Encoder(), InteractionConfig(16, 12, 0.0, variant))
        logits, gates = model(x, mask, return_gates=True)
        assert logits[0].shape == (4,4) and logits[1].shape == (4,10)
        loss = model.multitask_loss(logits, ys, yt); loss.backward()
        active = [p for p in model.parameters() if p.requires_grad and p.grad is not None]
        assert active, "loss must backpropagate through trainable parameters"
        assert model.encoder.emb.weight.grad is not None
        if variant == "adaptive": assert torch.all((gates["sentiment"] >= 0) & (gates["sentiment"] <= 1))
        assert count_parameters(model)["trainable"] > 0

if __name__ == "__main__": test_variants_forward_and_gradients(); print("PASS")
